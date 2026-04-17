"""Shared Jinja2Templates instance with root_path global."""
import os
from pathlib import Path

from fastapi.templating import Jinja2Templates

ROOT_PATH = os.environ.get("ITA_ROOT_PATH", "")  # e.g. "/itatorrents" on Ultra.cc
_TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["root_path"] = ROOT_PATH
