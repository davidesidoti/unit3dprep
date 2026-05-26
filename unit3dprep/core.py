"""Pure-logic functions. No print/input/sys.exit side effects."""
import json
import os
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None  # type: ignore

try:
    from guessit import guessit
except ImportError:
    guessit = None  # type: ignore

def seedings_dir() -> Path:
    """Configured hardlink target; env → shared .env → ~/seedings."""
    default = str(Path.home() / "seedings")
    try:
        from .web import config
        return Path(config.runtime_setting("U3DP_SEEDINGS_DIR", default=default))
    except Exception:
        from .web._env import env as _env
        return Path(_env("U3DP_SEEDINGS_DIR", "ITA_SEEDINGS_DIR", default) or default)


# Back-compat constant (resolves at import; use seedings_dir() for live-reload).
SEEDINGS_DIR = seedings_dir()
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm", ".wmv", ".flv"}
ITA_TAGS = {"it", "ita", "italian", "italiano"}
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
def tmdb_default_lang() -> str:
    """Re-evaluate every call so .env edits take effect without restart."""
    try:
        from .web import config
        return config.runtime_setting("U3DP_TMDB_LANG", default="it-IT")
    except Exception:
        from .web._env import env as _env
        return _env("U3DP_TMDB_LANG", "ITA_TMDB_LANG", "it-IT") or "it-IT"

LANG_MAP = {
    "it": "ITA", "ita": "ITA", "italian": "ITA", "italiano": "ITA",
    "en": "ENG", "eng": "ENG", "english": "ENG",
    "es": "SPA", "spa": "SPA", "spanish": "SPA",
    "fr": "FRE", "fra": "FRE", "fre": "FRE", "french": "FRE",
    "de": "GER", "ger": "GER", "deu": "GER", "german": "GER",
    "ja": "JPN", "jpn": "JPN", "japanese": "JPN",
    "ko": "KOR", "kor": "KOR", "korean": "KOR",
    "zh": "CHI", "chi": "CHI", "zho": "CHI", "chinese": "CHI",
    "pt": "POR", "por": "POR", "portuguese": "POR",
    "ru": "RUS", "rus": "RUS", "russian": "RUS",
    "nl": "DUT", "dut": "DUT", "nld": "DUT", "dutch": "DUT",
    "pl": "POL", "pol": "POL", "polish": "POL",
    "sv": "SWE", "swe": "SWE", "swedish": "SWE",
    "tr": "TUR", "tur": "TUR", "turkish": "TUR",
    "ar": "ARA", "ara": "ARA", "arabic": "ARA",
    "hi": "HIN", "hin": "HIN", "hindi": "HIN",
}

CHANNELS_MAP = {1: "1.0", 2: "2.0", 3: "2.1", 6: "5.1", 7: "6.1", 8: "7.1", 10: "9.1", 12: "11.1"}

STREAM_ABBR = {
    "netflix": "NF", "amazon": "AMZN", "amazon prime video": "AMZN",
    "disney+": "DSNP", "disney plus": "DSNP", "apple tv+": "ATVP",
    "hbo max": "HMAX", "max": "HMAX", "hulu": "HULU", "paramount+": "PMTP",
    "peacock": "PCOK", "sky": "SKY", "now": "NOW", "rai": "RAI",
    "crunchyroll": "CR",
}


# ---------------------------------------------------------------------------
# MediaInfo: audio detection
# ---------------------------------------------------------------------------

def _audio_langs(track) -> list[str]:
    cands = []
    if track.language:
        cands.append(track.language)
    other = getattr(track, "other_language", None)
    if other:
        cands.extend(other if isinstance(other, list) else [other])
    # Fallback: if no language tag, try track title (some muxers store "Italian", "ITA", etc. there)
    if not cands:
        title = getattr(track, "title", None) or ""
        if title:
            cands.append(title)
    return [c for c in cands if c]


def audio_languages(path: Path) -> list[str]:
    """Return sorted unique normalised language codes for all audio tracks.

    ITA appears first if present; remaining codes are alphabetically sorted.
    Returns empty list if pymediainfo not available or parse fails.
    """
    if MediaInfo is None:
        return []
    try:
        info = MediaInfo.parse(str(path))
    except Exception:
        return []
    seen: list[str] = []
    audio_track_count = 0
    for track in info.tracks:
        if track.track_type != "Audio":
            continue
        audio_track_count += 1
        for c in _audio_langs(track):
            normalized = c.lower().strip()
            # Handle IETF tags like "it-IT", "en-US" → use primary subtag
            if "-" in normalized and "_" not in normalized:
                normalized = normalized.split("-")[0]
            elif "_" in normalized:
                normalized = normalized.split("_")[0]
            code = LANG_MAP.get(normalized)
            if code and code not in seen:
                seen.append(code)
    # Audio tracks exist but none have a recognised language tag → mark as undetermined
    if audio_track_count > 0 and not seen:
        return ["UND"]
    # ITA first, rest alpha
    has_ita = "ITA" in seen
    rest = sorted(c for c in seen if c != "ITA")
    return (["ITA"] + rest) if has_ita else rest


def has_italian_audio(path: Path) -> bool:
    if MediaInfo is None:
        raise RuntimeError("pymediainfo not installed")
    try:
        info = MediaInfo.parse(str(path))
    except Exception as e:
        raise RuntimeError(f"Cannot parse '{path}': {e}") from e
    for track in info.tracks:
        if track.track_type != "Audio":
            continue
        for c in _audio_langs(track):
            normalized = c.lower().strip()
            if "-" in normalized and "_" not in normalized:
                normalized = normalized.split("-")[0]
            elif "_" in normalized:
                normalized = normalized.split("_")[0]
            if normalized in ITA_TAGS:
                return True
    return False


def iter_video_files(folder: Path):
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            yield f


# ---------------------------------------------------------------------------
# MediaInfo: technical specs
# ---------------------------------------------------------------------------

def extract_specs(path: Path) -> dict:
    if MediaInfo is None:
        raise RuntimeError("pymediainfo not installed")
    info = MediaInfo.parse(str(path))
    video_track = next((t for t in info.tracks if t.track_type == "Video"), None)
    audio_tracks = [t for t in info.tracks if t.track_type == "Audio"]

    specs: dict = {
        "resolution": "", "hdr": "", "vcodec_format": "",
        "bit_depth": None, "scan_type": "", "writing_library": "",
        "acodec": "", "channels": "", "object": "",
        "dub": [],
    }

    if video_track:
        height = getattr(video_track, "height", None)
        width = getattr(video_track, "width", None)
        scan = (getattr(video_track, "scan_type", "") or "Progressive").lower()
        suffix = "i" if scan.startswith("interlaced") else "p"
        if width:
            # Width-first: robust against anamorphic/letterboxed crops that reduce height
            # Thresholds: 3840→2160p, 1920→1080p, 1280→720p; SD falls back to height
            if width >= 3200:
                specs["resolution"] = f"2160{suffix}"
            elif width >= 1600:
                specs["resolution"] = f"1080{suffix}"
            elif width >= 1100:
                specs["resolution"] = f"720{suffix}"
            elif height:
                # SD: 720-wide for both PAL/NTSC → distinguish by height
                for h in (576, 480):
                    if height >= h:
                        specs["resolution"] = f"{h}{suffix}"
                        break
        elif height:
            for h in (2160, 1080, 720, 576, 480):
                if height >= h:
                    specs["resolution"] = f"{h}{suffix}"
                    break
        specs["vcodec_format"] = (getattr(video_track, "format", "") or "")
        specs["bit_depth"] = getattr(video_track, "bit_depth", None)
        specs["scan_type"] = scan
        specs["writing_library"] = getattr(video_track, "writing_library", "") or ""

        hdr_fmt = (getattr(video_track, "hdr_format_commercial", "")
                   or getattr(video_track, "hdr_format", "") or "")
        hdr_fmt_l = hdr_fmt.lower()
        if "dolby vision" in hdr_fmt_l and "hdr10+" in hdr_fmt_l:
            specs["hdr"] = "DV HDR10+"
        elif "dolby vision" in hdr_fmt_l and "hdr10" in hdr_fmt_l:
            specs["hdr"] = "DV HDR"
        elif "dolby vision" in hdr_fmt_l:
            specs["hdr"] = "DV"
        elif "hdr10+" in hdr_fmt_l:
            specs["hdr"] = "HDR10+"
        elif "hdr10" in hdr_fmt_l or "smpte st 2086" in hdr_fmt_l:
            specs["hdr"] = "HDR"
        elif "hlg" in hdr_fmt_l:
            specs["hdr"] = "HLG"

    if audio_tracks:
        main = audio_tracks[0]
        fmt = (getattr(main, "format", "") or "").lower()
        comm = (getattr(main, "format_commercial_if_any", "")
                or getattr(main, "commercial_name", "") or "").lower()
        profile = (getattr(main, "format_profile", "") or "").lower()

        if "truehd" in fmt or "truehd" in comm:
            specs["acodec"] = "TrueHD"
        elif "dts" in fmt or "dts" in comm:
            if "ma" in profile:
                specs["acodec"] = "DTS-HD MA"
            elif "hra" in profile or "hi" in profile:
                specs["acodec"] = "DTS-HD HRA"
            elif "x" in profile:
                specs["acodec"] = "DTS:X"
            elif "es" in profile:
                specs["acodec"] = "DTS-ES"
            else:
                specs["acodec"] = "DTS"
        elif "e-ac-3" in fmt or "eac3" in fmt or "dd+" in comm or "digital plus" in comm:
            specs["acodec"] = "DD+"
        elif "ac-3" in fmt or "ac3" in fmt:
            specs["acodec"] = "DD"
        elif "flac" in fmt:
            specs["acodec"] = "FLAC"
        elif "alac" in fmt:
            specs["acodec"] = "ALAC"
        elif "opus" in fmt:
            specs["acodec"] = "Opus"
        elif "pcm" in fmt:
            specs["acodec"] = "LPCM"
        elif "aac" in fmt:
            specs["acodec"] = "AAC"
        else:
            specs["acodec"] = (getattr(main, "format", "") or "").upper()

        try:
            ch = int(getattr(main, "channel_s", 0) or 0)
            specs["channels"] = CHANNELS_MAP.get(ch, f"{ch}.0")
        except (ValueError, TypeError):
            specs["channels"] = ""

        if "atmos" in comm or "atmos" in fmt:
            specs["object"] = "Atmos"
        elif "auro" in comm or "auro" in fmt:
            specs["object"] = "Auro3D"

        dubs = []
        for t in audio_tracks:
            for lang in _audio_langs(t):
                code = LANG_MAP.get(lang.lower().strip())
                if code and code not in dubs:
                    dubs.append(code)
        specs["dub"] = dubs

    return specs


def vcodec_for_type(specs: dict, src_type: str) -> str:
    fmt = (specs.get("vcodec_format") or "").upper()
    writing = (specs.get("writing_library") or "").lower()
    t = src_type.lower()

    is_avc = "AVC" in fmt
    is_hevc = "HEVC" in fmt or "H.265" in fmt
    is_vp9 = "VP9" in fmt
    is_mpeg2 = "MPEG" in fmt and "2" in fmt
    is_vc1 = "VC-1" in fmt

    if t in {"remux", "disc", "bluray", "uhd bluray", "3d bluray", "hddvd"}:
        if is_hevc: return "HEVC"
        if is_avc: return "AVC"
        if is_mpeg2: return "MPEG-2"
        if is_vc1: return "VC-1"
    if t in {"web-dl", "hdtv", "uhdtv"}:
        if is_hevc: return "H.265"
        if is_avc: return "H.264"
        if is_vp9: return "VP9"
        if is_mpeg2: return "MPEG-2"
    if "x265" in writing: return "x265"
    if "x264" in writing: return "x264"
    if is_hevc: return "x265"
    if is_avc: return "x264"
    return fmt


def hi10p_flag(specs: dict) -> bool:
    fmt = (specs.get("vcodec_format") or "").upper()
    return ("AVC" in fmt) and (specs.get("bit_depth") == 10) and (not specs.get("hdr"))


# ---------------------------------------------------------------------------
# guessit → source/type
# ---------------------------------------------------------------------------

def map_source(guess: dict) -> tuple[str, str]:
    src = (guess.get("source") or "").lower()
    other = guess.get("other") or []
    if isinstance(other, str):
        other = [other]
    other_l = [o.lower() for o in other]
    stream = (guess.get("streaming_service") or "").lower()

    is_remux = "remux" in other_l
    is_webdl = "web-dl" in other_l or src == "web"
    is_webrip = "webrip" in other_l or "web-rip" in other_l
    is_hdtv = src == "hdtv"
    is_uhd = "ultra hd blu-ray" in src or "uhd" in other_l

    if "blu-ray" in src or src == "bluray":
        source = "UHD BluRay" if is_uhd else "BluRay"
        if is_remux:
            return source, "REMUX"
        return source, ""
    if is_webdl:
        abbr = STREAM_ABBR.get(stream, stream.upper().replace(" ", "") if stream else "WEB")
        return abbr, "WEB-DL"
    if is_webrip:
        abbr = STREAM_ABBR.get(stream, stream.upper().replace(" ", "") if stream else "WEB")
        return abbr, "WEBRip"
    if is_hdtv:
        return ("UHDTV" if is_uhd else "HDTV"), ""
    if "dvd" in src:
        return "DVD", ""
    return (src.upper() if src else ""), ""


# ---------------------------------------------------------------------------
# TMDB
# ---------------------------------------------------------------------------

def tmdb_fetch(kind: str, tmdb_id: str, api_key: str, language: str | None = None) -> dict:
    if not api_key:
        raise RuntimeError("TMDB_API_KEY not set")
    lang = language or tmdb_default_lang()
    url = f"{TMDB_BASE}/{kind}/{urllib.parse.quote(str(tmdb_id))}?api_key={api_key}&language={lang}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def tmdb_fetch_bilingual(kind: str, tmdb_id: str, api_key: str) -> dict:
    """Fetch TMDB in primary lang (TMDB_DEFAULT_LANG) and en-US. Returns merged dict with:
      title, original_title, year, poster, overview (primary), overview_en, title_en.
    """
    data_primary = tmdb_fetch(kind, tmdb_id, api_key, language=tmdb_default_lang())
    data_en = tmdb_fetch(kind, tmdb_id, api_key, language="en-US")

    title = data_primary.get("title") or data_primary.get("name") or ""
    title_en = data_en.get("title") or data_en.get("name") or ""
    original_title = (
        data_primary.get("original_title") or data_primary.get("original_name") or ""
    )
    overview = (data_primary.get("overview") or "")[:300]
    overview_en = (data_en.get("overview") or "")[:300]

    return {
        **data_primary,
        "title": title,
        "title_en": title_en,
        "original_title": original_title,
        "overview": overview,
        "overview_en": overview_en,
    }


def tmdb_year(data: dict, kind: str) -> str:
    date = data.get("release_date") if kind == "movie" else data.get("first_air_date")
    if date and len(date) >= 4:
        return date[:4]
    return ""


def tmdb_poster_url(data: dict) -> str:
    path = data.get("poster_path")
    if path:
        return f"{TMDB_IMAGE_BASE}{path}"
    return ""


def tmdb_search(kind: str, query: str, year: str, api_key: str, language: str | None = None) -> list[dict]:
    """Search TMDB. kind='movie'|'tv'. Returns up to 5 normalized results."""
    if not api_key:
        raise RuntimeError("TMDB_API_KEY not set")
    lang = language or tmdb_default_lang()
    params: dict = {"api_key": api_key, "query": query, "language": lang}
    if year:
        if kind == "movie":
            params["year"] = year
        else:
            params["first_air_date_year"] = year
    url = f"{TMDB_BASE}/search/{kind}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    results = data.get("results", [])[:5]
    normalized = []
    for item in results:
        title = item.get("title") or item.get("name") or ""
        original_title = item.get("original_title") or item.get("original_name") or ""
        date = item.get("release_date") or item.get("first_air_date") or ""
        y = date[:4] if len(date) >= 4 else ""
        poster = f"{TMDB_IMAGE_BASE}{item['poster_path']}" if item.get("poster_path") else ""
        normalized.append({
            "id": item["id"],
            "title": title,
            "original_title": original_title,
            "year": y,
            "poster": poster,
            "overview": (item.get("overview") or "")[:200],
        })
    return normalized


# ---------------------------------------------------------------------------
# Name builder
# ---------------------------------------------------------------------------

def sanitize(s: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join(c for c in s if c not in bad).strip()


def build_name(
    title: str,
    year: str,
    se: str,
    specs: dict,
    source: str,
    src_type: str,
    tag: str,
    cut: str = "",
    repack: str = "",
    edition_flag: str = "",
    dub_override: list[str] | None = None,
) -> str:
    parts = [title]
    if year:
        parts.append(year)
    if se:
        parts.append(se)
    if cut:
        parts.append(cut)
    if repack:
        parts.append(repack)
    if specs.get("resolution"):
        parts.append(specs["resolution"])
    if "3d" in (edition_flag or "").lower():
        parts.append("3D")
    if source:
        parts.append(source)
    if src_type:
        parts.append(src_type)

    is_disc_or_remux = src_type.upper() in {"REMUX", ""} and source in {
        "BluRay", "UHD BluRay", "3D BluRay", "HDDVD"
    }
    dubs = dub_override if dub_override is not None else specs.get("dub", [])
    dub_str = " ".join(dubs) if dubs else ""

    if is_disc_or_remux:
        if hi10p_flag(specs): parts.append("Hi10P")
        if specs.get("hdr"): parts.append(specs["hdr"])
        vc = vcodec_for_type(specs, src_type or source)
        if vc: parts.append(vc)
        if dub_str: parts.append(dub_str)
        if specs.get("acodec"): parts.append(specs["acodec"])
        if specs.get("channels"): parts.append(specs["channels"])
        if specs.get("object"): parts.append(specs["object"])
    else:
        if dub_str: parts.append(dub_str)
        if specs.get("acodec"): parts.append(specs["acodec"])
        if specs.get("channels"): parts.append(specs["channels"])
        if specs.get("object"): parts.append(specs["object"])
        if hi10p_flag(specs): parts.append("Hi10P")
        if specs.get("hdr"): parts.append(specs["hdr"])
        vc = vcodec_for_type(specs, src_type or source)
        if vc: parts.append(vc)

    base = " ".join(p for p in parts if p)
    if tag:
        base = f"{base}-{tag}"
    return sanitize(base)


def format_se(season: int | None, episode) -> str:
    if season is None or episode is None:
        return ""
    if isinstance(episode, list) and episode:
        if len(episode) == 1:
            return f"S{season:02d}E{episode[0]:02d}"
        ep_sorted = sorted(episode)
        if ep_sorted == list(range(ep_sorted[0], ep_sorted[-1] + 1)):
            return f"S{season:02d}E{ep_sorted[0]:02d}-{ep_sorted[-1]:02d}"
        return f"S{season:02d}E{ep_sorted[0]:02d}E{ep_sorted[-1]:02d}"
    if isinstance(episode, int):
        return f"S{season:02d}E{episode:02d}"
    return ""


# ---------------------------------------------------------------------------
# Hardlink
# ---------------------------------------------------------------------------

def hardlink_file(src: Path, dst: Path, overwrite: bool = True):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if not overwrite:
            return
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    os.link(src, dst)


def hardlink_tree(src_dir: Path, dst_dir: Path, episode_rename: dict[Path, str]):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for src_file in sorted(src_dir.rglob("*")):
        if not src_file.is_file():
            continue
        if src_file.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        rel_parent = src_file.parent.relative_to(src_dir)
        target_parent = dst_dir / rel_parent
        target_parent.mkdir(parents=True, exist_ok=True)
        if src_file in episode_rename:
            new_name = episode_rename[src_file] + src_file.suffix.lower()
        else:
            new_name = src_file.name
        target = target_parent / new_name
        if target.exists():
            target.unlink()
        os.link(src_file, target)
