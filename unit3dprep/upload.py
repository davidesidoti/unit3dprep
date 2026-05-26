"""Pre-flight helpers used by the wizard + CLI.

Holds audio-check results, name-build helpers, and hardlink utilities. The
actual upload step is handled by `unit3dprep.web.webup_orchestrator` (HTTP
calls to Unit3DWebUp) — there is no longer any unit3dup CLI subprocess.

Hardlink layout: every upload lives in its own per-job sandbox directory
under `<seedings>/.unit3dprep/<jobid>/...`. This isolates each upload from
the rest of the seedings tree so Unit3DWebUp's `/scan` (which always
processes the entire SCAN_PATH) never re-scans unrelated files. The
sandbox path is deterministic from the final name, so re-uploading the
same item overwrites its sandbox cleanly.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

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
)


_SANDBOX_PARENT = ".unit3dprep"


def _sandbox_id(key: str) -> str:
    """Stable 8-char id derived from `key` (the final name).

    Same final_name → same sandbox dir → re-uploads overwrite cleanly.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _sandbox_dir(key: str) -> Path:
    """Resolve the per-job sandbox directory inside the configured seedings root."""
    seed = seedings_dir()
    return seed / _SANDBOX_PARENT / _sandbox_id(key)


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
            title=series_title, year="", se=se,
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
    """Hardlink a single movie file into its dedicated sandbox.

    Layout: `<seedings>/.unit3dprep/<jobid>/<final_name>.<ext>`.
    SCAN_PATH for webup will be the sandbox dir; webup sees one file → one
    Media → no concurrent scan of unrelated seedings entries.
    """
    sandbox = _sandbox_dir(final_name)
    sandbox.mkdir(parents=True, exist_ok=True)
    target = sandbox / f"{final_name}{src.suffix.lower()}"
    hardlink_file(src, target, overwrite=True)
    return target


def do_hardlink_series(
    src_dir: Path,
    folder_name: str,
    episode_rename: dict[Path, str],
) -> Path:
    """Hardlink an entire series/season pack into its dedicated sandbox.

    Layout: `<seedings>/.unit3dprep/<jobid>/<folder_name>/<episodes>`.
    SCAN_PATH for webup will be the sandbox dir; webup sees one subfolder
    → one Media (recognized as a pack).
    """
    sandbox = _sandbox_dir(folder_name)
    sandbox.mkdir(parents=True, exist_ok=True)
    target_dir = sandbox / folder_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    hardlink_tree(src_dir, target_dir, episode_rename)
    return target_dir
