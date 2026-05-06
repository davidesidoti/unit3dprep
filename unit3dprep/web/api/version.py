"""Versioning + auto-update endpoints.

- /api/version/info          → cached {app, webup} current/latest/newer
- /api/version/refresh       → force-refresh cache
- /api/version/changelog     → GitHub release body for a given app version
- /api/version/update/webup/stream      → SSE: git pull + pip install --upgrade Unit3DwebUp + systemctl restart unit3dwebup.service
- /api/version/update/app/stream        → SSE: git pull + pip install -e . + systemctl restart

Current app version: importlib.metadata (authoritative) with pyproject fallback.
Remote: GitHub releases/latest. 10-min in-memory cache, errors swallowed
(latest=None). Subprocess output streamed line-by-line.
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
from .._env import env as _env

try:
    from packaging.version import InvalidVersion, Version
except ImportError:
    Version = None
    InvalidVersion = Exception

router = APIRouter(prefix="/api", tags=["version"])

GITHUB_REPO = _env("U3DP_GITHUB_REPO", "ITA_GITHUB_REPO", "davidesidoti/unit3dprep") or "davidesidoti/unit3dprep"
WEBUP_GITHUB_REPO = "31December99/Unit3DWebUp"


def _systemd_unit() -> str:
    """Runtime-resolved systemd unit name. Reads from env → shared .env → default."""
    return runtime_setting("U3DP_SYSTEMD_UNIT", "unit3dprep-web.service")


def _webup_systemd_unit() -> str:
    return runtime_setting("WEBUP_SYSTEMD_UNIT", "unit3dwebup.service")


def _webup_repo_path() -> Path:
    return Path(runtime_setting("WEBUP_REPO_PATH", str(Path.home() / "dev" / "Unit3DWebUp"))).expanduser()


def _webup_python() -> str:
    """Resolve the python interpreter that has Unit3DwebUp installed.

    Precedence: WEBUP_VENV_BIN → <WEBUP_REPO_PATH>/.venv/bin → sys.executable
    (the running unit3dprep interpreter — works when both packages share a
    single venv, which is the canonical PyPI install layout).
    """
    explicit = runtime_setting("WEBUP_VENV_BIN", "")
    if explicit:
        return str(Path(explicit).expanduser() / "python")
    legacy = _webup_repo_path() / ".venv" / "bin" / "python"
    if legacy.exists():
        return str(legacy)
    return sys.executable
USER_AGENT = "unit3dprep/version-check"

_CACHE_TTL = 600.0
_CHANGELOG_TTL = 3600.0
_cache: dict[str, Any] = {"at": 0.0, "data": None}
_changelog_cache: dict[str, tuple[float, dict]] = {}


# ---------------------------------------------------------------- current --

def _current_app_version() -> str:
    # In git-checkout installs, pyproject.toml at the repo root is the authoritative
    # source — `git pull` updates it atomically. importlib.metadata can return stale
    # values when an orphan dist-info/egg-info shadows the fresh install.
    if _repo_root() is not None:
        try:
            import tomllib
            pyproject = _repo_root() / "pyproject.toml"
            v = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
            if v:
                return v
        except Exception:
            pass
    try:
        from importlib.metadata import version
        return version("unit3dprep")
    except Exception:
        pass
    try:
        import tomllib
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:
        return "0.0.0"


async def _current_webup_version() -> str | None:
    """Read VERSION from the running Unit3DWebUp instance via /setting."""
    try:
        from ..webup_client import get_client
        h = await get_client().health(force=False)
        if h.get("ok"):
            return h.get("version") or None
    except Exception:
        pass
    return None


def _current_webup_repo_version() -> str | None:
    """Best-effort: parse UNIT3DWEBUP__VERSION from .env(example) at the cloned repo."""
    repo = _webup_repo_path()
    for fname in (".env", ".env(example)"):
        f = repo / fname
        if not f.exists():
            continue
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("UNIT3DWEBUP__VERSION="):
                    return line.split("=", 1)[1].strip()
        except Exception:
            continue
    return None


def _current_webup_pip_version() -> str | None:
    """Read installed Unit3DwebUp version from the webup venv's site-packages.

    Webup 0.0.x is distributed via PyPI and no longer exposes a VERSION key in
    /setting nor in .env(example), so importlib.metadata against the webup venv
    is the canonical source.
    """
    py = _webup_python()
    if not Path(py).exists():
        return None
    try:
        r = subprocess.run(
            [py, "-c", "import importlib.metadata as m; print(m.version('Unit3DwebUp'))"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        v = (r.stdout or "").strip()
        return v or None
    except Exception:
        return None


# ---------------------------------------------------------------- remote --

async def _fetch_github_latest(client: httpx.AsyncClient) -> dict | None:
    try:
        r = await client.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
            timeout=10.0,
            follow_redirects=True,
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


async def _fetch_webup_latest(client: httpx.AsyncClient) -> str | None:
    try:
        r = await client.get(
            f"https://api.github.com/repos/{WEBUP_GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
            timeout=10.0,
            follow_redirects=True,
        )
        if r.status_code == 404:
            # No release published — fall back to default branch HEAD via tags
            r2 = await client.get(
                f"https://api.github.com/repos/{WEBUP_GITHUB_REPO}/tags",
                headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
                timeout=10.0,
                follow_redirects=True,
            )
            r2.raise_for_status()
            tags = r2.json() or []
            if tags:
                return (tags[0].get("name") or "").lstrip("v") or None
            return None
        r.raise_for_status()
        return (r.json().get("tag_name") or "").lstrip("v") or None
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
        release, webup_latest = await asyncio.gather(
            _fetch_github_latest(client),
            _fetch_webup_latest(client),
        )
    app_current = _current_app_version()
    app_latest = release["version"] if release else None
    webup_current = (
        await _current_webup_version()
        or _current_webup_pip_version()
        or _current_webup_repo_version()
    )
    return {
        "app": {
            "current": app_current,
            "latest": app_latest,
            "newer": _is_newer(app_current, app_latest),
            "release": release,
        },
        "webup": {
            "current": webup_current,
            "latest": webup_latest,
            "newer": _is_newer(webup_current, webup_latest),
            "installed": webup_current is not None,
            "repo_path": str(_webup_repo_path()),
        },
        "can_update_app": _systemd_available(),
        "can_update_webup": _webup_can_update(),
    }


def _webup_can_update() -> bool:
    """True iff we have a python interpreter able to `pip install --upgrade
    Unit3DwebUp` AND a reachable systemd user unit for the webup service.

    The legacy git-clone path (`<WEBUP_REPO_PATH>/.git`) is no longer required
    — Unit3DwebUp 0.0.x is distributed via PyPI, so a pip install is the
    canonical update path. If a checkout exists we'll still `git pull` it
    before pip-installing, but its absence is not a failure.
    """
    if not Path(_webup_python()).exists():
        return False
    if not shutil.which("systemctl"):
        return False
    try:
        r = subprocess.run(
            ["systemctl", "--user", "cat", _webup_systemd_unit()],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


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
                follow_redirects=True,
            )
            if r.status_code == 404:
                r = await client.get(
                    f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{v}",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
                    timeout=10.0,
                    follow_redirects=True,
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


@router.get("/version/update/webup/stream")
async def update_webup():
    """Update Unit3DWebUp: git pull → pip install → systemctl restart."""
    async def gen() -> AsyncGenerator[dict, None]:
        before = (
            await _current_webup_version()
            or _current_webup_pip_version()
            or _current_webup_repo_version()
        )
        yield _sse("start", {"target": "webup", "current": before})

        if not _webup_can_update():
            py = _webup_python()
            if not Path(py).exists():
                yield _sse("error", {"message": f"webup python not found at {py} (set WEBUP_VENV_BIN)"})
            else:
                yield _sse("error", {"message": f"webup systemd unit '{_webup_systemd_unit()}' not available"})
            yield _sse("done", {"ok": False})
            return

        repo = _webup_repo_path()
        # Optional: if a git checkout exists at WEBUP_REPO_PATH, refresh it first.
        # PyPI install does not require this; we only do it for users who run
        # webup from a local checkout (legacy / dev setups).
        if (repo / ".git").exists():
            for argv in (
                ["git", "fetch", "--all"],
                ["git", "pull", "--ff-only"],
            ):
                async for ev in _stream_subprocess(argv, cwd=repo):
                    if ev["event"] == "exit":
                        if json.loads(ev["data"])["code"] != 0:
                            yield _sse("error", {"message": f"{argv[0]} {argv[1]} failed"})
                            yield _sse("done", {"ok": False})
                            return
                        break
                    yield ev

        py = _webup_python()
        pip_cwd = repo if repo.exists() else None
        async for ev in _stream_subprocess(
            [py, "-m", "pip", "install", "--upgrade", "Unit3DwebUp"], cwd=pip_cwd
        ):
            if ev["event"] == "exit":
                if json.loads(ev["data"])["code"] != 0:
                    yield _sse("error", {"message": "pip install failed"})
                    yield _sse("done", {"ok": False})
                    return
                break
            yield ev

        # Restart webup service via systemd-run timer (fire-and-forget;
        # outside our cgroup, won't be killed when this request finishes).
        unit = _webup_systemd_unit()
        if shutil.which("systemd-run"):
            try:
                subprocess.run(
                    [
                        "systemd-run", "--user", "--on-active=2s",
                        "--unit", f"webup-restart-{int(time.time())}",
                        "systemctl", "--user", "restart", unit,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=10,
                    check=True,
                )
                yield _sse("log", f"restart scheduled for {unit} (2s)")
            except Exception as exc:
                yield _sse("log", f"systemd-run failed, fallback Popen: {exc}")
                try:
                    subprocess.Popen(
                        ["systemctl", "--user", "restart", unit],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except Exception as exc2:
                    yield _sse("error", {"message": f"failed to spawn systemctl: {exc2}"})

        # Invalidate cache so the next /version/info reflects the new version.
        _cache["data"] = None
        _cache["at"] = 0.0
        # webup HTTP probably down right now (just restarted) — fall back to
        # the pip-installed version, which is updated synchronously above.
        after = _current_webup_pip_version() or _current_webup_repo_version()
        yield _sse("done", {"ok": True, "target": "webup", "from": before, "to": after})

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

        # Schedule the restart via a transient systemd-run timer so the restart
        # command lives OUTSIDE this service's cgroup. A plain `Popen(...,
        # start_new_session=True)` child stays in the parent unit's cgroup and
        # gets killed together with it when systemd stops the service.
        restart_scheduled = False
        if shutil.which("systemd-run"):
            try:
                subprocess.run(
                    [
                        "systemd-run", "--user", "--on-active=3s",
                        "--unit", f"unit3dprep-restart-{int(time.time())}",
                        "systemctl", "--user", "restart", _systemd_unit(),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=10,
                    check=True,
                )
                restart_scheduled = True
                yield _sse("log", "restart scheduled via systemd-run (3s)")
            except Exception as exc:
                yield _sse("log", f"systemd-run failed, falling back: {exc}")

        if not restart_scheduled:
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


async def _clean_stale_metadata(repo: Path) -> AsyncGenerator[dict, None]:
    """Remove stale egg-info (source tree) and orphan dist-info (site-packages)
    that can shadow the fresh install and confuse importlib.metadata.
    """
    for egg_name in ("unit3dprep.egg-info", "itatorrents.egg-info"):
        egg_info = repo / egg_name
        if egg_info.exists():
            yield _sse("log", f"removing stale egg-info: {egg_info}")
            shutil.rmtree(egg_info, ignore_errors=True)

    try:
        import site
        roots: list[Path] = []
        for p in [site.getusersitepackages(), *site.getsitepackages()]:
            rp = Path(p)
            if rp.exists() and rp not in roots:
                roots.append(rp)
        for root in roots:
            for pkg in ("unit3dprep", "itatorrents"):
                for d in root.glob(f"{pkg}-*.dist-info"):
                    yield _sse("log", f"removing dist-info: {d}")
                    shutil.rmtree(d, ignore_errors=True)
                for pth in root.glob(f"__editable__.{pkg}-*.pth"):
                    yield _sse("log", f"removing editable pth: {pth}")
                    try:
                        pth.unlink()
                    except Exception:
                        pass
    except Exception as exc:
        yield _sse("log", f"cleanup warning: {exc}")


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

    # Fetch + pull first, THEN clean metadata so pip install creates fresh
    # dist-info without any leftovers shadowing it.
    for argv in (
        ["git", "fetch", "origin", "main"],
        ["git", "pull", "--ff-only", "origin", "main"],
    ):
        async for ev in _stream_subprocess(argv, cwd=repo):
            if ev["event"] == "exit":
                if json.loads(ev["data"])["code"] != 0:
                    yield _sse("error", {"message": f"{argv[0]} failed"})
                    yield _sse("done", {"ok": False})
                    return
                break
            yield ev

    # Uninstall in a loop (pip doesn't remove orphan dist-info reliably).
    # Target both the new name and the legacy one for mid-rename upgrades.
    for pkg_name in ("unit3dprep", "itatorrents"):
        for _ in range(3):
            done_uninstall = False
            async for ev in _stream_subprocess(
                [sys.executable, "-m", "pip", "uninstall", "-y", pkg_name], cwd=repo
            ):
                if ev["event"] == "exit":
                    done_uninstall = True
                    break
                yield ev
            if done_uninstall:
                break

    async for ev in _clean_stale_metadata(repo):
        yield ev

    async for ev in _stream_subprocess(
        [sys.executable, "-m", "pip", "install", "-e", "."], cwd=repo
    ):
        if ev["event"] == "exit":
            if json.loads(ev["data"])["code"] != 0:
                yield _sse("error", {"message": "pip install failed"})
                yield _sse("done", {"ok": False})
                return
            break
        yield ev

    after = _current_app_version()
    # Invalidate /version/info cache so post-reload poll re-computes against
    # the freshly installed version — otherwise the old process (if still
    # answering during the restart race) returns stale {newer: true}.
    _cache["data"] = None
    _cache["at"] = 0.0
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
    _cache["data"] = None
    _cache["at"] = 0.0
    yield _sse("log", f"restarting systemd unit {_systemd_unit()}…")
    yield _sse("done", {"ok": True, "target": "app", "from": before, "to": after, "mode": "pip"})
