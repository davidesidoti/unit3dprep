"""Upload orchestration. Yields progress events as dicts."""
import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, Optional

from guessit import guessit

from .core import (
    SEEDINGS_DIR,
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
    SEEDINGS_DIR.mkdir(parents=True, exist_ok=True)
    target = SEEDINGS_DIR / f"{final_name}{src.suffix.lower()}"
    hardlink_file(src, target, overwrite=True)
    return target


def do_hardlink_series(
    src_dir: Path,
    folder_name: str,
    episode_rename: dict[Path, str],
) -> Path:
    SEEDINGS_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = SEEDINGS_DIR / folder_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    hardlink_tree(src_dir, target_dir, episode_rename)
    return target_dir


# Patterns that indicate unit3dup is waiting for user input on stdin.
# These prompts don't end with \n so readline() would block forever.
_PROMPT_PATTERNS = [
    "Please digit a valid TMDB ID",
    "Please digit a valid",
    "digit a valid",
    "insert a valid",
]


def _is_prompt(text: str) -> bool:
    t = text.strip()
    return any(p.lower() in t.lower() for p in _PROMPT_PATTERNS)


async def stream_unit3dup(
    args: list[str],
    input_queue: Optional[asyncio.Queue] = None,
    tmdb_id: str = "",
) -> AsyncGenerator[dict, None]:
    """Async generator yielding event dicts:
      {'type': 'log',         'data': str}
      {'type': 'input_needed','data': str}   — unit3dup waiting for stdin
      {'type': 'error',       'data': str}
      {'type': 'done',        'data': '', 'exit_code': int}
    When input_queue is provided, responses typed by the user are put there
    and forwarded to the subprocess stdin.
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
    # The system libsqlite3 on Ultra.cc is 3.8.6 (lacks sqlite3_deserialize);
    # pyenv Python must pick up the newer one built from source.
    local_lib = os.path.join(home, ".local", "lib")
    current_ldpath = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = local_lib + (os.pathsep + current_ldpath if current_ldpath else "")

    # Force unbuffered output so prompts (no trailing \n) arrive immediately.
    env["PYTHONUNBUFFERED"] = "1"

    # Resolve absolute path if possible (avoids relying on PATH at exec time)
    unit3dup_bin = shutil.which("unit3dup", path=env["PATH"]) or "unit3dup"

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
    assert proc.stdin is not None

    buf = ""
    while True:
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(512), timeout=0.3)
        except asyncio.TimeoutError:
            # Nothing arrived — if buffer looks like a prompt, ask the user.
            if buf and _is_prompt(buf):
                yield {"type": "input_needed", "data": buf.strip()}
                _default = tmdb_id if (tmdb_id and "tmdb id" in buf.lower()) else "0"
                user_input = (await input_queue.get()) if input_queue is not None else _default
                proc.stdin.write((user_input + "\n").encode())
                await proc.stdin.drain()
                buf = ""
            continue

        if not chunk:
            # EOF from process
            if buf.strip():
                yield {"type": "log", "data": buf.rstrip()}
            break

        text = chunk.decode("utf-8", errors="replace")
        buf += text

        # Flush any complete lines from the buffer
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if line.strip():
                yield {"type": "log", "data": line}

        # Partial line remaining — check if it's already a prompt
        if buf and _is_prompt(buf):
            yield {"type": "input_needed", "data": buf.strip()}
            _default = tmdb_id if (tmdb_id and "tmdb id" in buf.lower()) else "0"
            user_input = (await input_queue.get()) if input_queue is not None else _default
            proc.stdin.write((user_input + "\n").encode())
            await proc.stdin.drain()
            buf = ""

    exit_code = await proc.wait()
    yield {"type": "done", "data": "", "exit_code": exit_code}
