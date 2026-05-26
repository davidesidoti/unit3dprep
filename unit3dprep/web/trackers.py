"""Tracker (Unit3D) API wrappers.

v1 wires up ITT (Unit3D public API). PTT/SIS return 501 on search so the
UI can render the tabs without crashing when the user hasn't filled in
their credentials.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any

import httpx


@dataclass
class SearchResult:
    tracker: str
    id: int
    name: str
    type: str          # Movie|Serie|Game|Doc
    resolution: str    # 4K|1080p|720p|—
    size: str          # human-readable
    seeders: int
    leechers: int
    uploader: str
    url: str           # details URL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Tracker(ABC):
    key: str = "generic"
    label: str = "Generic"

    @abstractmethod
    async def status(self) -> bool: ...

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]: ...


def _human_size(b: int) -> str:
    for unit, size in [("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
        if b >= size:
            return f"{b / size:.1f} {unit}"
    return f"{b} B"


def _resolution_for(attrs: dict[str, Any]) -> str:
    res_id = attrs.get("resolution_id")
    res_name = (attrs.get("resolution") or "").lower()
    if "2160" in res_name or res_id == 1:
        return "4K"
    if "1080" in res_name:
        return "1080p"
    if "720" in res_name:
        return "720p"
    if "576" in res_name or "480" in res_name:
        return "SD"
    return "—"


def _type_for(attrs: dict[str, Any]) -> str:
    cat = (attrs.get("category") or "").lower()
    if "tv" in cat or "serie" in cat:
        return "Serie"
    if "movie" in cat or "film" in cat:
        return "Movie"
    if "game" in cat:
        return "Game"
    if "doc" in cat or "book" in cat:
        return "Doc"
    return "Movie"


class Unit3DTracker(Tracker):
    """Generic Unit3D tracker. Subclass with site-specific key/label/url."""

    base_url: str
    api_key: str

    def __init__(self, key: str, label: str, url: str, api_key: str):
        self.key = key
        self.label = label
        self.base_url = url.rstrip("/")
        self.api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and bool(self.api_key) and self.api_key not in {"no_key", ""}

    async def status(self) -> bool:
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(self.base_url)
                return r.status_code < 500
        except Exception:
            return False

    async def search(self, query: str) -> list[SearchResult]:
        if not self.api_key or self.api_key in {"no_key", ""}:
            raise RuntimeError(f"{self.key} API key not configured")
        params = {"api_token": self.api_key, "name": query, "perPage": 25}
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{self.base_url}/api/torrents/filter", params=params)
            r.raise_for_status()
            payload = r.json()
        out: list[SearchResult] = []
        for entry in payload.get("data", [])[:25]:
            attrs = entry.get("attributes") or entry
            tid = int(entry.get("id") or attrs.get("id") or 0)
            size_val = attrs.get("size")
            try:
                size_int = int(size_val)
                size_h = _human_size(size_int)
            except (TypeError, ValueError):
                size_h = str(size_val or "—")
            out.append(SearchResult(
                tracker=self.key,
                id=tid,
                name=attrs.get("name") or "",
                type=_type_for(attrs),
                resolution=_resolution_for(attrs),
                size=size_h,
                seeders=int(attrs.get("seeders") or 0),
                leechers=int(attrs.get("leechers") or 0),
                uploader=attrs.get("uploader") or "",
                url=f"{self.base_url}/torrents/{tid}",
            ))
        return out


class _StubTracker(Tracker):
    def __init__(self, key: str, label: str, url: str, api_key: str = ""):
        self.key = key
        self.label = label
        self.url = url.rstrip("/")
        self.api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self.url) and bool(self.api_key) and self.api_key not in {"no_key", ""}

    async def status(self) -> bool:
        if not self.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(self.url)
                return r.status_code < 500
        except Exception:
            return False

    async def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError(f"{self.key} search not implemented yet")


def build_trackers(cfg: dict[str, Any]) -> dict[str, Tracker]:
    """Instantiate all three trackers from the shared .env config."""
    return {
        "ITT": Unit3DTracker(
            "ITT", "ITA Torrents",
            cfg.get("ITT_URL", ""), cfg.get("ITT_APIKEY", ""),
        ),
        "PTT": _StubTracker(
            "PTT", "Polish Torrent",
            cfg.get("PTT_URL", ""), cfg.get("PTT_APIKEY", ""),
        ),
        "SIS": _StubTracker(
            "SIS", "SIS",
            cfg.get("SIS_URL", ""), cfg.get("SIS_APIKEY", ""),
        ),
    }
