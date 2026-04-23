"""Versioning + auto-update endpoints.

- /api/version/info          → cached {app, unit3dup} current/latest/newer
- /api/version/refresh       → force-refresh cache
- /api/version/changelog     → GitHub release body for a given app version
- /api/version/update/unit3dup/stream   → SSE: pip install --upgrade unit3dup
- /api/version/update/app/stream        → SSE: git pull + pip install -e . + systemctl restart

Current app version: importlib.metadata (authoritative) with pyproject fallback.
Remote: GitHub releases/latest + PyPI JSON. 10-min in-memory cache, errors
swallowed (latest=None). Subprocess output streamed line-by-line.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from ..config import runtime_setting

try:
    from packaging.version import InvalidVersion, Version
except ImportError:
    Version = None
    InvalidVersion = Exception

router = APIRouter(prefix="/api", tags=["version"])

GITHUB_REPO = os.environ.get("ITA_GITHUB_REPO", "davidesidoti/itatorrents-seeding")
PYPI_URL = "https://pypi.org/pypi/unit3dup/json"


def _systemd_unit() -> str:
    """Runtime-resolved systemd unit name. Reads from env → Unit3Dbot.json → default."""
    return runtime_setting("ITA_SYSTEMD_UNIT", "itatorrents.service")
USER_AGENT = "itatorrents-seeding/version-check"

_CACHE_TTL = 600.0
_CHANGELOG_TTL = 3600.0
_cache: dict[str, Any] = {"at": 0.0, "data": None}
_changelog_cache: dict[str, tuple[float, dict]] = {}


# ---------------------------------------------------------------- current --

def _current_app_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version
        return version("itatorrents")
    except Exception:
        pass
    try:
        import tomllib
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:
        return "0.0.0"


def _current_unit3dup_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("unit3dup")
    except Exception:
        return None


# ---------------------------------------------------------------- remote --

async def _fetch_github_latest(client: httpx.AsyncClient) -> dict | None:
    try:
        r = await client.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
            timeout=10.0,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        j = r.json()
        tag = (j.get("tag_name") or "").lstrip("v")
        if not tag:
            return None
        return {
            "version": tag,
            "body": j.get("body") or "",
            "html_url": j.get("html_url") or "",
            "published_at": j.get("published_at") or "",
            "name": j.get("name") or tag,
        }
    except Exception:
        return None


async def _fetch_pypi_latest(client: httpx.AsyncClient) -> str | None:
    try:
        r = await client.get(PYPI_URL, headers={"User-Agent": USER_AGENT}, timeout=10.0)
        r.raise_for_status()
        return r.json().get("info", {}).get("version")
    except Exception:
        return None


def _is_newer(current: str | None, latest: str | None) -> bool:
    if not current or not latest:
        return False
    if Version is None:
        return current != latest
    try:
        return Version(current) < Version(latest)
    except InvalidVersion:
        return current != latest


async def _compute_info() -> dict:
    async with httpx.AsyncClient() as client:
        release, pypi = await asyncio.gather(
            _fetch_github_latest(client),
            _fetch_pypi_latest(client),
        )
    app_current = _current_app_version()
    app_latest = release["version"] if release else None
    bot_current = _current_unit3dup_version()
    return {
        "app": {
            "current": app_current,
            "latest": app_latest,
            "newer": _is_newer(app_current, app_latest),
            "release": release,
        },
        "unit3dup": {
            "current": bot_current,
            "latest": pypi,
            "newer": _is_newer(bot_current, pypi),
            "installed": bot_current is not None,
        },
        "can_update_app": _systemd_available(),
    }


def _systemd_available() -> bool:
    """True iff the systemd unit file exists and is loadable.

    Uses `systemctl --user cat` which returns 0 for any valid state
    (enabled, linked, static, disabled) and non-zero only when the unit
    cannot be found. Previous `is-enabled` check incorrectly rejected
    symlinked (`linked`) units.
    """
    if not shutil.which("systemctl"):
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "cat", _systemd_unit()],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _install_mode() -> str:
    """Returns 'git' if the package was installed from a git checkout
    (has a reachable `.git` at repo root) or 'pip' otherwise (e.g. installed
    via `pip install git+https://...@tag`, which drops the `.git` folder).
    """
    if _repo_root() is not None:
        return "git"
    return "pip"


async def _get_info(force: bool = False) -> dict:
    now = time.time()
    if not force and _cache["data"] and (now - _cache["at"]) < _CACHE_TTL:
        return _cache["data"]
    data = await _compute_info()
    _cache["at"] = now
    _cache["data"] = data
    return data


# ---------------------------------------------------------------- routes --

@router.get("/version/info")
async def info():
    return await _get_info()


@router.post("/version/refresh")
async def refresh():
    return await _get_info(force=True)


@router.get("/version/changelog")
async def changelog(v: str = Query(..., min_length=1, max_length=64)):
    v = v.strip().lstrip("v")
    now = time.time()
    cached = _changelog_cache.get(v)
    if cached and (now - cached[0]) < _CHANGELOG_TTL:
        return cached[1]
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/v{v}",
                headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
                timeout=10.0,
            )
            if r.status_code == 404:
                r = await client.get(
                    f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{v}",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
                    timeout=10.0,
                )
            r.raise_for_status()
            j = r.json()
            out = {
                "version": v,
                "name": j.get("name") or v,
                "body": j.get("body") or "",
                "html_url": j.get("html_url") or "",
                "published_at": j.get("published_at") or "",
            }
        except Exception as exc:
            raise HTTPException(404, f"Release not found: {exc}")
    _changelog_cache[v] = (now, out)
    return out


# ---------------------------------------------------------------- update --

def _sse(event: str, payload: Any) -> dict:
    return {"event": event, "data": json.dumps(payload) if not isinstance(payload, str) else payload}


async def _stream_subprocess(argv: list[str], cwd: Path | None = None) -> AsyncGenerator[dict, None]:
    yield _sse("log", f"$ {' '.join(argv)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as exc:
        yield _sse("error", {"message": f"command not found: {exc}"})
        return
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        try:
            text = line.decode("utf-8", errors="replace").rstrip()
        except Exception:
            text = repr(line)
        if text:
            yield _sse("log", text)
    code = await proc.wait()
    yield _sse("exit", {"code": code})


@router.get("/version/update/unit3dup/stream")
async def update_unit3dup():
    async def gen() -> AsyncGenerator[dict, None]:
        before = _current_unit3dup_version()
        yield _sse("start", {"target": "unit3dup", "current": before})
        failed = False
        async for ev in _stream_subprocess([sys.executable, "-m", "pip", "install", "--upgrade", "unit3dup"]):
            if ev["event"] == "exit":
                payload = json.loads(ev["data"])
                if payload["code"] != 0:
                    failed = True
                    yield _sse("error", {"message": f"pip exited with code {payload['code']}"})
                break
            yield ev
        if failed:
            yield _sse("done", {"ok": False})
            return
        after = _current_unit3dup_version()
        yield _sse("done", {"ok": True, "target": "unit3dup", "from": before, "to": after})

    return EventSourceResponse(gen())


async def _git(argv: list[str], cwd: Path) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *argv,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd),
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace").strip()


def _repo_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / ".git").exists():
        return candidate
    return None


@router.get("/version/update/app/stream")
async def update_app():
    async def gen() -> AsyncGenerator[dict, None]:
        before = _current_app_version()
        mode = _install_mode()
        yield _sse("start", {"target": "app", "current": before, "mode": mode})

        if not _systemd_available():
            yield _sse("error", {"message": f"systemd unit '{_systemd_unit()}' not available"})
            yield _sse("done", {"ok": False})
            return

        if mode == "git":
            async for ev in _update_app_from_git():
                yield ev
                data = ev.get("data") or ""
                if ev["event"] == "done":
                    try:
                        if not json.loads(data).get("ok"):
                            return
                    except Exception:
                        return
                    break
        else:
            async for ev in _update_app_from_pip():
                yield ev
                data = ev.get("data") or ""
                if ev["event"] == "done":
                    try:
                        if not json.loads(data).get("ok"):
                            return
                    except Exception:
                        return
                    break

        await asyncio.sleep(1.5)

        try:
            subprocess.Popen(
                ["systemctl", "--user", "restart", _systemd_unit()],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            yield _sse("error", {"message": f"failed to spawn systemctl: {exc}"})

    return EventSourceResponse(gen())


async def _update_app_from_git() -> AsyncGenerator[dict, None]:
    before = _current_app_version()
    repo = _repo_root()
    assert repo is not None
    yield _sse("log", f"install mode: git checkout at {repo}")

    code, branch = await _git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    if code != 0:
        yield _sse("error", {"message": f"git failed: {branch}"})
        yield _sse("done", {"ok": False})
        return
    if branch != "main":
        yield _sse("error", {"message": f"refuse to update: on branch '{branch}', expected 'main'"})
        yield _sse("done", {"ok": False})
        return

    code, dirty = await _git(["status", "--porcelain"], repo)
    if code != 0:
        yield _sse("error", {"message": f"git status failed: {dirty}"})
        yield _sse("done", {"ok": False})
        return
    if dirty:
        yield _sse("error", {"message": "working tree has uncommitted changes — refuse to update"})
        yield _sse("done", {"ok": False})
        return

    for argv in (
        ["git", "fetch", "origin", "main"],
        ["git", "pull", "--ff-only", "origin", "main"],
        [sys.executable, "-m", "pip", "install", "-e", "."],
    ):
        async for ev in _stream_subprocess(argv, cwd=repo):
            if ev["event"] == "exit":
                if json.loads(ev["data"])["code"] != 0:
                    yield _sse("error", {"message": f"{argv[0]} failed"})
                    yield _sse("done", {"ok": False})
                    return
                break
            yield ev

    after = _current_app_version()
    yield _sse("log", f"restarting systemd unit {_systemd_unit()}…")
    yield _sse("done", {"ok": True, "target": "app", "from": before, "to": after, "mode": "git"})


async def _update_app_from_pip() -> AsyncGenerator[dict, None]:
    before = _current_app_version()
    yield _sse("log", "install mode: pip (non-git) — will reinstall from GitHub tag")

    info = await _get_info(force=True)
    latest = (info.get("app") or {}).get("latest")
    if not latest:
        yield _sse("error", {"message": "cannot determine latest release (network issue or no GitHub release yet)"})
        yield _sse("done", {"ok": False})
        return

    spec = f"git+https://github.com/{GITHUB_REPO}.git@v{latest}"
    async for ev in _stream_subprocess(
        [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps", spec]
    ):
        if ev["event"] == "exit":
            if json.loads(ev["data"])["code"] != 0:
                yield _sse("error", {"message": "pip install failed"})
                yield _sse("done", {"ok": False})
                return
            break
        yield ev

    async for ev in _stream_subprocess(
        [sys.executable, "-m", "pip", "install", "--upgrade", spec]
    ):
        if ev["event"] == "exit":
            if json.loads(ev["data"])["code"] != 0:
                yield _sse("error", {"message": "pip install (deps) failed"})
                yield _sse("done", {"ok": False})
                return
            break
        yield ev

    after = _current_app_version()
    yield _sse("log", f"restarting systemd unit {_systemd_unit()}…")
    yield _sse("done", {"ok": True, "target": "app", "from": before, "to": after, "mode": "pip"})
