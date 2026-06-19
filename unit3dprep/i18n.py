"""Minimal i18n for user-facing API error messages.

The UI forwards the active locale in the `X-U3DP-Lang` header on every API
call; the backend falls back to the `U3DP_LANG` runtime setting when the
header is absent. Only API error `detail` strings are localized here — free
text coming from external processes (unit3dup, TMDB, hardlink OS errors) is
always echoed back untouched.
"""
from __future__ import annotations

from typing import Any

from .web import config as _config

SUPPORTED = ("it", "en")
DEFAULT = "it"

CATALOG: dict[str, dict[str, str]] = {
    "err.path_not_found": {
        "it": "Percorso non trovato",
        "en": "Path not found",
    },
    "err.path_not_found_at": {
        "it": "Percorso non trovato: {path}",
        "en": "Path not found: {path}",
    },
    "err.path_not_allowed": {
        "it": "Percorso non consentito",
        "en": "Path not allowed",
    },
    "err.path_outside": {
        "it": "Percorso fuori dalle directory consentite",
        "en": "Path outside allowed directories",
    },
    "err.permission_denied": {
        "it": "Permesso negato",
        "en": "Permission denied",
    },
    "err.invalid_mode": {
        "it": "Modalità non valida",
        "en": "Invalid mode",
    },
    "err.invalid_kind": {
        "it": "Tipo non valido",
        "en": "Invalid kind",
    },
    "err.job_not_found": {
        "it": "Job non trovato",
        "en": "Job not found",
    },
    "err.no_active_process": {
        "it": "Nessun processo attivo",
        "en": "No active process",
    },
    "err.category_not_found": {
        "it": "Categoria non trovata",
        "en": "Category not found",
    },
    "err.item_not_found_in_category": {
        "it": "'{name}' non trovato in {category}",
        "en": "'{name}' not found in {category}",
    },
    "err.tmdb_api_key_missing": {
        "it": "TMDB_API_KEY non impostata",
        "en": "TMDB_API_KEY not set",
    },
    "err.tracker_unknown": {
        "it": "Tracker sconosciuto '{tracker}'",
        "en": "Unknown tracker '{tracker}'",
    },
    "err.reseed_session_expired": {
        "it": "Sessione reseed non trovata o scaduta",
        "en": "Reseed session not found or expired",
    },
    "err.record_not_found": {
        "it": "Record non trovato",
        "en": "Record not found",
    },
    "err.wizard_session_expired": {
        "it": "Sessione wizard non trovata o scaduta",
        "en": "Wizard session not found or expired",
    },
    "err.episode_requires_file": {
        "it": "Modalità episodio richiede un path di file",
        "en": "Episode mode requires a file path",
    },
    "err.audio_check_not_passed": {
        "it": "Controllo audio non superato",
        "en": "Audio check not passed",
    },
    "err.tmdb_fetch_failed": {
        "it": "Recupero TMDB fallito: {error}",
        "en": "TMDB fetch failed: {error}",
    },
    "err.no_video_episode": {
        "it": "Nessun file video trovato per modalità episodio",
        "en": "No video file found for episode mode",
    },
    "err.no_video": {
        "it": "Nessun file video trovato",
        "en": "No video file found",
    },
    "err.hardlink_failed": {
        "it": "Hardlink fallito: {error}",
        "en": "Hardlink failed: {error}",
    },
    "err.invalid_password": {
        "it": "Password non valida",
        "en": "Invalid password",
    },
    "err.release_not_found": {
        "it": "Release non trovata: {error}",
        "en": "Release not found: {error}",
    },
}


def _normalize(lang: str | None) -> str:
    if not lang:
        return DEFAULT
    code = lang.strip().lower().split("-", 1)[0].split("_", 1)[0]
    return code if code in SUPPORTED else DEFAULT


def t(key: str, lang: str | None = None, /, **fmt: Any) -> str:
    """Resolve a catalog key to a localized string.

    Falls back to `U3DP_LANG` runtime setting then to `DEFAULT` when `lang`
    is None/unknown. Unknown keys return the key itself (defensive: never
    crash the API over a missing translation).
    """
    resolved = _normalize(lang or _config.runtime_setting("U3DP_LANG", DEFAULT))
    entry = CATALOG.get(key)
    if entry is None:
        return key.format(**fmt) if fmt else key
    text = entry.get(resolved) or entry.get(DEFAULT) or key
    return text.format(**fmt) if fmt else text


def get_request_lang(request: Any) -> str:
    """Extract active locale from a FastAPI/Starlette Request.

    Precedence: `X-U3DP-Lang` header → `U3DP_LANG` runtime setting → DEFAULT.
    """
    try:
        hdr = request.headers.get("x-u3dp-lang") or request.headers.get("X-U3DP-Lang")
    except Exception:
        hdr = None
    if hdr:
        return _normalize(hdr)
    return _normalize(_config.runtime_setting("U3DP_LANG", DEFAULT))
