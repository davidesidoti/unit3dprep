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

from ._env import env as _env_get

_CONFIG_PATH = Path(
    os.environ.get(
        "UNIT3DUP_CONFIG",
        str(Path.home() / "Unit3Dup_config" / "Unit3Dbot.json"),
    )
)
_lock = threading.Lock()

# Map legacy ITA_* config keys to new U3DP_* keys for one-way upgrade on load.
_LEGACY_KEY_MAP = {
    "ITA_MEDIA_ROOT": "U3DP_MEDIA_ROOT",
    "ITA_SEEDINGS_DIR": "U3DP_SEEDINGS_DIR",
    "ITA_DB_PATH": "U3DP_DB_PATH",
    "ITA_TMDB_CACHE_PATH": "U3DP_TMDB_CACHE_PATH",
    "ITA_LANG_CACHE_PATH": "U3DP_LANG_CACHE_PATH",
    "ITA_ROOT_PATH": "U3DP_ROOT_PATH",
    "ITA_TMDB_LANG": "U3DP_TMDB_LANG",
    "ITA_HOST": "U3DP_HOST",
    "ITA_PORT": "U3DP_PORT",
    "ITA_HTTPS_ONLY": "U3DP_HTTPS_ONLY",
    "ITA_SYSTEMD_UNIT": "U3DP_SYSTEMD_UNIT",
}

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

    # Seeding Flow — runtime settings (can be overridden by U3DP_* env vars).
    # Empty string means "fall back to default resolved in runtime_setting()".
    "U3DP_MEDIA_ROOT": "",
    "U3DP_SEEDINGS_DIR": "",
    "U3DP_DB_PATH": "",
    "U3DP_TMDB_CACHE_PATH": "",
    "U3DP_LANG_CACHE_PATH": "",
    "U3DP_ROOT_PATH": "",
    "U3DP_TMDB_LANG": "it-IT",
    "U3DP_HOST": "127.0.0.1",
    "U3DP_PORT": "8765",
    "U3DP_HTTPS_ONLY": False,
    "U3DP_SYSTEMD_UNIT": "",

    # Wizard Defaults — control default UI behaviour of the upload wizard.
    "W_AUDIO_CHECK": True,
    "W_AUTO_TMDB": True,
    "W_HIDE_UPLOADED": True,
    "W_HIDE_NO_ITALIAN": False,
    "W_HARDLINK_ONLY": False,
    "W_CONFIRM_NAMES": True,
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


def _upgrade_legacy_keys(data: dict[str, Any]) -> dict[str, Any]:
    for old, new in _LEGACY_KEY_MAP.items():
        if old in data and new not in data:
            data[new] = data.pop(old)
        elif old in data:
            data.pop(old)
    return data


def load() -> dict[str, Any]:
    with _lock:
        if not _CONFIG_PATH.exists():
            return dict(DEFAULT_CONFIG)
        try:
            with _CONFIG_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
    data = _upgrade_legacy_keys(data)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save(cfg: dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = _upgrade_legacy_keys(dict(cfg))
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


# ---------------------------------------------------------------------------
# Runtime settings — resolve from env first, then Unit3Dbot.json, then default.
# ---------------------------------------------------------------------------

_RUNTIME_DEFAULTS: dict[str, str] = {
    "U3DP_MEDIA_ROOT": str(Path.home() / "media"),
    "U3DP_SEEDINGS_DIR": str(Path.home() / "seedings"),
    "U3DP_DB_PATH": str(Path.home() / ".unit3dprep_db.json"),
    "U3DP_TMDB_CACHE_PATH": str(Path.home() / ".unit3dprep_tmdb_cache.json"),
    "U3DP_LANG_CACHE_PATH": str(Path.home() / ".unit3dprep_lang_cache.json"),
    "U3DP_ROOT_PATH": "",
    "U3DP_TMDB_LANG": "it-IT",
    "U3DP_HOST": "127.0.0.1",
    "U3DP_PORT": "8765",
    "U3DP_HTTPS_ONLY": "0",
    "U3DP_SYSTEMD_UNIT": "unit3dprep-web.service",
}


def _legacy_env_key(key: str) -> str | None:
    for legacy, new in _LEGACY_KEY_MAP.items():
        if new == key:
            return legacy
    return None


def runtime_setting(key: str, default: str | None = None) -> str:
    """Resolve a U3DP_* runtime setting. Precedence: env var (new → legacy ITA_*) → Unit3Dbot.json → default.

    Called on every access so settings saved through the web UI take effect
    without restarting the server.
    """
    env_val = _env_get(key, _legacy_env_key(key))
    if env_val is not None and env_val != "":
        return env_val
    cfg = load()
    cfg_val = cfg.get(key, "")
    if isinstance(cfg_val, bool):
        cfg_val = "1" if cfg_val else "0"
    if cfg_val:
        return str(cfg_val)
    if default is not None:
        return default
    return _RUNTIME_DEFAULTS.get(key, "")


def env_runtime() -> dict[str, str]:
    """Effective values shown in the Seeding Flow settings section.

    These combine env + config so users see what the running server is actually
    using. `UNIT3DUP_CONFIG` is install-time only.
    """
    return {
        "U3DP_HOST": runtime_setting("U3DP_HOST"),
        "U3DP_PORT": runtime_setting("U3DP_PORT"),
        "U3DP_ROOT_PATH": runtime_setting("U3DP_ROOT_PATH"),
        "U3DP_TMDB_LANG": runtime_setting("U3DP_TMDB_LANG"),
        "U3DP_HTTPS_ONLY": runtime_setting("U3DP_HTTPS_ONLY"),
        "U3DP_DB_PATH": runtime_setting("U3DP_DB_PATH"),
        "U3DP_TMDB_CACHE_PATH": runtime_setting("U3DP_TMDB_CACHE_PATH"),
        "U3DP_LANG_CACHE_PATH": runtime_setting("U3DP_LANG_CACHE_PATH"),
        "U3DP_MEDIA_ROOT": runtime_setting("U3DP_MEDIA_ROOT"),
        "U3DP_SEEDINGS_DIR": runtime_setting("U3DP_SEEDINGS_DIR"),
        "U3DP_SYSTEMD_UNIT": runtime_setting("U3DP_SYSTEMD_UNIT"),
        "UNIT3DUP_CONFIG": str(_CONFIG_PATH),
    }


env_readonly = env_runtime
