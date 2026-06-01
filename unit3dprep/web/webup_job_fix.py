"""Workarounds for Unit3DwebUp 0.0.25 job-state bugs.

This module patches the Redis-backed Media record that webup builds in
its `/scan` step, BEFORE we invoke `/maketorrent` and `/upload`. We do
this because some webup logic mis-flags otherwise-uploadable media and
the upstream fix lives on the wrong branch / unreleased.

Currently it patches a single bug:

  Audio-language gate (`tags_service.py:281`) leaves `media.can_upload`
  permanently False if the FIRST audio track is not in the preferred
  language. The check runs inside the per-track loop and only ever
  flips the flag to False, never back to True — so a movie with [eng,
  ita] tracks fails the gate even when `PREFERRED_LANG=it`. We detect
  that case here (preferred language IS present in some track) and
  force `can_upload = True` back.

If/when webup ships a fix, this whole module can be removed.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import redis.asyncio as aioredis

log = logging.getLogger("unit3dprep.webup_job_fix")

# Webup hardcodes Redis on localhost:6379 — see CLAUDE.md.
_REDIS_URL = "redis://127.0.0.1:6379/0"

# Season/episode token as written by the bridge's `build_name`: S01, S01E01,
# S01E01-E12, S01E01-12, S01E01E12.
_SEASON_TOKEN = re.compile(r"S\d{2}(?:E\d{2}(?:-?E?\d{2})?)?", re.IGNORECASE)


def _season_label(*sources: str | None) -> str:
    """First S##(E##) token from any bridge-built name, upper-cased."""
    for src in sources:
        if not src:
            continue
        m = _SEASON_TOKEN.search(src)
        if m:
            return m.group(0).upper()
    return ""


def _languages_for_track(track: dict[str, Any]) -> set[str]:
    """All language codes mentioned by mediainfo for a single audio track."""
    out: set[str] = set()
    lang = track.get("language")
    if isinstance(lang, str) and lang:
        out.add(lang.strip().lower())
    others = track.get("other_language")
    if isinstance(others, (list, tuple)):
        for v in others:
            if isinstance(v, str) and v.strip():
                out.add(v.strip().lower())
    return out


def _all_audio_languages(media: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    mediafile = media.get("mediafile") or {}
    tracks = mediafile.get("audio_tracks") or []
    if not isinstance(tracks, list):
        return out
    for t in tracks:
        if isinstance(t, dict):
            out |= _languages_for_track(t)
    return out


def _preferred_present(preferred: str, langs: set[str]) -> bool:
    """Is `preferred` (e.g. 'it') matched by any code in `langs`?

    Mediainfo emits 2-letter ('it') and 3-letter ('ita') codes plus
    plain-text names ('Italian'). We do a case-insensitive substring
    match in either direction so 'it' matches 'ita', 'italian',
    'italiano' — without false positives across unrelated codes
    (we require an exact start-with).
    """
    p = (preferred or "").strip().lower()
    if not p:
        return False
    for code in langs:
        if code == p:
            return True
        if code.startswith(p) or p.startswith(code):
            return True
    return False


async def maybe_force_can_upload(job_id: str, preferred_lang: str) -> dict[str, Any]:
    """If webup wrongly set `can_upload=False`, force it back to True.

    Returns a small dict describing what happened — useful for logs:
    ``{"patched": bool, "reason": str, "preferred": str,
       "languages": [list]}``.

    Never raises: on any failure returns ``{"patched": False,
    "reason": "<error>"}`` so the caller can keep the upload flow
    going.
    """
    pref = (preferred_lang or "").strip().lower()
    result: dict[str, Any] = {
        "patched": False,
        "preferred": pref,
        "languages": [],
        "reason": "",
    }
    if not pref:
        result["reason"] = "no preferred lang set"
        return result
    try:
        client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    except Exception as e:
        result["reason"] = f"redis connect failed: {e!r}"
        return result
    try:
        try:
            raw = await client.hget(job_id, "data")
        except Exception as e:
            result["reason"] = f"redis hget failed: {e!r}"
            return result
        if not raw:
            result["reason"] = "no job data in redis"
            return result
        try:
            data = json.loads(raw)
        except Exception as e:
            result["reason"] = f"json parse failed: {e!r}"
            return result
        if data.get("can_upload"):
            result["reason"] = "can_upload already true"
            return result
        langs = sorted(_all_audio_languages(data))
        result["languages"] = langs
        if not _preferred_present(pref, set(langs)):
            result["reason"] = f"preferred '{pref}' not in audio tracks"
            return result
        data["can_upload"] = True
        try:
            await client.hset(job_id, mapping={"data": json.dumps(data)})
        except Exception as e:
            result["reason"] = f"redis hset failed: {e!r}"
            return result
        result["patched"] = True
        result["reason"] = (
            f"forced can_upload=true (preferred '{pref}' present in audio tracks {langs})"
        )
        return result
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def maybe_inject_season(job_id: str) -> dict[str, Any]:
    """Ensure webup's tracker ``display_name`` carries the season label.

    Webup builds ``display_name`` from ``PREFS__TAG_POSITION_SERIE`` but reads
    that setting from a module-global ``settings`` captured at import time
    (``media.py`` / ``tags_service.py``), so a corrected tag order in the
    ``.env`` only takes effect after a webup *restart*. To make the season
    appear without restarting webup, patch the Redis job's ``display_name``
    directly: take the ``S##(E##)`` token from the bridge-built folder/torrent
    name and insert it right after the title.

    Series only. Idempotent: skips if the label is already present. Never
    raises — returns ``{"patched": bool, "reason": str, "display_name": str}``.
    """
    result: dict[str, Any] = {"patched": False, "reason": "", "display_name": ""}
    try:
        client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    except Exception as e:
        result["reason"] = f"redis connect failed: {e!r}"
        return result
    try:
        try:
            raw = await client.hget(job_id, "data")
        except Exception as e:
            result["reason"] = f"redis hget failed: {e!r}"
            return result
        if not raw:
            result["reason"] = "no job data in redis"
            return result
        try:
            data = json.loads(raw)
        except Exception as e:
            result["reason"] = f"json parse failed: {e!r}"
            return result
        if data.get("category") != "series":
            result["reason"] = "not a series"
            return result
        display = (data.get("display_name") or "").strip()
        if not display:
            result["reason"] = "no display_name"
            return result
        label = _season_label(
            data.get("torrent_name"), data.get("title"), data.get("title_sanitized")
        )
        if not label:
            result["reason"] = "no season token in source name"
            return result
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])", display, re.IGNORECASE):
            result["reason"] = f"season '{label}' already present"
            return result
        guess_title = (data.get("guess_title") or "").strip()
        if guess_title and guess_title in display:
            new_display = display.replace(guess_title, f"{guess_title} {label}", 1)
        else:
            new_display = f"{label} {display}"
        data["display_name"] = new_display
        try:
            await client.hset(job_id, mapping={"data": json.dumps(data)})
        except Exception as e:
            result["reason"] = f"redis hset failed: {e!r}"
            return result
        result["patched"] = True
        result["display_name"] = new_display
        result["reason"] = f"inserted season '{label}' into display_name"
        return result
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
