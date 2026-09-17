"""Read-only Sonarr release provenance, tied to the current imported files."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from . import arr


def _timestamp(value: str) -> float:
    if not isinstance(value, str) or not value:
        raise ValueError("Missing history timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def match_history(files: list[dict], episodes: list[dict], history: list[dict]) -> dict[str, str]:
    """Join current file -> import -> grab using episode, path, time and download ID.

    Names alone are not evidence: older downloads of the same episode must not
    supply provenance for a replacement file. Multi-episode files need consensus.
    """
    result = {}
    for f in files:
        path = f["path"]
        ids = {e["id"] for e in episodes if e.get("episodeFileId") == f["id"]}
        titles = set()
        for eid in ids:
            imports = [r for r in history if r.get("eventType") == "downloadFolderImported"
                       and r.get("episodeId") == eid
                       and arr.norm_path((r.get("data") or {}).get("importedPath", "")) == arr.norm_path(path)]
            if not imports:
                break
            latest = max(imports, key=lambda r: r.get("date", ""))
            try:
                imported_at = _timestamp(latest["date"])
                if abs(imported_at - _timestamp(f["dateAdded"])) > 120:
                    break
            except (KeyError, TypeError, ValueError):
                break
            download_id = (latest.get("downloadId") or "").lower()
            if not download_id:
                break
            grabs = [r for r in history if r.get("eventType") == "grabbed"
                     and r.get("episodeId") == eid
                     and (r.get("downloadId") or "").lower() == download_id
                     and r.get("sourceTitle")]
            valid = []
            for grab in grabs:
                try:
                    if _timestamp(grab["date"]) <= imported_at:
                        valid.append(grab["sourceTitle"])
                except (KeyError, TypeError, ValueError):
                    continue
            if len(set(valid)) != 1:
                break
            titles.add(valid[0])
        else:
            if ids and len(titles) == 1:
                result[path] = titles.pop()
    return result


async def _fetch(paths: list[Path]) -> dict[str, str]:
    series = await arr._get_json("sonarr", "api/v3/series")
    result = {}
    for show in series:
        root = arr.norm_path(show.get("path", ""))
        if not root:
            continue
        selected = {arr.norm_path(str(p)): p for p in paths
                    if p.is_relative_to(Path(root))}
        if not selected:
            continue
        params = {"seriesId": show["id"]}
        files, episodes, history = await asyncio.gather(
            arr._get_json("sonarr", "api/v3/episodefile", params),
            arr._get_json("sonarr", "api/v3/episode", params),
            arr._get_json("sonarr", "api/v3/history/series", params),
        )
        if isinstance(history, dict):
            history = history.get("records", [])
        current = []
        for f in files:
            file_path = f.get("path") or str(Path(root) / f.get("relativePath", ""))
            local = selected.get(arr.norm_path(file_path))
            # Ensure Sonarr still describes the file the wizard is examining.
            if local is not None and local.stat().st_size == f.get("size"):
                current.append({**f, "path": str(local)})
        result.update(match_history(current, episodes, history))
    return result


async def fetch_release_names(paths: list[Path]) -> tuple[dict[str, str], str]:
    """Optional enrichment: an unavailable Sonarr never blocks the naming step."""
    if not paths or not arr.configured("sonarr"):
        return {}, ""
    try:
        return await asyncio.wait_for(_fetch(paths), timeout=20), ""
    except Exception:
        # No URLs, response bodies or API credentials in user-visible errors.
        return {}, "sonarr_unavailable"
