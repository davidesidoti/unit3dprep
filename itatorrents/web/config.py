"""Unit3Dbot.json read/write.

The web UI owns the lifecycle of the Unit3Dup config file so users can edit
every setting from the Settings panel. unit3dup itself reads the same file
when invoked for uploads.

Location precedence:
  1. $UNIT3DUP_CONFIG env var if set
  2. ~/Unit3Dup_config/Unit3Dbot.json (default used by unit3dup)

Writes are atomic (temp + rename) so unit3dup never sees a half-written file.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(
    os.environ.get(
        "UNIT3DUP_CONFIG",
        str(Path.home() / "Unit3Dup_config" / "Unit3Dbot.json"),
    )
)
_lock = threading.Lock()

DEFAULT_CONFIG: dict[str, Any] = {
    "ITT_URL": "https://itatorrents.xyz",
    "ITT_APIKEY": "",
    "ITT_PID": "",
    "PTT_URL": "https://polishtorrent.top/",
    "PTT_APIKEY": "no_key",
    "PTT_PID": "no_key",
    "SIS_URL": "https://no_tracker.xyz",
    "SIS_APIKEY": "no_key",
    "SIS_PID": "no_key",
    "MULTI_TRACKER": ["itt"],

    "TMDB_APIKEY": "",
    "TVDB_APIKEY": "",
    "YOUTUBE_KEY": "",
    "IGDB_CLIENT_ID": "no_key",
    "IGDB_ID_SECRET": "no_key",

    "TORRENT_CLIENT": "qbittorrent",
    "TAG": "ItaTorrentsBot",
    "QBIT_HOST": "127.0.0.1",
    "QBIT_PORT": "15491",
    "QBIT_USER": "admin",
    "QBIT_PASS": "",
    "SHARED_QBIT_PATH": "",
    "TRASM_HOST": "127.0.0.1",
    "TRASM_PORT": "9091",
    "TRASM_USER": "admin",
    "TRASM_PASS": "no_pass",
    "SHARED_TRASM_PATH": "no_path",
    "RTORR_HOST": "127.0.0.1",
    "RTORR_PORT": "9091",
    "RTORR_USER": "admin",
    "RTORR_PASS": "no_pass",
    "SHARED_RTORR_PATH": "no_path",

    "DUPLICATE_ON": True,
    "SKIP_DUPLICATE": False,
    "SKIP_TMDB": False,
    "SKIP_YOUTUBE": False,
    "ANON": False,
    "PERSONAL_RELEASE": False,
    "WEBP_ENABLED": False,
    "CACHE_SCR": False,
    "CACHE_DBONLINE": False,
    "RESIZE_SCSHOT": False,
    "YOUTUBE_CHANNEL_ENABLE": False,
    "NUMBER_OF_SCREENSHOTS": 4,
    "COMPRESS_SCSHOT": 3,
    "SIZE_TH": 2,
    "FAST_LOAD": 0,
    "YOUTUBE_FAV_CHANNEL_ID": "",
    "WATCHER_INTERVAL": 60,
    "TORRENT_COMMENT": "",
    "PREFERRED_LANG": "all",
    "RELEASER_SIGN": "",

    "PTSCREENS_KEY": "",
    "PASSIMA_KEY": "",
    "IMGBB_KEY": "",
    "IMGFI_KEY": "no_key",
    "FREE_IMAGE_KEY": "no_key",
    "LENSDUMP_KEY": "no_key",
    "IMARIDE_KEY": "",
    "IMAGE_HOST_ORDER": [
        "PTSCREENS", "PASSIMA", "IMGBB", "IMGFI",
        "FREE_IMAGE", "LENSDUMP", "IMARIDE",
    ],

    "TORRENT_ARCHIVE_PATH": "",
    "CACHE_PATH": "",
    "WATCHER_PATH": "",
    "WATCHER_DESTINATION_PATH": "",
    "FTPX_IP": "127.0.0.1",
    "FTPX_PORT": "2121",
    "FTPX_USER": "user",
    "FTPX_PASS": "pass",
    "FTPX_LOCAL_PATH": ".",
    "FTPX_ROOT": ".",
    "FTPX_KEEP_ALIVE": False,

    "TAG_ORDER_MOVIE": [
        "title", "year", "part", "version", "resolution", "uhd",
        "platform", "source", "remux", "multi", "acodec", "channels",
        "flag", "subtitle", "hdr", "vcodec", "video_encoder",
    ],
    "TAG_ORDER_SERIE": [
        "title", "year", "part", "version", "resolution", "uhd",
        "platform", "source", "remux", "multi", "acodec", "channels",
        "flag", "subtitle", "hdr", "vcodec", "video_encoder",
    ],

    "NORMAL_COLOR": "blue bold",
    "ERROR_COLOR": "red bold",
    "QUESTION_MESSAGE_COLOR": "yellow",
    "WELCOME_MESSAGE_COLOR": "blue",
    "WELCOME_MESSAGE_BORDER_COLOR": "yellow",
    "PANEL_MESSAGE_COLOR": "blue",
    "PANEL_MESSAGE_BORDER_COLOR": "yellow",
    "WELCOME_MESSAGE": "https://itatorrents.xyz",
}

MASKED_KEYS = {
    "ITT_APIKEY", "ITT_PID", "PTT_APIKEY", "PTT_PID", "SIS_APIKEY", "SIS_PID",
    "TMDB_APIKEY", "TVDB_APIKEY", "YOUTUBE_KEY",
    "IGDB_CLIENT_ID", "IGDB_ID_SECRET",
    "QBIT_PASS", "TRASM_PASS", "RTORR_PASS", "FTPX_PASS",
    "PTSCREENS_KEY", "PASSIMA_KEY", "IMGBB_KEY", "IMGFI_KEY",
    "FREE_IMAGE_KEY", "LENSDUMP_KEY", "IMARIDE_KEY",
}


def config_path() -> Path:
    return _CONFIG_PATH


def load() -> dict[str, Any]:
    with _lock:
        if not _CONFIG_PATH.exists():
            return dict(DEFAULT_CONFIG)
        try:
            with _CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save(cfg: dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(cfg, indent=2, ensure_ascii=False)
    with _lock:
        fd, tmp = tempfile.mkstemp(
            prefix="Unit3Dbot.", suffix=".tmp", dir=str(_CONFIG_PATH.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(serialized)
            os.replace(tmp, _CONFIG_PATH)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def mask_secrets(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with secret values replaced by a fixed marker when set."""
    masked: dict[str, Any] = {}
    for k, v in cfg.items():
        if k in MASKED_KEYS and v and v not in {"no_key", "no_pass"}:
            masked[k] = "__SET__"
        else:
            masked[k] = v
    return masked


def merge_secrets(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """When the client sends `__SET__` for a masked key it means 'leave unchanged'.
    Substitute the existing value so save() doesn't overwrite secrets with the marker.
    """
    out = dict(incoming)
    for k in MASKED_KEYS:
        if out.get(k) == "__SET__":
            out[k] = existing.get(k, "")
    return out


def env_readonly() -> dict[str, str]:
    """Expose ITA_* env vars that are *not* part of Unit3Dbot.json — displayed
    read-only in the Seeding Flow settings section so users see the actual
    values driving the web server + DB layer.
    """
    return {
        "ITA_HOST": os.environ.get("ITA_HOST", "127.0.0.1"),
        "ITA_PORT": os.environ.get("ITA_PORT", "8765"),
        "ITA_ROOT_PATH": os.environ.get("ITA_ROOT_PATH", ""),
        "ITA_TMDB_LANG": os.environ.get("ITA_TMDB_LANG", "it-IT"),
        "ITA_HTTPS_ONLY": os.environ.get("ITA_HTTPS_ONLY", "0"),
        "ITA_DB_PATH": os.environ.get(
            "ITA_DB_PATH", str(Path.home() / ".itatorrents_db.json")
        ),
        "ITA_TMDB_CACHE_PATH": os.environ.get(
            "ITA_TMDB_CACHE_PATH", str(Path.home() / ".itatorrents_tmdb_cache.json")
        ),
        "ITA_LANG_CACHE_PATH": os.environ.get(
            "ITA_LANG_CACHE_PATH", str(Path.home() / ".itatorrents_lang_cache.json")
        ),
        "ITA_MEDIA_ROOT": str(Path.home() / "media"),
        "ITA_SEEDINGS_DIR": str(Path.home() / "seedings"),
        "UNIT3DUP_CONFIG": str(_CONFIG_PATH),
    }
