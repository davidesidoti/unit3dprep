"""Library scanner for ~/media/{movies,series,anime}."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .core import VIDEO_EXTENSIONS

MEDIA_ROOT = Path.home() / "media"
CATEGORIES = ("movies", "series", "anime")


@dataclass
class Season:
    number: int
    label: str  # "Season 01"
    path: Path
    video_files: list[Path] = field(default_factory=list)
    already_uploaded: bool = False

    @property
    def episode_count(self) -> int:
        return len(self.video_files)


@dataclass
class MediaItem:
    name: str
    path: Path
    category: str    # movies | series | anime
    kind: str        # movie | series
    seasons: list[Season] = field(default_factory=list)
    video_files: list[Path] = field(default_factory=list)
    # TMDB metadata (populated by routes from cache, not by scanner)
    tmdb_id: str = ""
    tmdb_kind: str = ""
    tmdb_title: str = ""
    tmdb_poster: str = ""
    tmdb_overview: str = ""
    # Upload status (populated by routes)
    already_uploaded: bool = False
    uploaded_season_numbers: list = field(default_factory=list)

    @property
    def year(self) -> str:
        m = re.search(r'\((\d{4})\)', self.name)
        return m.group(1) if m else ""

    @property
    def title(self) -> str:
        return re.sub(r'\s*\(\d{4}\)\s*$', '', self.name).strip()

    @property
    def total_files(self) -> int:
        if self.kind == "series":
            return sum(s.episode_count for s in self.seasons)
        return len(self.video_files)


def _iter_video(folder: Path) -> list[Path]:
    return sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    )


def _detect_kind(folder: Path, category: str) -> str:
    if category == "series":
        return "series"
    if category == "movies":
        return "movie"
    # anime: has Season XX/ subfolder → series
    for child in folder.iterdir():
        if child.is_dir() and re.match(r'[Ss]eason\s+\d+', child.name):
            return "series"
    return "movie"


def _scan_seasons(folder: Path) -> list[Season]:
    seasons = []
    for child in sorted(folder.iterdir()):
        if not child.is_dir():
            continue
        m = re.match(r'[Ss]eason\s+(\d+)', child.name)
        if m:
            num = int(m.group(1))
            videos = _iter_video(child)
            seasons.append(Season(
                number=num,
                label=child.name,
                path=child,
                video_files=videos,
            ))
    return seasons


def scan_category(category: str) -> list[MediaItem]:
    base = MEDIA_ROOT / category
    if not base.exists():
        return []
    items = []
    for item_path in sorted(base.iterdir()):
        if item_path.is_file():
            if item_path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            items.append(MediaItem(
                name=item_path.stem,
                path=item_path,
                category=category,
                kind="movie",
                video_files=[item_path],
            ))
        elif item_path.is_dir():
            kind = _detect_kind(item_path, category)
            if kind == "series":
                seasons = _scan_seasons(item_path)
                items.append(MediaItem(
                    name=item_path.name,
                    path=item_path,
                    category=category,
                    kind="series",
                    seasons=seasons,
                ))
            else:
                items.append(MediaItem(
                    name=item_path.name,
                    path=item_path,
                    category=category,
                    kind="movie",
                    video_files=_iter_video(item_path),
                ))
    return items


def get_item(category: str, item_name: str) -> MediaItem | None:
    """Fetch single item by category + folder/file name."""
    base = MEDIA_ROOT / category
    target = base / item_name
    if not target.exists():
        # Try as file without extension
        for ext in VIDEO_EXTENSIONS:
            candidate = base / (item_name + ext)
            if candidate.exists():
                return MediaItem(
                    name=candidate.stem,
                    path=candidate,
                    category=category,
                    kind="movie",
                    video_files=[candidate],
                )
        return None
    if target.is_file():
        return MediaItem(
            name=target.stem,
            path=target,
            category=category,
            kind="movie",
            video_files=[target],
        )
    kind = _detect_kind(target, category)
    if kind == "series":
        return MediaItem(
            name=target.name,
            path=target,
            category=category,
            kind="series",
            seasons=_scan_seasons(target),
        )
    return MediaItem(
        name=target.name,
        path=target,
        category=category,
        kind="movie",
        video_files=_iter_video(target),
    )


def scan_seedings() -> list[Path]:
    """List top-level items in ~/seedings/."""
    seedings = Path.home() / "seedings"
    if not seedings.exists():
        return []
    return sorted(seedings.iterdir())
