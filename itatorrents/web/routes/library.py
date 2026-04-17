"""Library browse routes: movies / series / anime list + detail."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ...media import CATEGORIES, get_item, scan_category
from ..templates_env import ROOT_PATH, templates

router = APIRouter()

CATEGORY_LABELS = {
    "movies": "Movies",
    "series": "Series",
    "anime": "Anime",
}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(f"{ROOT_PATH}/library/movies")


@router.get("/library/{category}", response_class=HTMLResponse)
async def library_list(request: Request, category: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    items = scan_category(category)
    return templates.TemplateResponse("library.html", {
        "request": request,
        "category": category,
        "label": CATEGORY_LABELS[category],
        "items": items,
        "active": category,
    })


@router.get("/library/{category}/{item_name:path}", response_class=HTMLResponse)
async def library_detail(request: Request, category: str, item_name: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Categoria non trovata")
    item = get_item(category, item_name)
    if item is None:
        raise HTTPException(404, f"'{item_name}' non trovato in {category}")
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "item": item,
        "category": category,
        "label": CATEGORY_LABELS[category],
        "active": category,
    })
