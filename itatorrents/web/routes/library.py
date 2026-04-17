"""Library browse routes: movies / series / anime list + detail."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ...media import CATEGORIES, get_item, scan_category
from ..db import list_uploads
from ..tmdb_cache import get_many
from ..templates_env import ROOT_PATH, templates

router = APIRouter()

CATEGORY_LABELS = {
    "movies": "Movies",
    "series": "Series",
    "anime": "Anime",
}


def _default_tmdb_kind(item) -> str:
    return "tv" if item.kind == "series" else "movie"


async def _enrich_item(item, cache: dict, uploaded_source_paths: set):
    """Inject TMDB cache + upload status into a MediaItem in-place."""
    sp = str(item.path)

    # TMDB from series-level cache key
    tmdb = cache.get(sp)
    if tmdb:
        item.tmdb_id = tmdb.get("tmdb_id", "")
        item.tmdb_kind = tmdb.get("tmdb_kind", "") or _default_tmdb_kind(item)
        item.tmdb_title = tmdb.get("title", "")
        item.tmdb_poster = tmdb.get("poster", "")
        item.tmdb_overview = tmdb.get("overview", "")

    if item.kind == "series":
        for season in item.seasons:
            ssp = str(season.path)
            season.already_uploaded = ssp in uploaded_source_paths
            # Fall back to season-level cache if series level has none
            if not item.tmdb_id:
                s_tmdb = cache.get(ssp)
                if s_tmdb:
                    item.tmdb_id = s_tmdb.get("tmdb_id", "")
                    item.tmdb_kind = s_tmdb.get("tmdb_kind", "") or _default_tmdb_kind(item)
                    item.tmdb_title = s_tmdb.get("title", "")
                    item.tmdb_poster = s_tmdb.get("poster", "")
                    item.tmdb_overview = s_tmdb.get("overview", "")
        item.uploaded_season_numbers = [s.number for s in item.seasons if s.already_uploaded]

    if not item.tmdb_kind:
        item.tmdb_kind = _default_tmdb_kind(item)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(f"{ROOT_PATH}/library/movies")


@router.get("/library/{category}", response_class=HTMLResponse)
async def library_list(request: Request, category: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    items = scan_category(category)

    # Uploaded source paths for filtering
    uploads = await list_uploads()
    uploaded_source_paths = {r["source_path"] for r in uploads}

    # Collect all paths for bulk cache lookup
    all_paths = []
    for item in items:
        all_paths.append(str(item.path))
        for s in item.seasons:
            all_paths.append(str(s.path))
    cache = await get_many(all_paths)

    filtered = []
    for item in items:
        await _enrich_item(item, cache, uploaded_source_paths)
        if item.kind == "movie":
            if str(item.path) in uploaded_source_paths:
                continue  # hide already-uploaded movies
        filtered.append(item)

    has_missing_tmdb = any(not i.tmdb_id for i in filtered)

    return templates.TemplateResponse(request, "library.html", {
        "category": category,
        "label": CATEGORY_LABELS[category],
        "items": filtered,
        "active": category,
        "has_missing_tmdb": has_missing_tmdb,
    })


@router.get("/library/{category}/{item_name:path}", response_class=HTMLResponse)
async def library_detail(request: Request, category: str, item_name: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, f"'{item_name}' non trovato in {category}")

    uploads = await list_uploads()
    uploaded_source_paths = {r["source_path"] for r in uploads}

    all_paths = [str(item.path)] + [str(s.path) for s in item.seasons]
    cache = await get_many(all_paths)
    await _enrich_item(item, cache, uploaded_source_paths)

    return templates.TemplateResponse(request, "detail.html", {
        "item": item,
        "category": category,
        "label": CATEGORY_LABELS[category],
        "active": category,
    })
