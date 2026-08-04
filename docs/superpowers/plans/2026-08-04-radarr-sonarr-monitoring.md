# Integrazione Radarr / Sonarr — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rimuovere il monitoraggio di un film, di una serie, di una stagione o di un
episodio da Radarr/Sonarr direttamente dalla libreria di unit3dprep, vedendo lo stato
di monitoraggio nella griglia.

**Architecture:** Un modulo `web/arr.py` separa le funzioni pure (costruzione
dell'indice, mutazione dei payload) dalle chiamate HTTP. Un router `web/api/arr.py`
espone un indice `path → monitored` in una sola chiamata con cache 60 s; il frontend
lo mergia sulla libreria per path. La libreria resta indipendente: se Radarr o Sonarr
sono offline o non configurati, non cambia nulla.

**Tech Stack:** Python 3.12+, FastAPI, httpx, pydantic · React 18, TypeScript, Vite,
react-i18next, lucide-react.

**Spec:** [2026-08-04-radarr-sonarr-monitoring-design.md](../specs/2026-08-04-radarr-sonarr-monitoring-design.md)

---

## Nota sulla verifica

**Questo repo non ha una suite di test** e per istruzione di progetto non se ne deve
introdurre una (`CLAUDE.md`: *"Strumenti reali di questo repo (non cercarne altri)"*).
Gli strumenti reali sono:

| Ambito | Comando |
|---|---|
| Backend, syntax check | `python -m py_compile <file>` |
| Frontend, build + type-check | `cd frontend && npm run build` |
| Documentazione | `python -m mkdocs build --strict -d "$TEMP/claude/mkdocs-check"` |

Per mantenere comunque il ritmo test-first, ogni task backend con logica pura si
verifica con uno **script di verifica** nella scratchpad che asserisce il
comportamento su payload finti. Lo script si scrive e si lancia **prima**
dell'implementazione (deve fallire), poi si rilancia dopo (deve passare). Gli script
non entrano nel repo.

Directory scratchpad (già esistente, non va creata):

```
C:\Users\sidot\AppData\Local\Temp\claude\C--Users-sidot-Documents-Github-itatorrents-seeding\3ef9771b-54de-4c17-9ad9-cdf48012b007\scratchpad
```

Nel resto del piano viene indicata come `$SCRATCH`. Gli script impostano
`U3DP_ENV_PATH` su un file della scratchpad, così `config.load()` non tocca mai il
`.env` reale dell'utente.

---

## Struttura dei file

**Creati:**

| File | Responsabilità |
|---|---|
| `unit3dprep/web/arr.py` | Client Radarr/Sonarr + funzioni pure di indicizzazione e mutazione. Nessuna dipendenza da FastAPI. |
| `unit3dprep/web/api/arr.py` | Router JSON: status, episodi, unmonitor singolo e bulk, test connessione. |
| `frontend/src/components/ArrMonitor.tsx` | `MonitorBadge` e `UnmonitorBtn` nelle varianti `full` / `icon` / `chip`. |

**Modificati:**

| File | Modifica |
|---|---|
| `unit3dprep/web/config.py` | 4 chiavi in `DEFAULT_CONFIG`, 2 in `MASKED_KEYS`, gruppo `.env`. |
| `unit3dprep/web/app.py` | Import e registrazione del router. |
| `unit3dprep/web/api/settings.py` | Il PUT invalida la cache `arr` quando cambiano le credenziali. |
| `frontend/src/types.ts` | `ArrEntry`, `ArrIndex`, `ArrEpisode`. |
| `frontend/src/components/primitives.tsx` | `ICON_BTN` spostato qui da LibraryView e condiviso. |
| `frontend/src/i18n/locales/{en,it}.ts` | Namespace `arr.*` + chiavi `settings.arr*`. |
| `frontend/src/views/SettingsView.tsx` | Sezione `arr`. |
| `frontend/src/views/LibraryView.tsx` | Caricamento indice, badge, pulsanti, azione bulk. |
| `docs/configurazione.md` (+ `.en`) | Tabella delle chiavi. |
| `docs/uso-web.md` (+ `.en`) | Sezione d'uso. |
| `CHANGELOG.md` | Voce sotto `[Unreleased]`. |

`LibraryView.tsx` è già a 2144 righe: tutta la UI nuova riutilizzabile va in
`ArrMonitor.tsx`, in LibraryView restano solo il caricamento dello stato e i punti di
innesto.

---

## Task 1: Chiavi di configurazione

**Files:**
- Modify: `unit3dprep/web/config.py`

- [ ] **Step 1: Scrivere lo script di verifica**

Crea `$SCRATCH/verify_arr_config.py`:

```python
import os, sys, tempfile
sys.path.insert(0, r"C:\Users\sidot\Documents\Github\itatorrents-seeding")
os.environ["U3DP_ENV_PATH"] = os.path.join(tempfile.gettempdir(), "u3dp_verify.env")

from unit3dprep.web import config

for k in ("W_RADARR_URL", "W_RADARR_APIKEY", "W_SONARR_URL", "W_SONARR_APIKEY"):
    assert k in config.DEFAULT_CONFIG, f"{k} assente da DEFAULT_CONFIG"
    assert config.DEFAULT_CONFIG[k] == "", f"{k} deve avere default vuoto"

assert "W_RADARR_APIKEY" in config.MASKED_KEYS, "W_RADARR_APIKEY non mascherata"
assert "W_SONARR_APIKEY" in config.MASKED_KEYS, "W_SONARR_APIKEY non mascherata"

masked = config.mask_secrets({"W_RADARR_APIKEY": "abc123", "W_RADARR_URL": "http://x"})
assert masked["W_RADARR_APIKEY"] == "__SET__", masked
assert masked["W_RADARR_URL"] == "http://x", masked

restored = config.merge_secrets(
    {"W_SONARR_APIKEY": "real-key"}, {"W_SONARR_APIKEY": "__SET__"}
)
assert restored["W_SONARR_APIKEY"] == "real-key", restored

group_keys = [k for _, keys in config._GROUPS for k in keys]
for k in ("W_RADARR_URL", "W_RADARR_APIKEY", "W_SONARR_URL", "W_SONARR_APIKEY"):
    assert k in group_keys, f"{k} non presente in _GROUPS → non verrebbe scritta nel .env"

print("OK")
```

- [ ] **Step 2: Lanciarlo e verificare che fallisca**

Run: `python "$SCRATCH/verify_arr_config.py"`
Expected: `AssertionError: W_RADARR_URL assente da DEFAULT_CONFIG`

- [ ] **Step 3: Aggiungere le chiavi a `DEFAULT_CONFIG`**

In `unit3dprep/web/config.py`, sostituisci:

```python
    "W_DUPLICATE_CHECK": True,
    "W_DUPLICATE_SIZE_TOLERANCE_PCT": 2.0,
}
```

con:

```python
    "W_DUPLICATE_CHECK": True,
    "W_DUPLICATE_SIZE_TOLERANCE_PCT": 2.0,

    # Radarr / Sonarr — rimozione del monitoraggio dalla libreria.
    "W_RADARR_URL": "",
    "W_RADARR_APIKEY": "",
    "W_SONARR_URL": "",
    "W_SONARR_APIKEY": "",
}
```

- [ ] **Step 4: Aggiungere le API key a `MASKED_KEYS`**

Sostituisci:

```python
    "PTSCREENS_KEY", "PASSIMA_KEY", "IMGBB_KEY", "IMGFI_KEY",
    "FREE_IMAGE_KEY", "LENSDUMP_KEY", "IMARIDE_KEY",
}
```

con:

```python
    "PTSCREENS_KEY", "PASSIMA_KEY", "IMGBB_KEY", "IMGFI_KEY",
    "FREE_IMAGE_KEY", "LENSDUMP_KEY", "IMARIDE_KEY",
    "W_RADARR_APIKEY", "W_SONARR_APIKEY",
}
```

- [ ] **Step 5: Aggiungere il gruppo al dump `.env`**

Sostituisci:

```python
    ("Wizard defaults (unit3dprep)", [
        "W_AUDIO_CHECK", "W_AUTO_TMDB", "W_HIDE_UPLOADED",
        "W_HARDLINK_ONLY", "W_CONFIRM_NAMES",
        "W_DUPLICATE_CHECK", "W_DUPLICATE_SIZE_TOLERANCE_PCT",
    ]),
]
```

con:

```python
    ("Wizard defaults (unit3dprep)", [
        "W_AUDIO_CHECK", "W_AUTO_TMDB", "W_HIDE_UPLOADED",
        "W_HARDLINK_ONLY", "W_CONFIRM_NAMES",
        "W_DUPLICATE_CHECK", "W_DUPLICATE_SIZE_TOLERANCE_PCT",
    ]),
    ("Radarr / Sonarr (unit3dprep)", [
        "W_RADARR_URL", "W_RADARR_APIKEY",
        "W_SONARR_URL", "W_SONARR_APIKEY",
    ]),
]
```

- [ ] **Step 6: Rilanciare lo script e verificare che passi**

Run: `python "$SCRATCH/verify_arr_config.py"`
Expected: `OK`

- [ ] **Step 7: Syntax check**

Run: `python -m py_compile unit3dprep/web/config.py`
Expected: nessun output, exit 0

- [ ] **Step 8: Commit**

```bash
git add unit3dprep/web/config.py
git commit -m "feat(config): chiavi URL e API key per Radarr e Sonarr"
```

---

## Task 2: `arr.py` — indice path → monitored

**Files:**
- Create: `unit3dprep/web/arr.py`

> **Il codice qui sotto è la versione iniziale.** La review di qualità ha poi
> irrobustito la cache e il codice committato differisce: il lock è tenuto per
> tutta la fetch (single-flight invece che stampede), `invalidate_cache()` bumpa
> un contatore di generazione che `build_index` ricontrolla prima di scrivere
> (altrimenti una fetch già in volo resuscita lo stato pre-mutazione per un TTL
> intero), Radarr e Sonarr si interrogano in parallelo con
> `asyncio.gather(..., return_exceptions=True)`, il timeout ha `connect=5.0`, e
> `_exc_detail()` evita i messaggi troncati a `"Richiesta fallita: "` per le
> eccezioni httpx che si stringificano a vuoto. La verità è il file committato;
> gli anchor usati dal Task 3 (`series_index`, `error_msg`, `test_connection`)
> restano validi.

- [ ] **Step 1: Scrivere lo script di verifica**

Crea `$SCRATCH/verify_arr_index.py`:

```python
import os, sys, tempfile
sys.path.insert(0, r"C:\Users\sidot\Documents\Github\itatorrents-seeding")
os.environ["U3DP_ENV_PATH"] = os.path.join(tempfile.gettempdir(), "u3dp_verify.env")

from unit3dprep.web import arr

# --- norm_path -----------------------------------------------------------
assert arr.norm_path("/home/u/media/movies/X/") == "/home/u/media/movies/X"
assert arr.norm_path("/home/u/media//movies/X") == "/home/u/media/movies/X"
assert arr.norm_path("") == ""

# --- movie_index ---------------------------------------------------------
movies = [
    {"id": 7, "title": "Dune", "path": "/media/movies/Dune (2021)", "monitored": True},
    {"id": 8, "title": "Arrival", "path": "/media/movies/Arrival (2016)/", "monitored": False},
    {"id": None, "title": "Broken", "path": "/media/movies/Broken"},   # scartato
    {"id": 9, "title": "NoPath", "monitored": True},                    # scartato
    "not-a-dict",                                                       # scartato
]
idx = arr.movie_index(movies)
assert set(idx) == {"/media/movies/Dune (2021)", "/media/movies/Arrival (2016)"}, idx
assert idx["/media/movies/Dune (2021)"] == {"id": 7, "monitored": True, "title": "Dune"}
assert idx["/media/movies/Arrival (2016)"]["monitored"] is False
assert arr.movie_index(None) == {}
assert arr.movie_index({"error": "nope"}) == {}

# --- series_index --------------------------------------------------------
series = [
    {
        "id": 3, "title": "Severance", "path": "/media/series/Severance",
        "monitored": True,
        "seasons": [
            {"seasonNumber": 1, "monitored": False},
            {"seasonNumber": 2, "monitored": True},
            {"monitored": True},          # senza seasonNumber → scartata
        ],
    },
    {"id": 4, "title": "NoSeasons", "path": "/media/series/Other", "monitored": False},
]
sidx = arr.series_index(series)
assert set(sidx) == {"/media/series/Severance", "/media/series/Other"}, sidx
entry = sidx["/media/series/Severance"]
assert entry["id"] == 3 and entry["monitored"] is True
assert entry["seasons"] == {"1": False, "2": True}, entry["seasons"]
assert sidx["/media/series/Other"]["seasons"] == {}

# --- configured ----------------------------------------------------------
os.environ.pop("W_RADARR_URL", None)
os.environ.pop("W_RADARR_APIKEY", None)
assert arr.configured("radarr") is False
os.environ["W_RADARR_URL"] = "http://127.0.0.1:7878/"
os.environ["W_RADARR_APIKEY"] = "key"
assert arr.configured("radarr") is True
assert arr.creds("radarr") == ("http://127.0.0.1:7878", "key")
os.environ["W_RADARR_APIKEY"] = "no_key"
assert arr.configured("radarr") is False

print("OK")
```

- [ ] **Step 2: Lanciarlo e verificare che fallisca**

Run: `python "$SCRATCH/verify_arr_index.py"`
Expected: `ModuleNotFoundError: No module named 'unit3dprep.web.arr'`

- [ ] **Step 3: Creare `unit3dprep/web/arr.py`**

```python
"""Radarr / Sonarr — read the monitored state and switch it off.

Pure helpers (index building, payload mutation) are kept apart from the HTTP
calls so they can be exercised without a live Radarr or Sonarr.

Library items are matched to *arr records by path: both sides see the same
filesystem, so the ``path`` field these APIs return is identical to the
library item's own path.
"""
from __future__ import annotations

import asyncio
import logging
import posixpath
import time
from typing import Any

import httpx

from . import config

log = logging.getLogger("unit3dprep.arr")

KINDS = ("radarr", "sonarr")
_TIMEOUT = httpx.Timeout(15.0)
_CACHE_TTL = 60.0

_cache: dict[str, Any] = {"data": None, "at": 0.0}
_cache_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def creds(kind: str) -> tuple[str, str]:
    """(base_url without trailing slash, api_key) for ``radarr`` or ``sonarr``."""
    prefix = "W_RADARR" if kind == "radarr" else "W_SONARR"
    base = config.runtime_setting(f"{prefix}_URL", "").strip().rstrip("/")
    token = config.runtime_setting(f"{prefix}_APIKEY", "").strip()
    return base, token


def configured(kind: str) -> bool:
    if kind not in KINDS:
        return False
    base, token = creds(kind)
    return bool(base) and bool(token) and token not in {"no_key", "no_pass"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def norm_path(p: str) -> str:
    """Canonical form of a path, used as the index key.

    Radarr/Sonarr and unit3dprep always share a Linux filesystem in every
    supported deployment, so normalization is anchored to ``posixpath``
    rather than the host OS's path module — ``os.path.normpath`` would
    rewrite ``/`` to ``\\`` when this module is imported under a native
    Windows interpreter (e.g. for local testing), which is never what the
    actual Radarr/Sonarr paths look like.
    """
    if not p:
        return ""
    n = posixpath.normpath(str(p))
    return n.rstrip("/\\") or n


def movie_index(payload: Any) -> dict[str, dict[str, Any]]:
    """``{path: {id, monitored, title}}`` from Radarr ``GET /api/v3/movie``."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, list):
        return out
    for m in payload:
        if not isinstance(m, dict):
            continue
        path = norm_path(m.get("path") or "")
        mid = m.get("id")
        if not path or not isinstance(mid, int):
            continue
        out[path] = {
            "id": mid,
            "monitored": bool(m.get("monitored")),
            "title": str(m.get("title") or ""),
        }
    return out


def series_index(payload: Any) -> dict[str, dict[str, Any]]:
    """``{path: {id, monitored, seasons, title}}`` from Sonarr ``GET /api/v3/series``.

    ``seasons`` is keyed by season number as a string so it survives the JSON
    round-trip to the frontend.
    """
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, list):
        return out
    for s in payload:
        if not isinstance(s, dict):
            continue
        path = norm_path(s.get("path") or "")
        sid = s.get("id")
        if not path or not isinstance(sid, int):
            continue
        seasons: dict[str, bool] = {}
        for season in s.get("seasons") or []:
            if isinstance(season, dict) and isinstance(season.get("seasonNumber"), int):
                seasons[str(season["seasonNumber"])] = bool(season.get("monitored"))
        out[path] = {
            "id": sid,
            "monitored": bool(s.get("monitored")),
            "seasons": seasons,
            "title": str(s.get("title") or ""),
        }
    return out


def error_msg(e: Exception) -> str:
    """User-facing message for a Radarr/Sonarr failure (Italian, like the ITT one)."""
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None) if resp is not None else None
    if code == 401:
        return "API key rifiutata (401)."
    if code == 404:
        return "Endpoint non trovato (404) — controlla l'URL."
    if code is not None:
        return f"Errore HTTP {code}."
    if isinstance(e, httpx.TimeoutException):
        return "Timeout nella richiesta."
    if isinstance(e, httpx.ConnectError):
        return "Connessione rifiutata — servizio spento o URL errato."
    return f"Richiesta fallita: {e}"


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def _client(base: str, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base,
        headers={"X-Api-Key": token},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )


async def _get_json(kind: str, path: str, params: dict[str, Any] | None = None) -> Any:
    base, token = creds(kind)
    async with _client(base, token) as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r.json()


async def _put_json(kind: str, path: str, body: Any) -> None:
    base, token = creds(kind)
    async with _client(base, token) as c:
        r = await c.put(path, json=body)
        r.raise_for_status()


# ---------------------------------------------------------------------------
# Cached index
# ---------------------------------------------------------------------------

def invalidate_cache() -> None:
    _cache["data"] = None
    _cache["at"] = 0.0


async def build_index(*, force: bool = False) -> dict[str, Any]:
    """Full Radarr + Sonarr index, one request per instance.

    A failure on one instance does not stop the other from populating: it lands
    in ``errors`` and the frontend surfaces it without losing the rest.
    """
    async with _cache_lock:
        cached = _cache["data"]
        if cached is not None and not force and (time.monotonic() - _cache["at"]) < _CACHE_TTL:
            return cached

    movies: dict[str, dict[str, Any]] = {}
    series: dict[str, dict[str, Any]] = {}
    errors: dict[str, str | None] = {"radarr": None, "sonarr": None}
    has_radarr = configured("radarr")
    has_sonarr = configured("sonarr")

    if has_radarr:
        try:
            movies = movie_index(await _get_json("radarr", "/api/v3/movie"))
        except Exception as e:  # noqa: BLE001 — never let this break the library
            errors["radarr"] = error_msg(e)
            log.warning("Radarr: index not built — %s", e)
    if has_sonarr:
        try:
            series = series_index(await _get_json("sonarr", "/api/v3/series"))
        except Exception as e:  # noqa: BLE001
            errors["sonarr"] = error_msg(e)
            log.warning("Sonarr: index not built — %s", e)

    data = {
        "configured": {"radarr": has_radarr, "sonarr": has_sonarr},
        "movies": movies,
        "series": series,
        "errors": errors,
    }
    async with _cache_lock:
        _cache["data"] = data
        _cache["at"] = time.monotonic()
    return data


async def test_connection(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        return {"ok": False, "error": "Servizio sconosciuto."}
    if not configured(kind):
        return {"ok": False, "error": "URL o API key mancanti."}
    try:
        data = await _get_json(kind, "/api/v3/system/status")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": error_msg(e)}
    data = data if isinstance(data, dict) else {}
    return {
        "ok": True,
        "version": str(data.get("version") or ""),
        "instance_name": str(data.get("instanceName") or ""),
    }
```

- [ ] **Step 4: Rilanciare lo script e verificare che passi**

Run: `python "$SCRATCH/verify_arr_index.py"`
Expected: `OK`

- [ ] **Step 5: Syntax check**

Run: `python -m py_compile unit3dprep/web/arr.py`
Expected: nessun output, exit 0

- [ ] **Step 6: Commit**

```bash
git add unit3dprep/web/arr.py
git commit -m "feat(arr): indice path-monitored di Radarr e Sonarr con cache"
```

---

## Task 3: `arr.py` — rimozione del monitoraggio

**Files:**
- Modify: `unit3dprep/web/arr.py`

- [ ] **Step 1: Scrivere lo script di verifica**

Crea `$SCRATCH/verify_arr_unmonitor.py`:

```python
import os, sys, tempfile
sys.path.insert(0, r"C:\Users\sidot\Documents\Github\itatorrents-seeding")
os.environ["U3DP_ENV_PATH"] = os.path.join(tempfile.gettempdir(), "u3dp_verify.env")

from unit3dprep.web import arr

SERIES = {
    "id": 3, "title": "Severance", "path": "/media/series/Severance",
    "monitored": True, "qualityProfileId": 4,
    "seasons": [
        {"seasonNumber": 0, "monitored": True},
        {"seasonNumber": 1, "monitored": True},
        {"seasonNumber": 2, "monitored": True},
    ],
}

# --- serie intera: flag serie + tutte le stagioni --------------------------
whole = arr.series_unmonitored_payload(SERIES)
assert whole["monitored"] is False, whole
assert all(s["monitored"] is False for s in whole["seasons"]), whole["seasons"]
assert whole["qualityProfileId"] == 4, "gli altri campi devono sopravvivere"
assert whole["id"] == 3

# l'originale non va mutato
assert SERIES["monitored"] is True
assert all(s["monitored"] is True for s in SERIES["seasons"])

# --- singola stagione: solo quella, flag serie intatto ---------------------
one = arr.series_unmonitored_payload(SERIES, 2)
assert one["monitored"] is True, "il flag serie non va toccato su una stagione"
by_num = {s["seasonNumber"]: s["monitored"] for s in one["seasons"]}
assert by_num == {0: True, 1: True, 2: False}, by_num

# --- episode_ids ----------------------------------------------------------
EPISODES = [
    {"id": 10, "seasonNumber": 1, "episodeNumber": 1, "title": "Good News",
     "monitored": True, "episodeFile": {"path": "/media/series/Severance/S01/e01.mkv"}},
    {"id": 11, "seasonNumber": 1, "episodeNumber": 2, "title": "Half Loop",
     "monitored": False},
    {"id": 12, "seasonNumber": 2, "episodeNumber": 1, "title": "Hello",
     "monitored": True, "episodeFile": None},
    {"seasonNumber": 2},          # senza id → scartato
]
assert arr.episode_ids(EPISODES) == [10, 11, 12]
assert arr.episode_ids(EPISODES, 1) == [10, 11]
assert arr.episode_ids(EPISODES, 2) == [12]
assert arr.episode_ids(None) == []

# --- episodes_to_dicts ----------------------------------------------------
eps = arr.episodes_to_dicts(EPISODES)
assert len(eps) == 3, eps
assert eps[0] == {
    "id": 10, "season_number": 1, "episode_number": 1, "title": "Good News",
    "monitored": True, "path": "/media/series/Severance/S01/e01.mkv",
}, eps[0]
assert eps[1]["path"] == "", "episodio senza file → path vuoto"
assert eps[2]["path"] == "", "episodeFile None → path vuoto"

print("OK")
```

- [ ] **Step 2: Lanciarlo e verificare che fallisca**

Run: `python "$SCRATCH/verify_arr_unmonitor.py"`
Expected: `AttributeError: module 'unit3dprep.web.arr' has no attribute 'series_unmonitored_payload'`

- [ ] **Step 3: Aggiungere le funzioni pure**

In `unit3dprep/web/arr.py`, subito dopo `series_index` (prima di `def error_msg`), inserisci:

```python
def series_unmonitored_payload(
    series: dict[str, Any], season_number: int | None = None,
) -> dict[str, Any]:
    """Copy of a Sonarr series object with monitoring switched off.

    ``season_number`` at ``None`` switches off the whole series: the series flag
    plus every season. With a season number it switches off only that season and
    leaves the series flag alone. The input object is never mutated.
    """
    out = dict(series)
    seasons: list[Any] = []
    for season in series.get("seasons") or []:
        if isinstance(season, dict):
            s = dict(season)
            if season_number is None or s.get("seasonNumber") == season_number:
                s["monitored"] = False
            seasons.append(s)
        else:
            seasons.append(season)
    out["seasons"] = seasons
    if season_number is None:
        out["monitored"] = False
    return out


def episode_ids(payload: Any, season_number: int | None = None) -> list[int]:
    """Episode ids, optionally filtered to one season."""
    ids: list[int] = []
    for ep in payload if isinstance(payload, list) else []:
        if not isinstance(ep, dict) or not isinstance(ep.get("id"), int):
            continue
        if season_number is not None and ep.get("seasonNumber") != season_number:
            continue
        ids.append(ep["id"])
    return ids


def episodes_to_dicts(payload: Any) -> list[dict[str, Any]]:
    """Compact episode shape for the frontend.

    ``path`` is the file on disk: it is the key the detail panel uses to match a
    library episode row to its Sonarr episode. Empty when Sonarr has no file for
    that episode.
    """
    out: list[dict[str, Any]] = []
    for ep in payload if isinstance(payload, list) else []:
        if not isinstance(ep, dict) or not isinstance(ep.get("id"), int):
            continue
        f = ep.get("episodeFile")
        raw_path = f.get("path") if isinstance(f, dict) else ""
        out.append({
            "id": ep["id"],
            "season_number": ep.get("seasonNumber"),
            "episode_number": ep.get("episodeNumber"),
            "title": str(ep.get("title") or ""),
            "monitored": bool(ep.get("monitored")),
            "path": norm_path(raw_path or ""),
        })
    return out
```

- [ ] **Step 4: Aggiungere le mutazioni HTTP**

In fondo a `unit3dprep/web/arr.py`, dopo `test_connection`, aggiungi:

```python
# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

async def fetch_series(series_id: int) -> dict[str, Any]:
    data = await _get_json("sonarr", f"/api/v3/series/{series_id}")
    return data if isinstance(data, dict) else {}


async def fetch_episodes(series_id: int) -> list[dict[str, Any]]:
    data = await _get_json(
        "sonarr", "/api/v3/episode",
        {"seriesId": series_id, "includeEpisodeFile": "true"},
    )
    return data if isinstance(data, list) else []


async def unmonitor_movies(ids: list[int]) -> int:
    """Switch off one or many movies in a single call to the editor endpoint."""
    if not ids:
        return 0
    await _put_json("radarr", "/api/v3/movie/editor", {"movieIds": ids, "monitored": False})
    invalidate_cache()
    return len(ids)


async def unmonitor_episode_ids(ids: list[int]) -> int:
    if not ids:
        return 0
    await _put_json("sonarr", "/api/v3/episode/monitor", {"episodeIds": ids, "monitored": False})
    invalidate_cache()
    return len(ids)


async def unmonitor_series(series_id: int, season_number: int | None = None) -> int:
    """Switch off a whole series or a single season, cascading to its episodes.

    Returns how many episodes were switched off.
    """
    series = await fetch_series(series_id)
    await _put_json(
        "sonarr", f"/api/v3/series/{series_id}",
        series_unmonitored_payload(series, season_number),
    )
    ids = episode_ids(await fetch_episodes(series_id), season_number)
    if ids:
        await _put_json(
            "sonarr", "/api/v3/episode/monitor",
            {"episodeIds": ids, "monitored": False},
        )
    invalidate_cache()
    return len(ids)
```

- [ ] **Step 5: Rilanciare lo script e verificare che passi**

Run: `python "$SCRATCH/verify_arr_unmonitor.py"`
Expected: `OK`

- [ ] **Step 6: Rilanciare anche la verifica del Task 2 (nessuna regressione)**

Run: `python "$SCRATCH/verify_arr_index.py"`
Expected: `OK`

- [ ] **Step 7: Syntax check**

Run: `python -m py_compile unit3dprep/web/arr.py`
Expected: nessun output, exit 0

- [ ] **Step 8: Commit**

```bash
git add unit3dprep/web/arr.py
git commit -m "feat(arr): rimozione del monitoraggio con cascata su stagioni ed episodi"
```

---

## Task 4: Router `api/arr.py` e registrazione

**Files:**
- Create: `unit3dprep/web/api/arr.py`
- Modify: `unit3dprep/web/app.py`
- Modify: `unit3dprep/web/api/settings.py`

- [ ] **Step 1: Scrivere lo script di verifica**

Crea `$SCRATCH/verify_arr_router.py`:

```python
import os, sys, tempfile
sys.path.insert(0, r"C:\Users\sidot\Documents\Github\itatorrents-seeding")
os.environ["U3DP_ENV_PATH"] = os.path.join(tempfile.gettempdir(), "u3dp_verify.env")

from unit3dprep.web.api import arr as arr_api

routes = {(r.path, tuple(sorted(m for m in r.methods if m in {"GET", "POST"})))
          for r in arr_api.router.routes}

expected = {
    ("/api/arr/status", ("GET",)),
    ("/api/arr/test", ("GET",)),
    ("/api/arr/series/{series_id}/episodes", ("GET",)),
    ("/api/arr/unmonitor", ("POST",)),
    ("/api/arr/unmonitor/bulk", ("POST",)),
}
missing = expected - routes
assert not missing, f"rotte mancanti: {missing}"

# Il body accetta i quattro kind e ha default sensati.
body = arr_api.UnmonitorBody(kind="movie", path="/media/movies/X")
assert body.season_number is None and body.episode_ids == []

# Il router deve essere registrato nell'app.
from unit3dprep.web import app as app_mod
paths = {r.path for r in app_mod.app.routes}
assert any(p.endswith("/api/arr/status") for p in paths), "router non registrato in app.py"

print("OK")
```

- [ ] **Step 2: Lanciarlo e verificare che fallisca**

Run: `python "$SCRATCH/verify_arr_router.py"`
Expected: `ModuleNotFoundError: No module named 'unit3dprep.web.api.arr'`

- [ ] **Step 3: Creare `unit3dprep/web/api/arr.py`**

```python
"""Radarr / Sonarr endpoints consumed by the library view."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import arr, logbuf

router = APIRouter(prefix="/api", tags=["arr"])


class UnmonitorBody(BaseModel):
    kind: str
    path: str = ""
    season_number: int | None = None
    episode_ids: list[int] = []


class BulkBody(BaseModel):
    paths: list[str] = []


@router.get("/arr/status")
async def arr_status(force: int = 0):
    """path → monitored index for both instances, cached 60 s."""
    return JSONResponse(await arr.build_index(force=bool(force)))


@router.get("/arr/test")
async def arr_test(kind: str):
    return JSONResponse(await arr.test_connection(kind))


@router.get("/arr/series/{series_id}/episodes")
async def arr_series_episodes(series_id: int):
    if not arr.configured("sonarr"):
        raise HTTPException(400, "Sonarr non configurato.")
    try:
        raw = await arr.fetch_episodes(series_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, arr.error_msg(e)) from e
    return JSONResponse({"episodes": arr.episodes_to_dicts(raw)})


async def _resolve_and_unmonitor(body: UnmonitorBody) -> int:
    """Resolve the *arr id from the path and switch monitoring off. Returns the count."""
    index = await arr.build_index()
    key = arr.norm_path(body.path)

    if body.kind == "movie":
        entry = index["movies"].get(key)
        if not entry:
            raise HTTPException(404, "Film non trovato in Radarr.")
        return await arr.unmonitor_movies([entry["id"]])

    if body.kind in {"series", "season"}:
        entry = index["series"].get(key)
        if not entry:
            raise HTTPException(404, "Serie non trovata in Sonarr.")
        if body.kind == "season" and body.season_number is None:
            raise HTTPException(400, "season_number mancante.")
        season = body.season_number if body.kind == "season" else None
        return await arr.unmonitor_series(entry["id"], season)

    if body.kind == "episodes":
        if not body.episode_ids:
            raise HTTPException(400, "episode_ids mancante.")
        return await arr.unmonitor_episode_ids(body.episode_ids)

    raise HTTPException(400, f"kind non valido: {body.kind}")


@router.post("/arr/unmonitor")
async def arr_unmonitor(body: UnmonitorBody):
    try:
        changed = await _resolve_and_unmonitor(body)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logbuf.emit("error", f"Rimozione monitoraggio fallita: {e}", "arr", source="arr")
        raise HTTPException(502, arr.error_msg(e)) from e
    target = body.path or f"{len(body.episode_ids)} episodi"
    logbuf.emit("info", f"Monitoraggio rimosso ({body.kind}): {target}", "arr", source="arr")
    return JSONResponse({"ok": True, "changed": changed})


@router.post("/arr/unmonitor/bulk")
async def arr_unmonitor_bulk(body: BulkBody):
    """Switch monitoring off across many paths.

    Movies go out in a single call to Radarr's editor endpoint; each series gets
    its own cascade. One failure does not stop the others — it lands in
    ``failed``.
    """
    index = await arr.build_index()
    movie_ids: list[int] = []
    series_targets: list[tuple[str, int]] = []
    failed: list[dict[str, str]] = []

    for raw_path in body.paths:
        key = arr.norm_path(raw_path)
        movie = index["movies"].get(key)
        if movie:
            movie_ids.append(movie["id"])
            continue
        show = index["series"].get(key)
        if show:
            series_targets.append((raw_path, show["id"]))
            continue
        failed.append({"path": raw_path, "error": "Non trovato in Radarr/Sonarr."})

    done = 0
    if movie_ids:
        try:
            await arr.unmonitor_movies(movie_ids)
            done += len(movie_ids)
        except Exception as e:  # noqa: BLE001
            failed.append({"path": f"{len(movie_ids)} film", "error": arr.error_msg(e)})
    for path, series_id in series_targets:
        try:
            await arr.unmonitor_series(series_id)
            done += 1
        except Exception as e:  # noqa: BLE001
            failed.append({"path": path, "error": arr.error_msg(e)})

    level = "warn" if failed else "info"
    logbuf.emit(
        level, f"Monitoraggio in blocco: {done} rimossi, {len(failed)} falliti",
        "arr", source="arr",
    )
    for f in failed:
        logbuf.emit("warn", f"  {f['path']}: {f['error']}", "arr", source="arr")
    return JSONResponse({"ok": True, "done": done, "failed": failed})
```

- [ ] **Step 4: Registrare il router in `app.py`**

In `unit3dprep/web/app.py` sostituisci:

```python
from .api import (
    auth as auth_api,
    fs as fs_api,
```

con:

```python
from .api import (
    arr as arr_api,
    auth as auth_api,
    fs as fs_api,
```

- [ ] **Step 5: Aggiungere il router alla lista di `include_router`**

Nella stessa `app.py`, la tupla di router termina così:

```python
    reseed_api.router,
    search_api.router,
```

Sostituiscila con:

```python
    arr_api.router,
    reseed_api.router,
    search_api.router,
```

- [ ] **Step 6: Invalidare la cache quando cambiano le impostazioni**

`configured()` viene valutato solo su cache miss e il risultato finisce dentro il
payload in cache. Senza questo, dopo che l'utente ha compilato URL e API key il
"Test connessione" riesce ma la libreria continua a riportare `configured: false`
per un minuto.

In `unit3dprep/web/api/settings.py`, sostituisci:

```python
from .. import config
from ...media import media_root, seedings_root
```

con:

```python
from .. import arr, config
from ...media import media_root, seedings_root
```

Poi sostituisci:

```python
@router.put("/settings")
async def put_settings(incoming: dict):
    existing = config.load()
    merged = {**existing, **config.merge_secrets(existing, incoming)}
    config.save(merged)
    return JSONResponse({"ok": True, "config": config.mask_secrets(merged)})
```

con:

```python
_ARR_KEYS = ("W_RADARR_URL", "W_RADARR_APIKEY", "W_SONARR_URL", "W_SONARR_APIKEY")


@router.put("/settings")
async def put_settings(incoming: dict):
    existing = config.load()
    merged = {**existing, **config.merge_secrets(existing, incoming)}
    config.save(merged)
    # The *arr index caches `configured` alongside the data, so new credentials
    # would stay invisible to the library for a full TTL without this.
    if any(existing.get(k) != merged.get(k) for k in _ARR_KEYS):
        arr.invalidate_cache()
    return JSONResponse({"ok": True, "config": config.mask_secrets(merged)})
```

- [ ] **Step 7: Rilanciare lo script e verificare che passi**

Run: `python "$SCRATCH/verify_arr_router.py"`
Expected: `OK`

- [ ] **Step 8: Syntax check**

Run: `python -m py_compile unit3dprep/web/api/arr.py unit3dprep/web/app.py unit3dprep/web/api/settings.py`
Expected: nessun output, exit 0

- [ ] **Step 9: Commit**

```bash
git add unit3dprep/web/api/arr.py unit3dprep/web/app.py unit3dprep/web/api/settings.py
git commit -m "feat(api): endpoint di stato e rimozione del monitoraggio *arr"
```

---

## Task 5: Tipi frontend

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Aggiungere i tipi**

In `frontend/src/types.ts`, subito dopo la chiusura di `export interface LibraryItem { … }`
(la riga `}` che precede `export interface TrackerStatus`), inserisci:

```ts
export interface ArrEntry {
  id: number;
  monitored: boolean;
  title: string;
  /** Series only: season number (as a string) → monitored. */
  seasons?: Record<string, boolean>;
}

export interface ArrIndex {
  configured: { radarr: boolean; sonarr: boolean };
  movies: Record<string, ArrEntry>;
  series: Record<string, ArrEntry>;
  errors: { radarr: string | null; sonarr: string | null };
}

export interface ArrEpisode {
  id: number;
  season_number: number | null;
  episode_number: number | null;
  title: string;
  monitored: boolean;
  /** File on disk: the key matching this to a library episode row. */
  path: string;
}
```

- [ ] **Step 2: Build per verificare che compili**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore TypeScript

- [ ] **Step 3: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`
Expected: prompt nella radice. La working directory è condivisa fra i tool: senza
questo passo i comandi git successivi partono da `frontend/`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat(types): tipi dell'indice Radarr/Sonarr"
```

---

## Task 6: Chiavi i18n

**Files:**
- Modify: `frontend/src/i18n/locales/en.ts`
- Modify: `frontend/src/i18n/locales/it.ts`

Tutte le chiavi si aggiungono ora, in un colpo solo: `Catalog = typeof en` impone la
parità fra i due cataloghi, quindi aggiungerle a spizzichi produce errori TypeScript
a ogni task successivo.

- [ ] **Step 1: Aggiungere il namespace `arr` a `en.ts`**

In `frontend/src/i18n/locales/en.ts`, dopo la chiusura del blocco `library: { … },`
(la riga `},` che segue `bulkScanLangsDone`), inserisci:

```ts
  arr: {
    monitoredBadge: 'monitored',
    unmonitorMovie: 'Stop monitoring (Radarr)',
    unmonitorSeries: 'Stop monitoring series',
    unmonitorSeason: 'Stop monitoring season',
    unmonitorEpisode: 'Stop monitoring episode',
    unmonitored: 'Monitoring removed',
    bulkUnmonitor: 'Stop monitoring',
    bulkUnmonitorDone: 'Monitoring removed: {{done}} done, {{failed}} failed',
    bulkUnmonitorFail: 'Could not reach Radarr/Sonarr',
    statusError: 'Radarr/Sonarr unreachable: {{msg}}',
  },
```

- [ ] **Step 2: Aggiungere le chiavi `settings.arr*` a `en.ts`**

Nello stesso file, dentro il blocco `settings: { … }`, subito dopo la riga
`navConsole: 'Console',`, inserisci:

```ts
    navArr: 'Radarr / Sonarr',
    arrIntro: 'Remove monitoring from the library once you already have the version you want.',
    arrTest: 'Test connection',
    arrTesting: 'Testing…',
    arrTestOk: 'OK — {{name}} v{{version}}',
    arrTestFail: 'Failed: {{msg}}',
```

- [ ] **Step 3: Aggiungere il namespace `arr` a `it.ts`**

In `frontend/src/i18n/locales/it.ts`, nella stessa posizione (dopo la chiusura del
blocco `library`), inserisci:

```ts
  arr: {
    monitoredBadge: 'monitorato',
    unmonitorMovie: 'Rimuovi monitoraggio (Radarr)',
    unmonitorSeries: 'Rimuovi monitoraggio serie',
    unmonitorSeason: 'Rimuovi monitoraggio stagione',
    unmonitorEpisode: 'Rimuovi monitoraggio episodio',
    unmonitored: 'Monitoraggio rimosso',
    bulkUnmonitor: 'Rimuovi monitoraggio',
    bulkUnmonitorDone: 'Monitoraggio rimosso: {{done}} ok, {{failed}} falliti',
    bulkUnmonitorFail: 'Radarr/Sonarr non raggiungibili',
    statusError: 'Radarr/Sonarr non raggiungibili: {{msg}}',
  },
```

- [ ] **Step 4: Aggiungere le chiavi `settings.arr*` a `it.ts`**

Dentro il blocco `settings: { … }`, subito dopo `navConsole: 'Console',`:

```ts
    navArr: 'Radarr / Sonarr',
    arrIntro: 'Rimuovi il monitoraggio dalla libreria quando hai già la versione che ti serve.',
    arrTest: 'Test connessione',
    arrTesting: 'Verifica in corso…',
    arrTestOk: 'OK — {{name}} v{{version}}',
    arrTestFail: 'Errore: {{msg}}',
```

- [ ] **Step 5: Build per verificare la parità dei cataloghi**

Run: `cd frontend && npm run build`
Expected: build completata. Un errore `Property 'arr' is missing in type` significa
che una chiave è stata aggiunta a un solo catalogo.

- [ ] **Step 6: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/locales/en.ts frontend/src/i18n/locales/it.ts
git commit -m "i18n: etichette per il monitoraggio Radarr/Sonarr"
```

---

## Task 7: `ICON_BTN` condiviso in primitives

Il pulsante quadrato a sola icona serve sia a LibraryView sia al nuovo componente.
Vive come costante privata in LibraryView: va spostato in `primitives.tsx` per evitare
di duplicarlo (LibraryView importerà `ArrMonitor`, quindi non può esportarlo lei senza
creare un ciclo di import).

**Files:**
- Modify: `frontend/src/components/primitives.tsx`
- Modify: `frontend/src/views/LibraryView.tsx`

- [ ] **Step 1: Aggiungere `ICON_BTN` a primitives**

In fondo a `frontend/src/components/primitives.tsx` aggiungi:

```tsx
// Compact square icon button: season header toolbar and other tight actions.
export const ICON_BTN = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 26, height: 22, borderRadius: 4, cursor: 'pointer',
  border: '1px solid var(--border)', background: 'transparent',
  padding: 0, flexShrink: 0,
} as const;
```

- [ ] **Step 2: Rimuovere la costante locale da LibraryView**

In `frontend/src/views/LibraryView.tsx` elimina questo blocco (righe 27-33 circa):

```tsx
// Compact square icon button used in the season header action toolbar.
const seasonIconBtn = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 26, height: 22, borderRadius: 4, cursor: 'pointer',
  border: '1px solid var(--border)', background: 'transparent',
  padding: 0, flexShrink: 0,
} as const;
```

- [ ] **Step 3: Importarla da primitives**

Sostituisci la riga di import:

```tsx
import { LangChip, SubChip, Badge, LoadMore } from '../components/primitives';
```

con:

```tsx
import { LangChip, SubChip, Badge, LoadMore, ICON_BTN } from '../components/primitives';
```

- [ ] **Step 4: Aggiornare le tre occorrenze**

Sostituisci ogni `...seasonIconBtn` con `...ICON_BTN`. Sono tre, tutte nella forma
`style={{ ...seasonIconBtn, … }}`: nel pulsante Upload dell'header stagione, in
`MarkUploadedBtn` variante `icon`, in `ToCheckBtn` variante `icon`.

Verifica che non ne restino:

Run: `grep -n "seasonIconBtn" frontend/src/views/LibraryView.tsx`
Expected: nessun output

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore

- [ ] **Step 6: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/primitives.tsx frontend/src/views/LibraryView.tsx
git commit -m "refactor(ui): ICON_BTN condiviso in primitives"
```

---

## Task 8: Componente `ArrMonitor`

**Files:**
- Create: `frontend/src/components/ArrMonitor.tsx`

- [ ] **Step 1: Creare il componente**

```tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bookmark, BookmarkX } from 'lucide-react';
import { api } from '../api';
import { Badge, ICON_BTN } from './primitives';

/** What a monitoring removal acts on. */
export type ArrTarget =
  | { kind: 'movie'; path: string }
  | { kind: 'series'; path: string }
  | { kind: 'season'; path: string; seasonNumber: number }
  | { kind: 'episodes'; episodeIds: number[] };

/**
 * Shown only when the item is monitored: anything unmonitored, or absent from
 * Radarr/Sonarr, renders nothing — so the grid highlights exactly what is left
 * to do.
 */
export function MonitorBadge({ monitored }: { monitored?: boolean }) {
  const { t } = useTranslation();
  if (!monitored) return null;
  return (
    <Badge color="var(--blue)" bg="rgba(74,144,226,0.15)">
      <Bookmark size={8} fill="var(--blue)" style={{ marginRight: 2, verticalAlign: '-1px' }} />
      {t('arr.monitoredBadge')}
    </Badge>
  );
}

function labelKeyFor(kind: ArrTarget['kind']): string {
  if (kind === 'movie') return 'arr.unmonitorMovie';
  if (kind === 'series') return 'arr.unmonitorSeries';
  if (kind === 'season') return 'arr.unmonitorSeason';
  return 'arr.unmonitorEpisode';
}

export function UnmonitorBtn({
  target, variant = 'full', onDone,
}: {
  target: ArrTarget;
  variant?: 'full' | 'icon' | 'chip';
  onDone?: () => void;
}) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const title = t(labelKeyFor(target.kind));

  const run = async () => {
    if (done || busy) return;
    setBusy(true);
    try {
      await api.post('/api/arr/unmonitor', {
        kind: target.kind,
        path: 'path' in target ? target.path : '',
        season_number: target.kind === 'season' ? target.seasonNumber : null,
        episode_ids: target.kind === 'episodes' ? target.episodeIds : [],
      });
      setDone(true);
      onDone?.();
    } catch { /* the failure is already in the server-side logs */ }
    setBusy(false);
  };

  if (variant === 'icon') {
    return (
      <button
        onClick={run}
        disabled={done || busy}
        title={title}
        aria-label={title}
        style={{
          ...ICON_BTN,
          borderColor: done ? 'var(--green)' : 'var(--border)',
          color: done ? 'var(--green)' : 'var(--fg-3)',
        }}
      ><BookmarkX size={13} /></button>
    );
  }

  if (variant === 'chip') {
    return (
      <button
        onClick={run}
        disabled={done || busy}
        title={title}
        style={{
          background: 'transparent',
          border: '1px solid var(--border)', borderRadius: 4,
          padding: '2px 5px', fontSize: 9, fontWeight: 700,
          color: done ? 'var(--green)' : 'var(--fg-3)',
          cursor: done || busy ? 'default' : 'pointer',
          fontFamily: 'var(--font-display)',
          minWidth: 22, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >{done ? '✓' : <BookmarkX size={10} />}</button>
    );
  }

  return (
    <button
      onClick={run}
      disabled={done || busy}
      style={{
        width: '100%', background: 'transparent',
        border: '1px solid var(--border)', borderRadius: 6,
        padding: 8, fontSize: 11, fontWeight: 600,
        color: done ? 'var(--green)' : 'var(--fg-2)',
        cursor: done || busy ? 'default' : 'pointer',
        fontFamily: 'var(--font-display)', marginBottom: 6,
      }}
    >{done ? t('arr.unmonitored') : title}</button>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore

- [ ] **Step 3: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ArrMonitor.tsx
git commit -m "feat(ui): badge e pulsante di rimozione del monitoraggio"
```

---

## Task 9: Sezione Impostazioni

**Files:**
- Modify: `frontend/src/views/SettingsView.tsx`

- [ ] **Step 1: Aggiungere l'icona all'import di lucide**

Sostituisci:

```tsx
import {
  Activity, HardDrive, Sliders, Image as ImageIcon, Folder as FolderIcon,
  GitBranch, Terminal, CheckCircle, Languages, Tag,
  RefreshCw, ChevronDown, ExternalLink, Box, Package,
} from 'lucide-react';
```

con:

```tsx
import {
  Activity, HardDrive, Sliders, Image as ImageIcon, Folder as FolderIcon,
  GitBranch, Terminal, CheckCircle, Languages, Tag, Bookmark,
  RefreshCw, ChevronDown, ExternalLink, Box, Package,
} from 'lucide-react';
```

- [ ] **Step 2: Estendere il tipo `Section` e la lista `SECTIONS`**

Sostituisci:

```tsx
type Section = 'tracker' | 'client' | 'prefs' | 'imghost' | 'paths' | 'seeding' | 'version' | 'console' | 'interface';
```

con:

```tsx
type Section = 'tracker' | 'client' | 'prefs' | 'imghost' | 'paths' | 'seeding' | 'arr' | 'version' | 'console' | 'interface';
```

Poi sostituisci:

```tsx
  { id: 'seeding',  labelKey: 'settings.navSeeding',  icon: GitBranch },
```

con:

```tsx
  { id: 'seeding',  labelKey: 'settings.navSeeding',  icon: GitBranch },
  { id: 'arr',      labelKey: 'settings.navArr',      icon: Bookmark },
```

- [ ] **Step 3: Montare la sezione**

Sostituisci:

```tsx
          {section === 'version' && <VersionSection />}
```

con:

```tsx
          {section === 'arr' && <ArrSection cfg={cfg} set={set} isMobile={isMobile} />}
          {section === 'version' && <VersionSection />}
```

- [ ] **Step 4: Scrivere la sezione**

In fondo a `SettingsView.tsx` aggiungi:

```tsx
function ArrTestBtn({ kind }: { kind: 'radarr' | 'sonarr' }) {
  const { t } = useTranslation();
  const [state, setState] = useState<{ busy: boolean; msg: string; ok: boolean }>(
    { busy: false, msg: '', ok: false },
  );
  const run = async () => {
    setState({ busy: true, msg: '', ok: false });
    try {
      const r = await api.get<{ ok: boolean; version?: string; instance_name?: string; error?: string }>(
        `/api/arr/test?kind=${kind}`,
      );
      setState(r.ok
        ? { busy: false, ok: true,
            msg: t('settings.arrTestOk', { name: r.instance_name || kind, version: r.version || '?' }) }
        : { busy: false, ok: false, msg: t('settings.arrTestFail', { msg: r.error || '' }) });
    } catch (e) {
      setState({ busy: false, ok: false, msg: t('settings.arrTestFail', { msg: String(e) }) });
    }
  };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
      <button
        onClick={run}
        disabled={state.busy}
        style={{
          background: 'transparent', border: '1px solid var(--border)',
          borderRadius: 6, padding: '6px 12px', fontSize: 11, fontWeight: 600,
          color: 'var(--fg-2)', cursor: state.busy ? 'default' : 'pointer',
          fontFamily: 'var(--font-display)',
        }}
      >{state.busy ? t('settings.arrTesting') : t('settings.arrTest')}</button>
      {state.msg && (
        <span style={{
          fontSize: 11, fontFamily: 'var(--font-mono)',
          color: state.ok ? 'var(--green)' : 'var(--red)',
        }}>{state.msg}</span>
      )}
    </div>
  );
}

function ArrSection({ cfg, set, isMobile }: { cfg: Cfg; set: SetFn; isMobile?: boolean }) {
  const { t } = useTranslation();
  const grid2: React.CSSProperties = {
    display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10, marginBottom: 10,
  };
  return (
    <>
      <div style={{
        fontSize: 11, color: 'var(--fg-4)', fontFamily: 'var(--font-display)',
        marginBottom: 12,
      }}>{t('settings.arrIntro')}</div>

      <div style={{ ...GROUP_LABEL, marginTop: 0 }}>Radarr</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="W_RADARR_URL" label="W_RADARR_URL" />
        <Field cfg={cfg} set={set} k="W_RADARR_APIKEY" label="W_RADARR_APIKEY" masked />
      </div>
      <ArrTestBtn kind="radarr" />

      <div style={GROUP_LABEL}>Sonarr</div>
      <div style={grid2}>
        <Field cfg={cfg} set={set} k="W_SONARR_URL" label="W_SONARR_URL" />
        <Field cfg={cfg} set={set} k="W_SONARR_APIKEY" label="W_SONARR_APIKEY" masked />
      </div>
      <ArrTestBtn kind="sonarr" />
    </>
  );
}
```

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore

- [ ] **Step 6: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/SettingsView.tsx
git commit -m "feat(settings): sezione Radarr/Sonarr con test di connessione"
```

---

## Task 10: LibraryView — caricamento indice e badge sulle card

**Files:**
- Modify: `frontend/src/views/LibraryView.tsx`

- [ ] **Step 1: Estendere gli import**

Sostituisci:

```tsx
import type { Category, LibraryItem, Season, SeasonStatus, SeriesStatus, WizardCtx } from '../types';
```

con:

```tsx
import type {
  ArrEntry, ArrEpisode, ArrIndex,
  Category, LibraryItem, Season, SeasonStatus, SeriesStatus, WizardCtx,
} from '../types';
```

Poi, subito sotto la riga di import di `useIncremental`, aggiungi:

```tsx
import { MonitorBadge, UnmonitorBtn } from '../components/ArrMonitor';
```

- [ ] **Step 2: Caricare l'indice**

Nel corpo del componente `LibraryView`, subito dopo
`const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());`,
aggiungi:

```tsx
  // Radarr/Sonarr index. Loaded after the grid and merged by path, so the
  // library is unaffected when either instance is slow or down.
  const [arrIndex, setArrIndex] = useState<ArrIndex | null>(null);
  const loadArr = () => {
    api.get<ArrIndex>('/api/arr/status')
      .then(setArrIndex)
      .catch(() => setArrIndex(null));
  };
  useEffect(() => { loadArr(); }, []);

  const arrEntryFor = (it: LibraryItem): ArrEntry | undefined =>
    it.kind === 'movie' ? arrIndex?.movies[it.path] : arrIndex?.series[it.path];

  const arrEnabled = !!(arrIndex?.configured.radarr || arrIndex?.configured.sonarr);
  const arrError = arrIndex?.errors.radarr || arrIndex?.errors.sonarr || '';
```

- [ ] **Step 3: Mostrare il badge sulla card**

Nella griglia, sostituisci:

```tsx
                    {(item.any_to_check || item.to_check) && (
                      <Badge color="var(--yellow)" bg="var(--yellow-dim)">
                        <Flag size={8} fill="var(--yellow)" style={{ marginRight: 2, verticalAlign: '-1px' }} />
                        {t('library.toCheckBadge')}
                      </Badge>
                    )}
```

con:

```tsx
                    {(item.any_to_check || item.to_check) && (
                      <Badge color="var(--yellow)" bg="var(--yellow-dim)">
                        <Flag size={8} fill="var(--yellow)" style={{ marginRight: 2, verticalAlign: '-1px' }} />
                        {t('library.toCheckBadge')}
                      </Badge>
                    )}
                    <MonitorBadge monitored={arrEntryFor(item)?.monitored} />
```

- [ ] **Step 4: Mostrare l'errore di raggiungibilità**

L'avviso va come primo figlio della griglia, così occupa l'intera riga.
Sostituisci:

```tsx
          overflowY: 'auto', alignContent: 'start',
        }}>
          {visible.map((item) => {
```

con:

```tsx
          overflowY: 'auto', alignContent: 'start',
        }}>
          {arrError && (
            <div style={{
              gridColumn: '1/-1',
              fontSize: 11, fontFamily: 'var(--font-display)',
              color: 'var(--yellow)', background: 'var(--yellow-dim)',
              border: '1px solid var(--yellow)', borderRadius: 6,
              padding: '6px 10px', marginBottom: 8,
            }}>{t('arr.statusError', { msg: arrError })}</div>
          )}
          {visible.map((item) => {
```

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore

- [ ] **Step 6: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/LibraryView.tsx
git commit -m "feat(library): badge di monitoraggio sulle card"
```

---

## Task 11: LibraryView — pannello dettaglio

**Files:**
- Modify: `frontend/src/views/LibraryView.tsx`

- [ ] **Step 1: Passare l'indice al pannello**

Sostituisci il montaggio di `DetailPanel`:

```tsx
          <DetailPanel
            item={selected}
            category={category}
            onStart={startWizard}
            onClose={() => setSelected(null)}
            onEditTmdb={() => setTmdbEditOpen(true)}
            onRescan={(langs) => setSelected((prev) => prev ? { ...prev, langs, lang_scanned: true } : prev)}
            onMarked={() => reloadKeepSelection(category)}
            isMobile={isMobile}
          />
```

con:

```tsx
          <DetailPanel
            item={selected}
            category={category}
            onStart={startWizard}
            onClose={() => setSelected(null)}
            onEditTmdb={() => setTmdbEditOpen(true)}
            onRescan={(langs) => setSelected((prev) => prev ? { ...prev, langs, lang_scanned: true } : prev)}
            onMarked={() => reloadKeepSelection(category)}
            arrEntry={arrEntryFor(selected)}
            onArrChanged={loadArr}
            isMobile={isMobile}
          />
```

- [ ] **Step 2: Accettare le nuove prop in `DetailPanel`**

Sostituisci:

```tsx
function DetailPanel({
  item, category, onStart, onClose, onEditTmdb, onRescan, onMarked, isMobile,
}: {
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onClose: () => void;
  onEditTmdb: () => void;
  onRescan?: (langs: string[]) => void;
  onMarked?: () => void;
  isMobile?: boolean;
}) {
```

con:

```tsx
function DetailPanel({
  item, category, onStart, onClose, onEditTmdb, onRescan, onMarked,
  arrEntry, onArrChanged, isMobile,
}: {
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onClose: () => void;
  onEditTmdb: () => void;
  onRescan?: (langs: string[]) => void;
  onMarked?: () => void;
  arrEntry?: ArrEntry;
  onArrChanged?: () => void;
  isMobile?: boolean;
}) {
```

- [ ] **Step 3: Caricare gli episodi Sonarr nel pannello**

Nel corpo di `DetailPanel`, insieme agli altri `useState`, aggiungi:

```tsx
  // Sonarr episodes: a single call when opening a series that is in the index.
  // Needed to map each episode row to its Sonarr id.
  const [arrEpisodes, setArrEpisodes] = useState<ArrEpisode[]>([]);
  useEffect(() => {
    setArrEpisodes([]);
    if (item.kind !== 'series' || !arrEntry?.id) return;
    let alive = true;
    api.get<{ episodes: ArrEpisode[] }>(`/api/arr/series/${arrEntry.id}/episodes`)
      .then((r) => { if (alive) setArrEpisodes(r.episodes); })
      .catch(() => { if (alive) setArrEpisodes([]); });
    return () => { alive = false; };
  }, [item.kind, arrEntry?.id]);
```

- [ ] **Step 4: Pulsante a livello film**

Sostituisci:

```tsx
            <MarkUploadedBtn category={category} name={item.name} onMarked={onMarked} />
            <ToCheckBtn
              category={category}
              name={item.name}
              flagged={!!item.to_check}
              onToggled={onMarked}
            />
            <RescanLangsBtn category={category} name={item.name} onRescan={onRescan} />
          </>
        )}
```

con:

```tsx
            <MarkUploadedBtn category={category} name={item.name} onMarked={onMarked} />
            <ToCheckBtn
              category={category}
              name={item.name}
              flagged={!!item.to_check}
              onToggled={onMarked}
            />
            {arrEntry?.monitored && (
              <UnmonitorBtn
                target={{ kind: 'movie', path: item.path }}
                onDone={onArrChanged}
              />
            )}
            <RescanLangsBtn category={category} name={item.name} onRescan={onRescan} />
          </>
        )}
```

- [ ] **Step 5: Pulsante a livello serie**

Sostituisci:

```tsx
            <ToCheckBtn
              category={category}
              name={item.name}
              flagged={!!item.to_check}
              onToggled={onMarked}
              label={t('library.markSeriesToCheck')}
            />
            <RescanLangsBtn category={category} name={item.name} onRescan={onRescan} />
```

con:

```tsx
            <ToCheckBtn
              category={category}
              name={item.name}
              flagged={!!item.to_check}
              onToggled={onMarked}
              label={t('library.markSeriesToCheck')}
            />
            {arrEntry?.monitored && (
              <UnmonitorBtn
                target={{ kind: 'series', path: item.path }}
                onDone={onArrChanged}
              />
            )}
            <RescanLangsBtn category={category} name={item.name} onRescan={onRescan} />
```

- [ ] **Step 6: Passare i dati a `SeasonRow`**

Nel `.map` che monta le `SeasonRow`, sostituisci:

```tsx
                <SeasonRow
                  key={s.number}
                  season={s}
                  item={item}
                  category={category}
                  onStart={onStart}
                  onMarked={onMarked}
                  defaultOpen={idx === firstOpenIdx}
                  statusMeta={seriesStatus?.seasons?.[String(s.number)]}
                  statusReady={statusReady}
                />
```

con:

```tsx
                <SeasonRow
                  key={s.number}
                  season={s}
                  item={item}
                  category={category}
                  onStart={onStart}
                  onMarked={onMarked}
                  defaultOpen={idx === firstOpenIdx}
                  statusMeta={seriesStatus?.seasons?.[String(s.number)]}
                  statusReady={statusReady}
                  arrMonitored={arrEntry?.seasons?.[String(s.number)]}
                  arrEpisodes={arrEpisodes.filter((e) => e.season_number === s.number)}
                  onArrChanged={onArrChanged}
                />
```

- [ ] **Step 7: Accettare le nuove prop in `SeasonRow`**

Sostituisci:

```tsx
function SeasonRow({
  season, item, category, onStart, onMarked, defaultOpen, statusMeta, statusReady,
}: {
  season: Season;
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onMarked?: () => void;
  defaultOpen?: boolean;
  statusMeta?: SeasonStatus;
  statusReady?: boolean;
}) {
```

con:

```tsx
function SeasonRow({
  season, item, category, onStart, onMarked, defaultOpen, statusMeta, statusReady,
  arrMonitored, arrEpisodes = [], onArrChanged,
}: {
  season: Season;
  item: LibraryItem;
  category: Category;
  onStart: (kind: 'movie' | 'series' | 'episode', path: string, season?: Season) => void;
  onMarked?: () => void;
  defaultOpen?: boolean;
  statusMeta?: SeasonStatus;
  statusReady?: boolean;
  arrMonitored?: boolean;
  arrEpisodes?: ArrEpisode[];
  onArrChanged?: () => void;
}) {
```

- [ ] **Step 8: Badge e pulsante nell'header di stagione**

Nell'header di stagione, sostituisci:

```tsx
          {seasonToCheck && (
            <span style={{ marginLeft: 6 }}>
              <Badge color="var(--yellow)" bg="var(--yellow-dim)">
                <Flag size={8} fill="var(--yellow)" style={{ marginRight: 2, verticalAlign: '-1px' }} />
                {season.to_check
                  ? t('library.toCheckBadge')
                  : t('library.toCheckCount', { count: toCheckEpCount })}
              </Badge>
            </span>
          )}
```

con:

```tsx
          {seasonToCheck && (
            <span style={{ marginLeft: 6 }}>
              <Badge color="var(--yellow)" bg="var(--yellow-dim)">
                <Flag size={8} fill="var(--yellow)" style={{ marginRight: 2, verticalAlign: '-1px' }} />
                {season.to_check
                  ? t('library.toCheckBadge')
                  : t('library.toCheckCount', { count: toCheckEpCount })}
              </Badge>
            </span>
          )}
          {arrMonitored && (
            <span style={{ marginLeft: 6 }}><MonitorBadge monitored /></span>
          )}
```

Poi, nella toolbar delle icone, sostituisci:

```tsx
        <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
          {!season.already_uploaded && (
            <>
```

con:

```tsx
        <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
          {arrMonitored && (
            <UnmonitorBtn
              target={{ kind: 'season', path: item.path, seasonNumber: season.number }}
              variant="icon"
              onDone={onArrChanged}
            />
          )}
          {!season.already_uploaded && (
            <>
```

Il pulsante della stagione sta **fuori** dal ramo `!season.already_uploaded`: una
stagione già caricata sul tracker è proprio quella per cui vuoi spegnere il
monitoraggio.

- [ ] **Step 9: Chip sulla riga episodio**

Nella riga episodio, sostituisci:

```tsx
                {!vf.uploaded && (
                  <span onClick={(e) => e.stopPropagation()} style={{ flexShrink: 0, display: 'flex', gap: 3 }}>
                    <ToCheckBtn
                      category={category}
                      name={item.name}
                      episodePath={vf.path}
                      flagged={!!vf.to_check}
                      variant="chip"
                      onToggled={onMarked}
                    />
                    <MarkUploadedBtn
                      category={category}
                      name={item.name}
                      episodePath={vf.path}
                      variant="chip"
                      onMarked={onMarked}
                    />
                  </span>
                )}
```

con:

```tsx
                <span onClick={(e) => e.stopPropagation()} style={{ flexShrink: 0, display: 'flex', gap: 3 }}>
                  {!vf.uploaded && (
                    <>
                      <ToCheckBtn
                        category={category}
                        name={item.name}
                        episodePath={vf.path}
                        flagged={!!vf.to_check}
                        variant="chip"
                        onToggled={onMarked}
                      />
                      <MarkUploadedBtn
                        category={category}
                        name={item.name}
                        episodePath={vf.path}
                        variant="chip"
                        onMarked={onMarked}
                      />
                    </>
                  )}
                  {(() => {
                    const ep = arrEpisodes.find((e) => e.path === vf.path);
                    if (!ep?.monitored) return null;
                    return (
                      <UnmonitorBtn
                        target={{ kind: 'episodes', episodeIds: [ep.id] }}
                        variant="chip"
                        onDone={onArrChanged}
                      />
                    );
                  })()}
                </span>
```

- [ ] **Step 10: Build**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore

- [ ] **Step 11: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 12: Commit**

```bash
git add frontend/src/views/LibraryView.tsx
git commit -m "feat(library): rimozione monitoraggio su film, serie, stagione ed episodio"
```

---

## Task 12: LibraryView — azione di massa

**Files:**
- Modify: `frontend/src/views/LibraryView.tsx`

- [ ] **Step 1: Aggiungere l'azione**

Subito dopo la funzione `runBulkScanLangs`, aggiungi:

```tsx
  const runBulkUnmonitor = async () => {
    if (bulkBusy || selectedCount === 0) return;
    const targets = items.filter((it) => selectedPaths.has(it.path));
    if (targets.length === 0) return;
    setBulkBusy(true);
    setBulkToast(null);
    try {
      const r = await api.post<{ done: number; failed: { path: string; error: string }[] }>(
        '/api/arr/unmonitor/bulk',
        { paths: targets.map((it) => it.path) },
      );
      setBulkToast(t('arr.bulkUnmonitorDone', { done: r.done, failed: r.failed.length }));
    } catch {
      setBulkToast(t('arr.bulkUnmonitorFail'));
    }
    setBulkBusy(false);
    anchorRef.current = null;
    setSelectedPaths(new Set());
    setBulkMode(false);
    loadArr();
  };
```

- [ ] **Step 2: Aggiungere il pulsante alla barra bulk**

Nella barra azioni, sostituisci:

```tsx
          <button
            onClick={runBulkMark}
            disabled={!canBulkMark || bulkBusy}
            title={t('library.bulkOnlyMovies')}
```

con:

```tsx
          {arrEnabled && (
            <button
              onClick={runBulkUnmonitor}
              disabled={selectedCount === 0 || bulkBusy}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: 'transparent',
                border: '1px solid var(--border)', borderRadius: 6,
                padding: '7px 14px', fontSize: 12, fontWeight: 700,
                color: selectedCount > 0 && !bulkBusy ? 'var(--fg-1)' : 'var(--fg-3)',
                cursor: selectedCount > 0 && !bulkBusy ? 'pointer' : 'not-allowed',
                fontFamily: 'var(--font-display)',
              }}
            >
              {t('arr.bulkUnmonitor')}
            </button>
          )}
          <button
            onClick={runBulkMark}
            disabled={!canBulkMark || bulkBusy}
            title={t('library.bulkOnlyMovies')}
```

- [ ] **Step 3: Registrare `arr` fra le sorgenti dei log**

`LogsView.tsx` ha una lista `SOURCES` hardcoded. Le righe con `source="arr"` che
il backend già emette si vedono comunque (il filtro nasconde solo le sorgenti
presenti in `hiddenSources`), ma restano senza chip di filtro e senza colore.

In `frontend/src/components/../views/LogsView.tsx`, aggiungi una voce `arr` alla
lista `SOURCES` seguendo esattamente la forma delle otto già presenti (stesso tipo
di oggetto, stessa convenzione di etichetta e colore). Scegli un colore non ancora
usato dalle altre sorgenti.

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore

- [ ] **Step 5: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/LibraryView.tsx frontend/src/views/LogsView.tsx unit3dprep/web/dist
git commit -m "feat(library): rimozione monitoraggio sulla selezione multipla"
```

`unit3dprep/web/dist/` va committata: sul VPS non c'è Node, il wheel include la SPA
già buildata.

---

## Task 13: Documentazione e changelog

**Files:**
- Modify: `docs/configurazione.md`, `docs/configurazione.en.md`
- Modify: `docs/uso-web.md`, `docs/uso-web.en.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Righe nella tabella delle chiavi (italiano)**

In `docs/configurazione.md`, la tabella delle chiavi `W_*` termina con la riga
`| `W_DUPLICATE_CHECK` | `true` | Prima dell'hardlink interroga … |`. Aggiungi subito
sotto, prima della riga `---`:

```markdown
| `W_RADARR_URL` | *(vuoto)* | URL di Radarr, es. `http://127.0.0.1:7878`. Vuoto = integrazione disattivata. |
| `W_RADARR_APIKEY` | *(vuoto)* | API key di Radarr (Impostazioni → Generale → Sicurezza). |
| `W_SONARR_URL` | *(vuoto)* | URL di Sonarr, es. `http://127.0.0.1:8989`. Vuoto = integrazione disattivata. |
| `W_SONARR_APIKEY` | *(vuoto)* | API key di Sonarr (Impostazioni → Generale → Sicurezza). |
```

- [ ] **Step 2: Stesse righe in inglese**

In `docs/configurazione.en.md`, stessa posizione: dopo la riga `W_DUPLICATE_CHECK`,
prima del `---`:

```markdown
| `W_RADARR_URL` | *(empty)* | Radarr URL, e.g. `http://127.0.0.1:7878`. Empty disables the integration. |
| `W_RADARR_APIKEY` | *(empty)* | Radarr API key (Settings → General → Security). |
| `W_SONARR_URL` | *(empty)* | Sonarr URL, e.g. `http://127.0.0.1:8989`. Empty disables the integration. |
| `W_SONARR_APIKEY` | *(empty)* | Sonarr API key (Settings → General → Security). |
```

- [ ] **Step 3: Sezione d'uso in italiano**

In fondo a `docs/uso-web.md` aggiungi:

```markdown
## Radarr e Sonarr

Configura URL e API key in **Impostazioni → Radarr / Sonarr** e usa **Test
connessione** per verificarli. Radarr e Sonarr devono vedere lo stesso filesystem di
unit3dprep: l'accoppiamento fra libreria e monitoraggio avviene per path.

Quando l'integrazione è attiva la libreria mostra un badge **monitorato** su ciò che
Radarr o Sonarr stanno ancora cercando. Il pulsante di rimozione compare solo lì:

- **Film** — nel pannello dettaglio.
- **Serie** — nel pannello dettaglio; spegne anche tutte le stagioni e tutti gli
  episodi.
- **Stagione** — icona nell'intestazione della stagione; spegne anche i suoi episodi.
- **Episodio** — icona sulla riga dell'episodio.

Per lavorare in blocco: filtra per **Lingua**, entra in selezione multipla, seleziona
e usa **Rimuovi monitoraggio**. I film vengono spenti in un colpo solo, le serie una
per una a cascata; alla fine un avviso riporta quanti sono riusciti e quanti no.

Se Radarr o Sonarr non rispondono, la libreria funziona come sempre e in cima compare
un avviso: badge e pulsanti restano nascosti finché il servizio non torna.
```

- [ ] **Step 4: Sezione d'uso in inglese**

In fondo a `docs/uso-web.en.md`:

```markdown
## Radarr and Sonarr

Set the URL and API key under **Settings → Radarr / Sonarr** and use **Test
connection** to check them. Radarr and Sonarr must see the same filesystem as
unit3dprep: library items are matched to their records by path.

With the integration on, the library shows a **monitored** badge on whatever Radarr or
Sonarr is still searching for. The removal button appears only there:

- **Movie** — in the detail panel.
- **Series** — in the detail panel; also switches off every season and episode.
- **Season** — icon in the season header; also switches off its episodes.
- **Episode** — icon on the episode row.

To work in bulk: filter by **Language**, enter multi-select, pick the items and hit
**Stop monitoring**. Movies go off in a single call, series one at a time with their
cascade; a toast reports how many succeeded and how many failed.

If Radarr or Sonarr are unreachable the library keeps working as usual and a notice
appears at the top: badges and buttons stay hidden until the service is back.
```

- [ ] **Step 5: Voce nel changelog**

In `CHANGELOG.md`, sotto `## [Unreleased]`, aggiungi (creando `### Added` se manca):

```markdown
### Added
- Integrazione Radarr e Sonarr: stato di monitoraggio visibile nella libreria e
  rimozione con un click su film, serie, stagione ed episodio, anche sulla
  selezione multipla. URL e API key si impostano in Impostazioni → Radarr / Sonarr.
```

- [ ] **Step 6: Build della documentazione**

Run: `python -m mkdocs build --strict -d "$TEMP/claude/mkdocs-check"`
Expected: `Documentation built in …` senza warning. Un anchor rotto fa fallire il
build in modalità strict.

- [ ] **Step 7: Commit**

```bash
git add docs/configurazione.md docs/configurazione.en.md docs/uso-web.md docs/uso-web.en.md CHANGELOG.md
git commit -m "docs: integrazione Radarr/Sonarr"
```

---

## Task 14: Verifica completa e deploy di prova

**Files:** nessuno

- [ ] **Step 1: Syntax check di tutti i file backend toccati**

Run: `python -m py_compile unit3dprep/web/arr.py unit3dprep/web/api/arr.py unit3dprep/web/app.py unit3dprep/web/config.py`
Expected: nessun output, exit 0

- [ ] **Step 2: Rilanciare tutti gli script di verifica**

```bash
python "$SCRATCH/verify_arr_config.py" && python "$SCRATCH/verify_arr_index.py" && python "$SCRATCH/verify_arr_unmonitor.py" && python "$SCRATCH/verify_arr_router.py"
```

Expected: quattro `OK`

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: build completata, nessun errore TypeScript

- [ ] **Step 4: Tornare alla radice del repo**

Run: `cd C:/Users/sidot/Documents/Github/itatorrents-seeding`

- [ ] **Step 5: Build documentazione**

Run: `python -m mkdocs build --strict -d "$TEMP/claude/mkdocs-check"`
Expected: nessun warning

- [ ] **Step 6: Verificare che la dist sia committata**

Run: `git status --short`
Expected: nessun file modificato non tracciato sotto `unit3dprep/web/dist/`. Se ce ne
sono, `git add unit3dprep/web/dist && git commit -m "build: aggiorna la SPA"`.

- [ ] **Step 7: Push su main**

```bash
git push origin main
```

Nessun tag e nessuna release: il deploy di prova installa da `@main`.

- [ ] **Step 8: Reinstallare sul VPS**

```bash
ssh ultra '~/.venvs/unit3dprep/bin/pip install --force-reinstall --no-deps "git+https://github.com/davidesidoti/unit3dprep.git@main" >/tmp/pip.log 2>&1; echo exit=$?'
```

Expected: `exit=0`. Un `Connection reset by peer` alla fine non significa fallimento:
l'output è nel file, va riletto in una connessione separata.

- [ ] **Step 9: Verificare che il codice sia atterrato**

```bash
ssh ultra 'grep -c "series_unmonitored_payload" ~/.venvs/unit3dprep/lib/python*/site-packages/unit3dprep/web/arr.py'
```

Expected: un numero ≥ 1. Il numero di versione non cambia con un install da `@main`,
quindi non è un indicatore valido.

- [ ] **Step 10: Riavviare e controllare la salute**

```bash
ssh ultra 'systemctl --user restart unit3dprep.service; sleep 8; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:42514/unit3dprep/'
```

Expected: `200`. L'app impiega circa 6 secondi a salire: un 502 con un'attesa più
breve è transitorio.

- [ ] **Step 11: Ricavare le porte reali di Radarr e Sonarr**

```bash
ssh ultra 'ss -ltnp | grep -Ei "radarr|sonarr"'
```

Annota le porte: servono per compilare Impostazioni → Radarr / Sonarr.

- [ ] **Step 12: Test manuale nella UI**

1. Impostazioni → Radarr / Sonarr: inserisci URL (`http://127.0.0.1:<porta>`) e API
   key, premi **Test connessione** su entrambe. Attese: versione e nome istanza.
2. Salva, vai in Libreria e ricarica. Attesa: badge **monitorato** sui titoli che
   Radarr/Sonarr stanno ancora cercando.
3. Apri un film monitorato → **Rimuovi monitoraggio**. Attesa: il pulsante diventa
   *Monitoraggio rimosso*; in Radarr il film risulta non monitorato.
4. Apri una serie monitorata → rimuovi a livello serie. Attesa: in Sonarr la serie e
   **tutte** le sue stagioni ed episodi risultano non monitorati.
5. Su un'altra serie prova la sola stagione. Attesa: solo quella stagione e i suoi
   episodi si spengono; la serie resta monitorata.
6. Filtro **Lingua** = un codice qualsiasi → selezione multipla → **Rimuovi
   monitoraggio**. Attesa: avviso con il conteggio; ricaricando, i badge spariscono.

**Se i badge non compaiono mai** ma il test di connessione riesce, il match per path
non sta funzionando: confronta le chiavi di `GET /api/arr/status` con il campo `path`
di `GET /api/library/{categoria}`. Una differenza sistematica (un symlink su
`U3DP_MEDIA_ROOT`, un mount diverso) è la causa più probabile.

- [ ] **Step 13: Riferire l'esito**

Riporta cosa ha funzionato e cosa no, con l'output esatto dei passi falliti. Non
dichiarare il lavoro concluso se un controllo è fallito.

---

## Note per chi implementa

- **Scostamento voluto dalla spec.** La spec prevedeva funzioni wrapper
  (`arrStatus()`, `arrUnmonitor()`, …) in `api.ts`. Il piano chiama invece
  `api.get` / `api.post` direttamente nei componenti, che è come fa tutto il resto
  del codice: `api.ts` esporta l'oggetto `api` e nessuna vista usa wrapper per
  endpoint. Aggiungerne solo per `arr` avrebbe introdotto un secondo stile.
- **La working directory è condivisa fra il tool Bash e il tool PowerShell.** Dopo
  ogni `cd frontend` torna alla radice con un `cd` esplicito prima di usare git,
  altrimenti i comandi partono dalla sottocartella.
- **Messaggi di commit multi-riga:** scrivili su file e usa `git commit -F <file>`.
  La forma here-string di PowerShell (`@'…'@`) si rompe.
- **Non aggiungere il trailer `Co-Authored-By`** ai commit.
- **Il rebuild del grafo graphify** dopo aver modificato i file va lanciato dalla
  radice del repo, non da `frontend/`, e su Windows richiede `$env:PYTHONUTF8=1`.
