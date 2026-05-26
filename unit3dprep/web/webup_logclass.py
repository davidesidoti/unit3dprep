"""Classify WebSocket messages from Unit3DWebUp /ws into (kind, event) pairs.

Replaces the regex-on-stdout classifier (`logclass.py`) used for the unit3dup
CLI. Webup messages are already structured: `{type, level, message, job_id?}`.
We map level → log kind and the message text to a stable event slug used by
log filters/UI.
"""
from __future__ import annotations

import re
from typing import Any


_LEVEL_TO_KIND = {
    "success": "ok",
    "ok": "ok",
    "info": "info",
    "warn": "warn",
    "warning": "warn",
    "error": "error",
    "debug": "debug",
}

_RX_TORRENT_CREATED = re.compile(r"torrent.*(created|file exists)", re.I)
_RX_UPLOAD_OK = re.compile(r"\b(uploaded|successful|success)\b", re.I)
# Match: explicit fail words OR Laravel-style validation error dicts that
# webup forwards verbatim (e.g. "{'episode_number': ['The episode number
# field is required.']}").
_RX_UPLOAD_FAIL = re.compile(
    r"\b(fail|failure|error|exception|denied|invalid|required|rejected)\b",
    re.I,
)
_RX_SEED_OK = re.compile(r"added to (qbittorrent|transmission|rtorrent)", re.I)
_RX_SEED_FAIL = re.compile(r"(login failed|file not found)", re.I)
_RX_SCAN_DONE = re.compile(r"scan completato|scan complete|scan done", re.I)
_RX_TRACKER_ONLINE = re.compile(r"tracker.*online", re.I)
_RX_QBIT = re.compile(r"qbittorrent|qbit\b", re.I)
_RX_IMAGES = re.compile(r"(screenshot|image host|imgbb|passima|ptscreens)", re.I)
_RX_TMDB = re.compile(r"\b(tmdb|tvdb|imdb)\b", re.I)


def kind_for_level(level: str | None) -> str:
    return _LEVEL_TO_KIND.get((level or "info").lower(), "info")


def classify_msg(msg: dict[str, Any]) -> tuple[str, str | None, str]:
    """
    Returns (kind, event, text) for a webup WS message.

    - kind: 'info'|'ok'|'warn'|'error'|'debug' for the log buffer.
    - event: stable slug like 'upload.done', 'upload.maketorrent', 'scan.done', or None.
    - text: the message string (already concatenated; use as the log line).
    """
    mtype = (msg.get("type") or "").lower()
    level = msg.get("level")
    text = str(msg.get("message") or "")
    kind = kind_for_level(level)

    if mtype == "posterlogmessage":
        if _RX_UPLOAD_OK.search(text):
            return ("ok", "upload.done", text)
        if _RX_UPLOAD_FAIL.search(text):
            return ("error", "upload.done", text)
        if _RX_TORRENT_CREATED.search(text):
            return (kind, "upload.maketorrent", text)
        if _RX_SEED_OK.search(text):
            return ("ok", "upload.qbit", text)
        if _RX_SEED_FAIL.search(text):
            return ("error", "upload.qbit", text)
        return (kind, "upload.target", text)

    if mtype == "log":
        if _RX_SCAN_DONE.search(text):
            return ("ok", "scan.done", text)
        if _RX_TRACKER_ONLINE.search(text):
            return ("ok", "tracker.online", text)
        if _RX_QBIT.search(text):
            return (kind, "upload.qbit", text)
        if _RX_IMAGES.search(text):
            return (kind, "upload.images", text)
        if _RX_TMDB.search(text):
            return (kind, "upload.tmdb", text)
        return (kind, None, text)

    return (kind, None, text)


def is_terminal_success(msg: dict[str, Any]) -> bool:
    """True if this message indicates the upload succeeded for its job_id."""
    if (msg.get("type") or "").lower() != "posterlogmessage":
        return False
    text = str(msg.get("message") or "")
    return bool(_RX_UPLOAD_OK.search(text))


def is_terminal_failure(msg: dict[str, Any]) -> bool:
    if (msg.get("level") or "").lower() == "error":
        return True
    if (msg.get("type") or "").lower() == "posterlogmessage":
        text = str(msg.get("message") or "")
        # "None" (string) means tracker rejected with no 'data' field returned
        # by itt_tracker_service (response.get('data', None) when Unit3D API
        # returns {'message':..., 'errors':{...}} without a 'data' key).
        if not text or text == "None":
            return True
        return bool(_RX_UPLOAD_FAIL.search(text))
    return False
