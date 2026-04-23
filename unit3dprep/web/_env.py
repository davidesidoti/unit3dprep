import logging
import os
from pathlib import Path

log = logging.getLogger("unit3dprep.env")

_warned: set[str] = set()


def env(new_key: str, legacy_key: str | None = None, default: str | None = None) -> str | None:
    v = os.getenv(new_key)
    if v is not None:
        return v
    if legacy_key:
        v = os.getenv(legacy_key)
        if v is not None:
            if legacy_key not in _warned:
                log.warning("Using legacy env var %s; rename to %s", legacy_key, new_key)
                _warned.add(legacy_key)
            return v
    return default


_LEGACY_DOTFILES = {
    ".itatorrents_db.json": ".unit3dprep_db.json",
    ".itatorrents_tmdb_cache.json": ".unit3dprep_tmdb_cache.json",
    ".itatorrents_lang_cache.json": ".unit3dprep_lang_cache.json",
}


def migrate_dotfiles(root: Path) -> None:
    for old, new in _LEGACY_DOTFILES.items():
        old_p = root / old
        new_p = root / new
        if old_p.exists() and not new_p.exists():
            try:
                old_p.rename(new_p)
                log.warning("Migrated legacy dotfile %s -> %s", old, new)
            except OSError as e:
                log.error("Failed to migrate %s -> %s: %s", old, new, e)
