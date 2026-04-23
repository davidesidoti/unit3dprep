"""Classifier for unit3dup stdout lines.

Turns raw subprocess output into (kind, event) tuples so the Logs tab can
group related output and hide decorative noise behind the debug filter.

Unknown lines fall through as ("info", None).
"""
from __future__ import annotations

import re

_PROGRESS_RE = re.compile(r"\d{1,3}%\|")
_BANNER_RE = re.compile(r"^(UNIT3Dup\b|https://itatorrents\.xyz|Unit3Dup\s+\d)")
_DECOR_RE = re.compile(r"^\s*(--\s*\*\*|={3,}|-{3,}|\*{3,})")
_TRACKER_ONLINE_RE = re.compile(r"Tracker\s*->\s*'([^']+)'\s+Online", re.I)
_TRACKER_DONE_RE = re.compile(r"Tracker\s*'([^']+)'\s+Done", re.I)
_UPLOAD_TARGET_RE = re.compile(r"^\s*\['[^']+'\]\s+\S+.*-\s*[\d.]+\s*[KMGT]?B", re.I)
_DISPLAY_NAME_RE = re.compile(r"'DISPLAYNAME'")
_RESPONSE_OK_RE = re.compile(r"\[RESPONSE\].*SUCCESSFUL", re.I)
_RESPONSE_FAIL_RE = re.compile(r"\[RESPONSE\].*(FAIL|ERROR)", re.I)
_TMDB_RE = re.compile(r"'(TMDB|IMDB|TVDB|TRAILER)\b")
_IMAGES_START_RE = re.compile(r"(Starting image upload|GENERATING IMAGES)", re.I)
_IMAGE_URL_RE = re.compile(r"https?://\S+\.(png|jpe?g|webp)", re.I)
_QBIT_SEND_RE = re.compile(r"QBITTORRENT client", re.I)
_ANALYZE_RE = re.compile(r"(Analyzing your media|Here is your files list)", re.I)
_TABLE_DECOR_RE = re.compile(r"^\s*(Torrent\s+Pack|No\s+movie\s+)")
_CONFIG_HINT_RE = re.compile(
    r"^\s*("
    r"\[Configuration\]|\[\*\.torrent|\[Images|\[Watcher\]|"
    r"New Torrent Configuration|New Options attribute|"
    r"->\s*Backup|->\s*Json file|Checking your configuration"
    r")",
    re.I,
)
_DONE_STEP_RE = re.compile(r"^\s*(\[\d{2}:\d{2}:\d{2}\]\s*)?Done\.\s*$", re.I)


def classify(line: str) -> tuple[str, str | None]:
    """Return (kind, event) for a single unit3dup output line.

    kind:  one of "info" | "ok" | "warn" | "error" | "debug"
    event: optional slug used by the UI to group adjacent entries
    """
    s = line.strip()
    if not s:
        return "debug", "decor"

    if _PROGRESS_RE.search(s):
        return "debug", "progress"
    if _BANNER_RE.search(s) or _DECOR_RE.match(s) or _TABLE_DECOR_RE.match(s):
        return "debug", "decor"

    if _RESPONSE_OK_RE.search(s):
        return "ok", "upload.done"
    if _RESPONSE_FAIL_RE.search(s):
        return "error", "upload.done"

    if _TRACKER_ONLINE_RE.search(s):
        return "ok", "tracker.online"
    if _TRACKER_DONE_RE.search(s):
        return "info", "upload.done"

    if _CONFIG_HINT_RE.match(s):
        return "info", "config"

    if _ANALYZE_RE.search(s):
        return "info", "analyze"

    if _TMDB_RE.search(s):
        return "info", "upload.tmdb"

    if _IMAGES_START_RE.search(s) or _IMAGE_URL_RE.search(s):
        return "info", "upload.images"

    if _DISPLAY_NAME_RE.search(s) or _UPLOAD_TARGET_RE.match(s):
        return "info", "upload.target"

    if _QBIT_SEND_RE.search(s):
        return "info", "upload.qbit"

    if _DONE_STEP_RE.match(s):
        return "info", "upload.step"

    return "info", None
