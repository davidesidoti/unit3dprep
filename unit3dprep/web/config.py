"""unit3dprep config storage — single .env file shared with Unit3DWebUp 0.0.20+.

Path resolution for the .env file:
  1. $U3DP_ENV_PATH (full file path, explicit override for unit3dprep)
  2. $ENVPATH (directory, à la Unit3DWebUp; file = $ENVPATH/.env)
  3. ~/.config/unit3dprep/.env (default, XDG-style)

On disk, keys understood by Unit3DWebUp are written with their canonical
``TRACKER__*`` / ``TORRENT__*`` / ``PREFS__*`` names so the same file can be
loaded by ``unit3dwup`` at startup. In Python and in the ``/api/settings``
payload we keep the short historical names (``ITT_APIKEY``, ``QBIT_HOST``…) —
translation is confined to this module.

Migration: at first ``load()`` the legacy ``Unit3Dbot.json`` (default
``~/Unit3Dup_config/Unit3Dbot.json``, override via ``$UNIT3DUP_CONFIG``) is
read once and re-written as the new ``.env``. The original is renamed to
``Unit3Dbot.json.migrated-bak`` (never deleted by us).

Writes are atomic (tempfile + rename) so neither unit3dprep nor webup
ever sees a half-written file.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from ._env import env as _env_get

log = logging.getLogger("unit3dprep.config")

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_DEFAULT_ENV_PATH = Path.home() / ".config" / "unit3dprep" / ".env"
_LEGACY_JSON_DEFAULT = Path.home() / "Unit3Dup_config" / "Unit3Dbot.json"

_lock = threading.Lock()


def _resolve_env_path() -> Path:
    explicit = os.environ.get("U3DP_ENV_PATH")
    if explicit:
        return Path(explicit).expanduser()
    envpath = os.environ.get("ENVPATH")
    if envpath:
        return Path(envpath).expanduser() / ".env"
    return _DEFAULT_ENV_PATH


def _legacy_json_path() -> Path:
    return Path(
        os.environ.get("UNIT3DUP_CONFIG", str(_LEGACY_JSON_DEFAULT))
    ).expanduser()


def config_path() -> Path:
    """Path to the unified .env (replaces the old Unit3Dbot.json path)."""
    return _resolve_env_path()


def webup_envpath_dir() -> Path:
    """Directory to pass as ``ENVPATH=`` when launching Unit3DWebUp."""
    return _resolve_env_path().parent


# ---------------------------------------------------------------------------
# Legacy key upgrade (ITA_* → U3DP_*)
# ---------------------------------------------------------------------------

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


def _upgrade_legacy_keys(data: dict[str, Any]) -> dict[str, Any]:
    for old, new in _LEGACY_KEY_MAP.items():
        if old in data and new not in data:
            data[new] = data.pop(old)
        elif old in data:
            data.pop(old)
    return _ensure_season_in_serie(data)


def _ensure_season_in_serie(data: dict[str, Any]) -> dict[str, Any]:
    """Guarantee ``"season"`` is present in TAG_ORDER_SERIE.

    Webup stores the ``S<NN>(E<NN>)`` label under the ``season`` tag key and,
    when building the tracker name, only emits tag keys that appear in
    ``PREFS__TAG_POSITION_SERIE``. A series tag order missing ``season`` thus
    silently drops the season/episode number from the uploaded name even
    though guessit parsed it correctly. Heal configs written before
    ``season`` was added to the default so existing installs recover on the
    next load/save (and the corrected order is then pushed to webup).
    """
    order = data.get("TAG_ORDER_SERIE")
    if isinstance(order, list) and "season" not in order:
        healed = list(order)
        if "year" in healed:
            idx = healed.index("year") + 1
        elif "title" in healed:
            idx = healed.index("title") + 1
        else:
            idx = 0
        healed.insert(idx, "season")
        data["TAG_ORDER_SERIE"] = healed
    return data


# ---------------------------------------------------------------------------
# Defaults & masking
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "ITT_URL": "https://itatorrents.xyz",
    "ITT_APIKEY": "",
    "ITT_PID": "",
    "PTT_URL": "https://polishtorrent.top",
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
    # Webup `tags_service.mediainfo_audio` blocks upload (`can_upload=False`)
    # when PREFERRED_LANG is not present among the audio tracks. Webup 0.0.25
    # expects ISO 639-1 codes ("it"), not ISO 639-2 ("ita"); mediainfo's
    # `language` field on each audio track is the 2-letter code, so anything
    # else silently fails the match and the upload is dropped without logging.
    # ItaTorrents is an Italian tracker; "it" is the right pre-flight default.
    "PREFERRED_LANG": "it",
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
        "title", "year", "season", "part", "version", "resolution", "uhd",
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

    # Seeding Flow — runtime settings (overridable by U3DP_* env vars).
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
    "U3DP_LANG": "it",
    "U3DP_DRY_RUN_TRACKER": "0",

    # Wizard Defaults — control default UI behaviour of the upload wizard.
    "W_AUDIO_CHECK": True,
    "W_AUTO_TMDB": True,
    "W_HIDE_UPLOADED": True,
    "W_HIDE_NO_ITALIAN": False,
    "W_HARDLINK_ONLY": False,
    "W_CONFIRM_NAMES": True,
    "W_DUPLICATE_CHECK": True,
}

MASKED_KEYS = {
    "ITT_APIKEY", "ITT_PID", "PTT_APIKEY", "PTT_PID", "SIS_APIKEY", "SIS_PID",
    "TMDB_APIKEY", "TVDB_APIKEY", "YOUTUBE_KEY",
    "IGDB_CLIENT_ID", "IGDB_ID_SECRET",
    "QBIT_PASS", "TRASM_PASS", "RTORR_PASS", "FTPX_PASS",
    "PTSCREENS_KEY", "PASSIMA_KEY", "IMGBB_KEY", "IMGFI_KEY",
    "FREE_IMAGE_KEY", "LENSDUMP_KEY", "IMARIDE_KEY",
}


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
    """When the client sends ``__SET__`` for a masked key it means 'leave unchanged'.

    Substitute the existing value so save() doesn't overwrite secrets with the marker.
    """
    out = dict(incoming)
    for k in MASKED_KEYS:
        if out.get(k) == "__SET__":
            out[k] = existing.get(k, "")
    return out


# ---------------------------------------------------------------------------
# Webup canonical naming (TRACKER__/TORRENT__/PREFS__) ↔ short historical names
# ---------------------------------------------------------------------------

WEBUP_KEY_MAP: dict[str, str] = {
    # Trackers
    "ITT_URL": "TRACKER__ITT_URL",
    "ITT_APIKEY": "TRACKER__ITT_APIKEY",
    "ITT_PID": "TRACKER__ITT_PID",
    "SIS_URL": "TRACKER__SIS_URL",
    "SIS_APIKEY": "TRACKER__SIS_APIKEY",
    "SIS_PID": "TRACKER__SIS_PID",
    "MULTI_TRACKER": "TRACKER__MULTI_TRACKER",
    # Metadata API
    "TMDB_APIKEY": "TRACKER__TMDB_APIKEY",
    "TVDB_APIKEY": "TRACKER__TVDB_APIKEY",
    "YOUTUBE_KEY": "TRACKER__YOUTUBE_KEY",
    "IGDB_CLIENT_ID": "TRACKER__IGDB_CLIENT_ID",
    "IGDB_ID_SECRET": "TRACKER__IGDB_ID_SECRET",
    # Image hosts
    "IMGBB_KEY": "TRACKER__IMGBB_KEY",
    "IMGFI_KEY": "TRACKER__IMGFI_KEY",
    "PTSCREENS_KEY": "TRACKER__PTSCREENS_KEY",
    "PASSIMA_KEY": "TRACKER__PASSIMA_KEY",
    "LENSDUMP_KEY": "TRACKER__LENSDUMP_KEY",
    "FREE_IMAGE_KEY": "TRACKER__FREE_IMAGE_KEY",
    "IMARIDE_KEY": "TRACKER__IMARIDE_KEY",
    # Torrent client
    "TORRENT_CLIENT": "TORRENT__TORRENT_CLIENT",
    "TAG": "TORRENT__TAG",
    "QBIT_HOST": "TORRENT__QBIT_HOST",
    "QBIT_PORT": "TORRENT__QBIT_PORT",
    "QBIT_USER": "TORRENT__QBIT_USER",
    "QBIT_PASS": "TORRENT__QBIT_PASS",
    "SHARED_QBIT_PATH": "TORRENT__SHARED_QBIT_PATH",
    "TRASM_HOST": "TORRENT__TRASM_HOST",
    "TRASM_PORT": "TORRENT__TRASM_PORT",
    "TRASM_USER": "TORRENT__TRASM_USER",
    "TRASM_PASS": "TORRENT__TRASM_PASS",
    "SHARED_TRASM_PATH": "TORRENT__SHARED_TRASM_PATH",
    "RTORR_HOST": "TORRENT__RTORR_HOST",
    "RTORR_PORT": "TORRENT__RTORR_PORT",
    "RTORR_USER": "TORRENT__RTORR_USER",
    "RTORR_PASS": "TORRENT__RTORR_PASS",
    "SHARED_RTORR_PATH": "TORRENT__SHARED_RTORR_PATH",
    # Behaviour flags
    "ANON": "PREFS__ANON",
    "PERSONAL_RELEASE": "PREFS__PERSONAL_RELEASE",
    "DUPLICATE_ON": "PREFS__DUPLICATE_ON",
    "SKIP_DUPLICATE": "PREFS__SKIP_DUPLICATE",
    "SKIP_YOUTUBE": "PREFS__SKIP_YOUTUBE",
    "WEBP_ENABLED": "PREFS__WEBP_ENABLED",
    "YOUTUBE_CHANNEL_ENABLE": "PREFS__YOUTUBE_CHANNEL_ENABLE",
    # Numbers
    "NUMBER_OF_SCREENSHOTS": "PREFS__NUMBER_OF_SCREENSHOTS",
    "COMPRESS_SCSHOT": "PREFS__COMPRESS_SCSHOT",
    "SIZE_TH": "PREFS__SIZE_TH",
    "FAST_LOAD": "PREFS__FAST_LOAD",
    "WATCHER_INTERVAL": "PREFS__WATCHER_INTERVAL",
    # Paths
    "TORRENT_ARCHIVE_PATH": "PREFS__TORRENT_ARCHIVE_PATH",
    "WATCHER_PATH": "PREFS__WATCHER_PATH",
    "WATCHER_DESTINATION_PATH": "PREFS__WATCHER_DESTINATION_PATH",
    # Misc
    "RELEASER_SIGN": "PREFS__RELEASER_SIGN",
    "TORRENT_COMMENT": "PREFS__TORRENT_COMMENT",
    "PREFERRED_LANG": "PREFS__PREFERRED_LANG",
    # Tag ordering — local TAG_ORDER_* ↔ webup PREFS__TAG_POSITION_*
    "TAG_ORDER_MOVIE": "PREFS__TAG_POSITION_MOVIE",
    "TAG_ORDER_SERIE": "PREFS__TAG_POSITION_SERIE",
}

_WEBUP_TO_SHORT: dict[str, str] = {v: k for k, v in WEBUP_KEY_MAP.items()}

# Image-host priority keys are written for webup but never read back:
# IMAGE_HOST_ORDER (a list) is the authoritative source for the order.
_IMAGE_HOSTS = (
    "PTSCREENS", "PASSIMA", "IMGBB", "IMGFI",
    "FREE_IMAGE", "LENSDUMP", "IMARIDE",
)
_PRIORITY_KEYS = {f"PREFS__{h}_PRIORITY" for h in _IMAGE_HOSTS}

# Webup's get_settings() does Path(settings.prefs.TORRENT_ARCHIVE_PATH) and
# Path.exists() at startup. If the value is None or empty webup raises
# SystemExit(1) and lru_caches the failure — meaning every following request
# returns 500. Our config uses "" as "unset"; on disk we must materialize
# something webup can call Path() on. "." (the bot's CWD) is the same
# fallback the upstream .env(example) ships with.
_WEBUP_REQUIRED_PATH_KEYS = {
    "TORRENT_ARCHIVE_PATH",
    "WATCHER_PATH",
    "WATCHER_DESTINATION_PATH",
}


def _stringify_value(v: Any) -> str | None:
    """Env-string form for a webup-mapped value, or ``None`` to skip pushing.

    Webup's pydantic ``empty_to_none`` validator converts empty strings to
    ``None`` and then crashes ``Settings()`` rebuild for required ``str``
    fields. We skip empty / ``no_key`` / ``no_pass`` / ``no_path`` /
    ``no_comment`` sentinels so webup keeps its own defaults.

    Lists are JSON-serialized — pydantic-settings v2 calls ``json.loads``
    on env-var values for ``list[str]`` fields rebuilt from ``os.environ``.
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        items = [str(x).strip() for x in v if str(x).strip()]
        return json.dumps(items) if items else None
    s = str(v)
    if not s.strip():
        return None
    if s in {"no_key", "no_pass", "no_path", "no_comment"}:
        return None
    return s


def _stringify_value_passthrough(v: Any) -> str:
    """Env-string form for local-only keys — always emit, even if empty."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return json.dumps(list(v))
    return str(v)


def _image_host_priorities(order: list[str]) -> dict[str, str]:
    """Project IMAGE_HOST_ORDER list → individual ``PREFS__<HOST>_PRIORITY``.

    Webup picks image hosts by numeric priority (lower = tried first). Hosts
    not in the list go to the back (priority 99) so empty-key hosts (notably
    Lensdump, default 0) don't get tried first.
    """
    out: dict[str, str] = {}
    known = set(_IMAGE_HOSTS)
    for i, host in enumerate(order):
        h = str(host).strip().upper()
        if h in known:
            out[f"PREFS__{h}_PRIORITY"] = str(i)
    for h in known:
        key = f"PREFS__{h}_PRIORITY"
        if key not in out:
            out[key] = "99"
    return out


# ---------------------------------------------------------------------------
# .env parser / dumper
# ---------------------------------------------------------------------------

_KV_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_NEEDS_QUOTE_RE = re.compile(r"[\s#'\"]|^$")


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _KV_RE.match(line)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            inner = v[1:-1]
            if v[0] == '"':
                inner = inner.replace('\\"', '"').replace("\\\\", "\\")
            v = inner
        out[k] = v
    return out


def _quote_value(v: str) -> str:
    if v == "":
        return '""'
    if not _NEEDS_QUOTE_RE.search(v):
        return v
    # Prefer single quotes when the value contains double quotes (e.g. JSON
    # arrays) so we avoid backslash-escaping and keep the .env human-readable.
    # python-dotenv (used by pydantic-settings v2) takes single-quoted values
    # literally without escape processing — perfect for JSON.
    if '"' in v and "'" not in v:
        return f"'{v}'"
    escaped = v.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_GROUPS: list[tuple[str, list[str]]] = [
    ("Trackers", [
        "TRACKER__ITT_URL", "TRACKER__ITT_APIKEY", "TRACKER__ITT_PID",
        "TRACKER__SIS_URL", "TRACKER__SIS_APIKEY", "TRACKER__SIS_PID",
        "TRACKER__MULTI_TRACKER",
        "PTT_URL", "PTT_APIKEY", "PTT_PID",
    ]),
    ("Metadata API", [
        "TRACKER__TMDB_APIKEY", "TRACKER__TVDB_APIKEY", "TRACKER__YOUTUBE_KEY",
        "TRACKER__IGDB_CLIENT_ID", "TRACKER__IGDB_ID_SECRET",
    ]),
    ("Image hosts", [
        "TRACKER__PTSCREENS_KEY", "TRACKER__PASSIMA_KEY", "TRACKER__IMGBB_KEY",
        "TRACKER__IMGFI_KEY", "TRACKER__FREE_IMAGE_KEY", "TRACKER__LENSDUMP_KEY",
        "TRACKER__IMARIDE_KEY",
        "IMAGE_HOST_ORDER",
        "PREFS__PTSCREENS_PRIORITY", "PREFS__PASSIMA_PRIORITY", "PREFS__IMGBB_PRIORITY",
        "PREFS__IMGFI_PRIORITY", "PREFS__FREE_IMAGE_PRIORITY", "PREFS__LENSDUMP_PRIORITY",
        "PREFS__IMARIDE_PRIORITY",
    ]),
    ("Torrent client", [
        "TORRENT__TORRENT_CLIENT", "TORRENT__TAG",
        "TORRENT__QBIT_HOST", "TORRENT__QBIT_PORT", "TORRENT__QBIT_USER",
        "TORRENT__QBIT_PASS", "TORRENT__SHARED_QBIT_PATH",
        "TORRENT__TRASM_HOST", "TORRENT__TRASM_PORT", "TORRENT__TRASM_USER",
        "TORRENT__TRASM_PASS", "TORRENT__SHARED_TRASM_PATH",
        "TORRENT__RTORR_HOST", "TORRENT__RTORR_PORT", "TORRENT__RTORR_USER",
        "TORRENT__RTORR_PASS", "TORRENT__SHARED_RTORR_PATH",
    ]),
    ("Behavior", [
        "PREFS__ANON", "PREFS__PERSONAL_RELEASE",
        "PREFS__DUPLICATE_ON", "PREFS__SKIP_DUPLICATE", "PREFS__SKIP_YOUTUBE",
        "PREFS__WEBP_ENABLED", "PREFS__YOUTUBE_CHANNEL_ENABLE",
        "PREFS__NUMBER_OF_SCREENSHOTS", "PREFS__COMPRESS_SCSHOT",
        "PREFS__SIZE_TH", "PREFS__FAST_LOAD", "PREFS__WATCHER_INTERVAL",
        "PREFS__RELEASER_SIGN", "PREFS__TORRENT_COMMENT", "PREFS__PREFERRED_LANG",
        "PREFS__TAG_POSITION_MOVIE", "PREFS__TAG_POSITION_SERIE",
        "SKIP_TMDB", "CACHE_SCR", "CACHE_DBONLINE", "RESIZE_SCSHOT",
        "YOUTUBE_FAV_CHANNEL_ID",
    ]),
    ("Paths", [
        "PREFS__TORRENT_ARCHIVE_PATH", "PREFS__WATCHER_PATH",
        "PREFS__WATCHER_DESTINATION_PATH",
        "CACHE_PATH",
        "FTPX_IP", "FTPX_PORT", "FTPX_USER", "FTPX_PASS",
        "FTPX_LOCAL_PATH", "FTPX_ROOT", "FTPX_KEEP_ALIVE",
    ]),
    ("Console (legacy unit3dup)", [
        "NORMAL_COLOR", "ERROR_COLOR", "QUESTION_MESSAGE_COLOR",
        "WELCOME_MESSAGE_COLOR", "WELCOME_MESSAGE_BORDER_COLOR",
        "PANEL_MESSAGE_COLOR", "PANEL_MESSAGE_BORDER_COLOR",
        "WELCOME_MESSAGE",
    ]),
    ("Runtime (unit3dprep)", [
        "U3DP_HOST", "U3DP_PORT", "U3DP_HTTPS_ONLY", "U3DP_ROOT_PATH",
        "U3DP_LANG", "U3DP_TMDB_LANG",
        "U3DP_MEDIA_ROOT", "U3DP_SEEDINGS_DIR",
        "U3DP_DB_PATH", "U3DP_TMDB_CACHE_PATH", "U3DP_LANG_CACHE_PATH",
        "U3DP_SYSTEMD_UNIT", "U3DP_DRY_RUN_TRACKER",
    ]),
    ("Wizard defaults (unit3dprep)", [
        "W_AUDIO_CHECK", "W_AUTO_TMDB", "W_HIDE_UPLOADED",
        "W_HIDE_NO_ITALIAN", "W_HARDLINK_ONLY", "W_CONFIRM_NAMES",
        "W_DUPLICATE_CHECK",
    ]),
]


def _dump_env_file(items: dict[str, str]) -> str:
    seen: set[str] = set()
    lines: list[str] = ["# Generated by unit3dprep — shared with Unit3DWebUp."]
    for header, keys in _GROUPS:
        section_lines: list[str] = []
        for k in keys:
            if k not in items:
                continue
            section_lines.append(f"{k}={_quote_value(items[k])}")
            seen.add(k)
        if section_lines:
            lines.append("")
            lines.append(f"# {header}")
            lines.extend(section_lines)
    extras = sorted(set(items) - seen)
    if extras:
        lines.append("")
        lines.append("# Other")
        for k in extras:
            lines.append(f"{k}={_quote_value(items[k])}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Canonical (on-disk) ↔ short (in-memory) translation
# ---------------------------------------------------------------------------

def _coerce_value(default_val: Any, raw: str) -> Any:
    if isinstance(default_val, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default_val, int) and not isinstance(default_val, bool):
        try:
            return int(raw)
        except ValueError:
            return default_val
    if isinstance(default_val, list):
        s = raw.strip()
        if s.startswith("["):
            try:
                v = json.loads(s)
                if isinstance(v, list):
                    return v
            except json.JSONDecodeError:
                pass
        return [x.strip() for x in s.split(",") if x.strip()]
    return raw


def _canonical_to_short(env_dict: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for canonical, raw in env_dict.items():
        if canonical in _PRIORITY_KEYS:
            continue  # write-only for webup; IMAGE_HOST_ORDER is authoritative
        short = _WEBUP_TO_SHORT.get(canonical, canonical)
        if short in DEFAULT_CONFIG:
            out[short] = _coerce_value(DEFAULT_CONFIG[short], raw)
        else:
            out[short] = raw
    return _upgrade_legacy_keys(out)


def _short_to_canonical(cfg: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for short, val in cfg.items():
        if short in WEBUP_KEY_MAP:
            sv = _stringify_value(val)
            if sv is None and short in _WEBUP_REQUIRED_PATH_KEYS:
                sv = str(Path.home())
            if sv is not None:
                out[WEBUP_KEY_MAP[short]] = sv
        else:
            out[short] = _stringify_value_passthrough(val)
    order = cfg.get("IMAGE_HOST_ORDER")
    if isinstance(order, list) and order:
        out.update(_image_host_priorities(order))
    # Webup needs PREFS__SCAN_PATH at boot; the orchestrator overrides it
    # per-upload via /setenv but the file must always carry a valid default.
    out.setdefault("PREFS__SCAN_PATH", ".")
    return out


# ---------------------------------------------------------------------------
# load() / save() / migration
# ---------------------------------------------------------------------------

def _migrate_json_to_env() -> bool:
    """Best-effort one-shot migration of legacy Unit3Dbot.json → .env.

    Returns True if a new .env was just written by us. Idempotent: if the
    backup already exists we don't touch anything.
    """
    json_path = _legacy_json_path()
    bak_path = json_path.with_name(json_path.name + ".migrated-bak")
    if bak_path.exists():
        if json_path.exists():
            log.warning(
                "Found both %s and existing backup %s — leaving JSON in place. "
                "Delete one to disambiguate.", json_path, bak_path,
            )
        return False
    if not json_path.exists():
        return False
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to migrate legacy JSON %s: %s", json_path, e)
        return False
    data = _upgrade_legacy_keys(data)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    save(merged)
    try:
        os.rename(json_path, bak_path)
        log.warning(
            "Migrated %s → %s; backup saved at %s",
            json_path, _resolve_env_path(), bak_path,
        )
    except OSError as e:
        log.error("Migration succeeded but rename failed: %s", e)
    return True


_TRACKER_URL_KEYS = {"ITT_URL", "PTT_URL", "SIS_URL"}


def _normalize_tracker_urls(cfg: dict[str, Any]) -> dict[str, Any]:
    """Strip trailing slashes from tracker base URLs.

    Webup builds the announce URL by appending ``/announce/<pid>`` to
    ``TRACKER__<X>_URL``. A trailing slash on the configured URL produces
    ``https://tracker.tld//announce/<pid>`` which the tracker rejects with
    404, leaving qBittorrent unable to register and the torrent silently
    invisible on the site even though webup's ``/upload`` returned 200.
    """
    for k in _TRACKER_URL_KEYS:
        v = cfg.get(k)
        if isinstance(v, str):
            stripped = v.rstrip("/")
            if stripped != v:
                cfg[k] = stripped
    return cfg


def load() -> dict[str, Any]:
    env_path = _resolve_env_path()
    if not env_path.exists():
        _migrate_json_to_env()
    if not env_path.exists():
        return dict(DEFAULT_CONFIG)
    with _lock:
        raw = _parse_env_file(env_path)
    short = _canonical_to_short(raw)
    merged = dict(DEFAULT_CONFIG)
    merged.update(short)
    return _normalize_tracker_urls(merged)


def save(cfg: dict[str, Any]) -> None:
    cfg = _upgrade_legacy_keys(dict(cfg))
    cfg = _normalize_tracker_urls(cfg)
    canonical = _short_to_canonical(cfg)
    text = _dump_env_file(canonical)
    env_path = _resolve_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        fd, tmp = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(env_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, env_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    # Best-effort: mirror to webup .env via /setenv. Runs in the background
    # if an event loop is available (i.e. called from a request handler).
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            from .webup_client import get_client
            asyncio.create_task(sync_to_webup(get_client(), dict(cfg)))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Runtime settings — env > .env file > _RUNTIME_DEFAULTS
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
    """Resolve a U3DP_* runtime setting.

    Precedence: env var (new → legacy ITA_*) → .env file → _RUNTIME_DEFAULTS.

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
    """Effective values shown in the Seeding Flow settings section."""
    p = _resolve_env_path()
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
        "U3DP_ENV_PATH": str(p),
        "WEBUP_ENVPATH_DIR": str(p.parent),
        "UNIT3DUP_CONFIG_LEGACY": str(_legacy_json_path()),
        "WEBUP_URL": runtime_setting("WEBUP_URL", "http://127.0.0.1:8000"),
        "WEBUP_REPO_PATH": runtime_setting("WEBUP_REPO_PATH", str(Path.home() / "dev" / "Unit3DWebUp")),
        "WEBUP_SYSTEMD_UNIT": runtime_setting("WEBUP_SYSTEMD_UNIT", "unit3dwebup.service"),
    }


env_readonly = env_runtime


# ---------------------------------------------------------------------------
# Webup runtime sync (live, no restart) via POST /setenv
# ---------------------------------------------------------------------------

def _to_webup_env_payload(cfg: dict[str, Any]) -> dict[str, str]:
    """Subset of cfg ready to be POSTed to webup ``/setenv`` one key at a time."""
    out: dict[str, str] = {}
    for k_local, k_remote in WEBUP_KEY_MAP.items():
        if k_local not in cfg:
            continue
        sv = _stringify_value(cfg[k_local])
        if sv is None:
            continue
        out[k_remote] = sv
    order = cfg.get("IMAGE_HOST_ORDER")
    if isinstance(order, list) and order:
        out.update(_image_host_priorities(order))
    return out


async def sync_to_webup(client: Any, diff: dict[str, Any] | None = None) -> dict[str, str]:
    """Push (a subset of) settings to webup runtime via /setenv.

    The persistent .env on disk is shared, but webup only re-reads it at
    startup. /setenv updates ``os.environ`` so the next ``Settings()``
    rebuild picks up changes without restarting webup.
    """
    cfg = load() if diff is None else diff
    payload = _to_webup_env_payload(cfg)
    pushed: dict[str, str] = {}
    for k, v in payload.items():
        try:
            await client.setenv(k, v)
            pushed[k] = v
        except Exception:
            continue
    return pushed


async def bootstrap_webup_env(client: Any) -> dict[str, str]:
    """Wait for webup health, then push the full mapped subset once."""
    import asyncio
    for attempt in range(6):
        try:
            h = await client.health(force=True)
        except Exception:
            h = {"ok": False}
        if h.get("ok"):
            return await sync_to_webup(client)
        await asyncio.sleep(min(2 * (attempt + 1), 30))
    return {}
