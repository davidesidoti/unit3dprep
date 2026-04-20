"""Upload orchestration. Yields progress events as dicts."""
import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, Optional

# pty is Linux-only; graceful fallback to pipe mode on Windows (dev)
try:
    import pty
    import fcntl
    _HAS_PTY = True
except ImportError:
    _HAS_PTY = False

# Strip ANSI/VT escape sequences (colours, cursor moves, etc.) from text
_ANSI_RE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-9;]*[a-zA-Z]|\][^\x07]*\x07)')

from guessit import guessit

from .core import (
    seedings_dir,
    build_name,
    extract_specs,
    format_se,
    hardlink_file,
    hardlink_tree,
    has_italian_audio,
    map_source,
    tmdb_fetch,
    tmdb_year,
)


@dataclass
class AudioResult:
    path: Path
    has_italian: bool
    error: str = ""


def check_audio_files(paths: list[Path]) -> list[AudioResult]:
    results = []
    for p in paths:
        try:
            ok = has_italian_audio(p)
            results.append(AudioResult(path=p, has_italian=ok))
        except Exception as e:
            results.append(AudioResult(path=p, has_italian=False, error=str(e)))
    return results


def build_episode_names(
    series_folder: Path,
    video_files: list[Path],
    series_title: str,
    year: str,
    folder_guess: dict,
) -> dict[Path, str]:
    """Returns mapping file_path → new_base_name (no extension)."""
    episode_rename: dict[Path, str] = {}
    for f in video_files:
        g = dict(guessit(f.name))
        season = g.get("season")
        if isinstance(season, list):
            season = season[0]
        episode = g.get("episode")
        se = format_se(season, episode)
        if not se:
            continue
        specs = extract_specs(f)
        source, src_type = map_source(g)
        tag = g.get("release_group", "") or folder_guess.get("release_group", "") or ""
        new_name = build_name(
            title=series_title, year=year, se=se,
            specs=specs, source=source, src_type=src_type, tag=tag,
        )
        episode_rename[f] = new_name
    return episode_rename


def build_movie_name_from_file(
    video_file: Path,
    movie_title: str,
    year: str,
) -> str:
    g = dict(guessit(video_file.name))
    specs = extract_specs(video_file)
    source, src_type = map_source(g)
    tag = g.get("release_group", "") or ""
    repack = "REPACK" if g.get("proper_count") else ""
    return build_name(
        title=movie_title, year=year, se="",
        specs=specs, source=source, src_type=src_type, tag=tag, repack=repack,
    )


def do_hardlink_movie(src: Path, final_name: str) -> Path:
    seed = seedings_dir()
    seed.mkdir(parents=True, exist_ok=True)
    target = seed / f"{final_name}{src.suffix.lower()}"
    hardlink_file(src, target, overwrite=True)
    return target


def do_hardlink_series(
    src_dir: Path,
    folder_name: str,
    episode_rename: dict[Path, str],
) -> Path:
    seed = seedings_dir()
    seed.mkdir(parents=True, exist_ok=True)
    target_dir = seed / folder_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    hardlink_tree(src_dir, target_dir, episode_rename)
    return target_dir


# Patterns that indicate unit3dup is waiting for user input on stdin.
# These prompts don't end with \n so readline() would block forever.
_TMDB_PROMPT_PATTERNS = [
    "Please digit a valid TMDB ID",
    "Please digit a valid",
    "digit a valid",
    "insert a valid",
]

# Patterns that indicate the duplicate-check interactive prompt (C/S/Q)
_DUPLICATE_PROMPT_PATTERNS = [
    "press (c) to continue",
    "(s) to skip",
    "(q) quit",
]

_ALL_PROMPT_PATTERNS = _TMDB_PROMPT_PATTERNS + _DUPLICATE_PROMPT_PATTERNS


def _is_prompt(text: str) -> bool:
    t = text.strip().lower()
    return any(p.lower() in t for p in _ALL_PROMPT_PATTERNS)


def _prompt_kind(text: str) -> str:
    """Return 'duplicate' if text is the C/S/Q duplicate prompt, else 'tmdb'."""
    t = text.strip().lower()
    if any(p in t for p in _DUPLICATE_PROMPT_PATTERNS):
        return "duplicate"
    return "tmdb"


async def stream_unit3dup(
    args: list[str],
    input_queue: Optional[asyncio.Queue] = None,
    tmdb_id: str = "",
) -> AsyncGenerator[dict, None]:
    """Async generator yielding event dicts:
      {'type': 'log',         'data': str}
      {'type': 'progress',    'data': str}   — in-place overwrite line (\\r-terminated)
      {'type': 'input_needed','kind': 'tmdb'|'duplicate', 'data': str}
      {'type': 'error',       'data': str}
      {'type': 'done',        'data': '', 'exit_code': int}

    On Linux uses a pty so rich/tqdm see a TTY and emit live progress.
    Falls back to pipe mode on Windows (dev only).
    ANSI escape sequences are stripped before yielding.
    """
    # Systemd user services have a minimal PATH; augment with common user bin dirs
    # so unit3dup installed via pyenv/pip/~/.local is found even from the service.
    home = str(Path.home())
    extra_dirs = [
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".pyenv", "shims"),
        os.path.join(home, ".pyenv", "bin"),
        os.path.join(home, "bin"),
    ]
    env = os.environ.copy()
    current_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(extra_dirs) + os.pathsep + current_path

    # Ensure user-compiled libsqlite3 (in ~/.local/lib) is loaded at runtime.
    local_lib = os.path.join(home, ".local", "lib")
    current_ldpath = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = local_lib + (os.pathsep + current_ldpath if current_ldpath else "")

    # Force unbuffered output so prompts (no trailing \n) arrive immediately.
    env["PYTHONUNBUFFERED"] = "1"

    # Resolve absolute path if possible (avoids relying on PATH at exec time)
    unit3dup_bin = shutil.which("unit3dup", path=env["PATH"]) or "unit3dup"

    master_fd: Optional[int] = None

    # ------------------------------------------------------------------ pty --
    if _HAS_PTY:
        # Open a pty so unit3dup/rich thinks it's writing to a real terminal →
        # live progress-bar updates instead of a single flush at exit.
        master_fd, slave_fd = pty.openpty()
        try:
            import struct
            import termios
            winsize = struct.pack("HHHH", 40, 120, 0, 0)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass
        env.update({"COLUMNS": "120", "LINES": "40",
                     "TERM": "xterm-256color", "FORCE_COLOR": "1"})

        try:
            proc = await asyncio.create_subprocess_exec(
                unit3dup_bin, *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
            )
        except FileNotFoundError:
            os.close(master_fd)
            os.close(slave_fd)
            yield {"type": "error", "data": f"'unit3dup' not found in PATH.\nSearched: {env['PATH']}"}
            return

        os.close(slave_fd)  # parent only needs master end

        # Set master fd non-blocking so loop.add_reader works correctly
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        loop = asyncio.get_running_loop()
        _pty_q: asyncio.Queue = asyncio.Queue()

        def _on_readable() -> None:
            try:
                data = os.read(master_fd, 4096)
                if data:
                    _pty_q.put_nowait(data)
            except BlockingIOError:
                pass
            except OSError:
                # EIO: child closed the slave (process exited)
                _pty_q.put_nowait(b"")
                loop.remove_reader(master_fd)

        loop.add_reader(master_fd, _on_readable)

        async def _read_chunk() -> bytes:
            return await asyncio.wait_for(_pty_q.get(), timeout=0.3)

    # --------------------------------------------------------------- pipe ---
    else:
        try:
            proc = await asyncio.create_subprocess_exec(
                unit3dup_bin, *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
        except FileNotFoundError:
            yield {"type": "error", "data": f"'unit3dup' not found in PATH.\nSearched: {env['PATH']}"}
            return

        assert proc.stdout is not None

        async def _read_chunk() -> bytes:
            return await asyncio.wait_for(proc.stdout.read(512), timeout=0.3)

    assert proc.stdin is not None

    # ------------------------------------------------- emit helper ----------
    async def _handle_prompt(raw: str) -> None:
        """Detect prompt kind, yield event, read user answer, forward to stdin."""
        kind = _prompt_kind(raw)
        yield_data = _ANSI_RE.sub("", raw).strip()
        # We can't yield from a nested function, so we push to a side-channel.
        # Caller drains _prompt_events after each chunk loop iteration.
        _prompt_events.append({"type": "input_needed", "kind": kind, "data": yield_data})
        if kind == "tmdb":
            _default = tmdb_id if tmdb_id else "0"
            answer = (await input_queue.get()) if input_queue is not None else _default
        else:
            # duplicate: always wait — no auto-skip
            answer = (await input_queue.get()) if input_queue is not None else "s"
        proc.stdin.write((answer + "\n").encode())
        await proc.stdin.drain()

    # Side-channel list for events produced inside the chunk-processing loop
    _prompt_events: list[dict] = []

    # ------------------------------------------------- main read loop -------
    buf = ""
    while True:
        # --- read chunk ---
        try:
            chunk = await _read_chunk()
        except asyncio.TimeoutError:
            if buf and _is_prompt(buf):
                kind = _prompt_kind(buf)
                prompt_text = _ANSI_RE.sub("", buf).strip()
                yield {"type": "input_needed", "kind": kind, "data": prompt_text}
                if kind == "tmdb":
                    _default = tmdb_id if tmdb_id else "0"
                    answer = (await input_queue.get()) if input_queue is not None else _default
                else:
                    answer = (await input_queue.get()) if input_queue is not None else "s"
                proc.stdin.write((answer + "\n").encode())
                await proc.stdin.drain()
                buf = ""
            continue

        if not chunk:
            # EOF — flush remainder
            if buf.strip():
                clean = _ANSI_RE.sub("", buf).rstrip()
                if clean:
                    yield {"type": "log", "data": clean}
            break

        # Strip ANSI, accumulate
        buf += _ANSI_RE.sub("", chunk.decode("utf-8", errors="replace"))

        # Split buf on \r\n / \n (log lines) and bare \r (progress overwrites)
        while True:
            rn = buf.find("\r\n")
            nl = buf.find("\n")
            cr = buf.find("\r")

            # Find earliest terminator; \r\n beats bare \r at same position
            candidates = [(p, t) for p, t in ((rn, "rn"), (nl, "nl"), (cr, "cr")) if p != -1]
            if not candidates:
                break
            earliest_pos, earliest_type = min(candidates, key=lambda x: x[0])

            if earliest_type == "rn":
                line, buf = buf[:rn], buf[rn + 2:]
                if line.strip():
                    yield {"type": "log", "data": line}
            elif earliest_type == "nl":
                line, buf = buf[:nl], buf[nl + 1:]
                if line.strip():
                    yield {"type": "log", "data": line}
            else:  # bare \r → progress overwrite
                line, buf = buf[:cr], buf[cr + 1:]
                if line.strip():
                    yield {"type": "progress", "data": line}

        # Partial line: check if it's already a prompt
        if buf and _is_prompt(buf):
            kind = _prompt_kind(buf)
            prompt_text = _ANSI_RE.sub("", buf).strip()
            yield {"type": "input_needed", "kind": kind, "data": prompt_text}
            if kind == "tmdb":
                _default = tmdb_id if tmdb_id else "0"
                answer = (await input_queue.get()) if input_queue is not None else _default
            else:
                answer = (await input_queue.get()) if input_queue is not None else "s"
            proc.stdin.write((answer + "\n").encode())
            await proc.stdin.drain()
            buf = ""

    # Cleanup pty fds
    if master_fd is not None:
        try:
            loop.remove_reader(master_fd)
        except Exception:
            pass
        try:
            os.close(master_fd)
        except Exception:
            pass

    exit_code = await proc.wait()
    yield {"type": "done", "data": "", "exit_code": exit_code}
