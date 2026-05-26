# Usage › CLI

The `unit3dprep` CLI is for interactive use over SSH or a local terminal. Workflow: file → audio check → TMDB → rename → hardlink → upload via Unit3DWebUp HTTP.

Entry point: `unit3dprep` (registered by `pip install -e .`).

!!! info "Upload backend"
    Since v0.7.0 the CLI **no longer spawns `unit3dup` as a subprocess**. The CLI flow now also goes through the HTTP bridge to `Unit3DWebUp` (the same one used by the Web UI wizard), reusing `webup_client` + `webup_orchestrator`. Practical consequence: Unit3DWebUp must be up and reachable (`WEBUP_URL`, default `127.0.0.1:8000`) before launching the CLI.

---

## Syntax

```bash
unit3dprep -u <FILE>        # movie or single episode
unit3dprep -f <FOLDER>      # series or entire season
```

`-u` and `-f` are mutually exclusive. No other flags: everything else is an interactive prompt (requires a TTY — the CLI uses `readline`).

---

## `-u` flow (single file)

```bash
unit3dprep -u /mnt/media/movies/Dune.Part.Two.2024.mkv
```

1. **Audio check** — `pymediainfo` lists the tracks. If Italian is missing, exits with an error.
2. **Confirmation** — *"Italian language found. Proceed with hardlink and rename? [y/n]"*.
3. **TMDB ID** — prompt *"Enter TMDB ID for movie (guessit: 'Dune Part Two')"*. Search <https://www.themoviedb.org>, copy the numeric ID from the URL (`/movie/693134` → `693134`) and paste it. Requires `TMDB_API_KEY`.
4. **Final name** — `guessit` + `extract_specs` compose a name per the [naming convention](nomenclatura.md). Editable inline (readline preloads the default).
5. **Collision check** — if the target exists in `~/seedings/`, prompts *overwrite / skip / cancel*.
6. **Hardlink** — created at `~/seedings/.unit3dprep/<jobid>/<final name>.<ext>` (per-upload sandbox to avoid the `/scan` race in webup; see [Unit3DWebUp integration](integrazione-webup.md#scan_path-semantics-per-upload-sandbox)).
7. **Upload confirmation** — *"Upload '<name>' via Unit3DWebUp? [y/n]"*.
8. **HTTP bridge** — if accepted, `run_webup_sync()` drives the `setenv → scan → maketorrent → upload → seed` pipeline against Unit3DWebUp and prints live logs to stdout (`[progress]` events, errors to stderr). Exit code propagated to the shell.

### Expected output

```
Analisi tracce audio: Dune.Part.Two.2024.mkv ...
Lingua italiana trovata. Proseguo con hardlink e rinomina? [y/n]: y
Inserisci TMDB ID per movie (guessit: 'Dune Part Two'): 693134
Nome finale: Dune Parte Due (2024) 2160p UHD BluRay TrueHD 7.1 HDR10 H.265 - ItaTorrentsBot
Hardlink creato: /home/user/seedings/Dune Parte Due (2024) ... .mkv
Uploadare 'Dune Parte Due ... .mkv' tramite Unit3DWebUp? [y/n]: y
[progress] {'phase': 'setenv', 'pct': 1.5, ...}
webup: setting SCAN_PATH=/home/user/seedings
webup: /scan…
[progress] {'phase': 'scan', 'pct': 30.0, ...}
webup: job_id=abcdef… title='Dune Parte Due (2024)'
webup: /maketorrent…
[New torrent] Dune Parte Due... - 100.0
webup: /upload…
webup: torrent seeded
```

(CLI strings remain in Italian by design — the tracker audience is Italian.)

---

## `-f` flow (series / season)

```bash
unit3dprep -f /mnt/media/series/Severance/Season\ 02/
```

1. **Scan** — every video file in the folder is analyzed.
2. **Audio check on ALL** — if even one file lacks Italian audio, exits.
3. **TMDB ID** — prompts for the **series**, not the season.
4. **Episode parsing** — `guessit` extracts `S##E##` from each filename. Episodes missing S/E are reported and skipped.
5. **Folder name** — generated from the first episode as a sample. Editable.
6. **Hardlink tree** — `~/seedings/.unit3dprep/<jobid>/<folder name>/<episode name>.<ext>` for each file (per-upload sandbox; see [Unit3DWebUp integration](integrazione-webup.md#scan_path-semantics-per-upload-sandbox)).
7. **Upload confirmation** — as above.
8. **HTTP bridge** — `run_webup_sync()` runs the pipeline with `kind=series`. Internally the orchestrator sets `SCAN_PATH = parent(seeding_folder)` and matches by subfolder, so webup recognizes the pack as a single Media (not separate episodes).

### Pointing at a single season

You can point directly at `Series/Season 01/`: `guessit` works on individual episode filenames, not on the folder name. Useful for multi-season series uploaded one season at a time.

---

## CLI environment variables

| Variable | Effect |
|---|---|
| `TMDB_API_KEY` | Required by `tmdb_fetch`. Without it the TMDB prompt fails with an error. |
| `WEBUP_URL` | Unit3DWebUp address (default `http://127.0.0.1:8000`). |
| `ENVPATH` / `U3DP_ENV_PATH` | Path of the shared `.env` (see [Configuration](configurazione.md)). |
| `U3DP_MEDIA_ROOT` | Not used directly by the CLI, but useful for short absolute paths via completion. |
| `U3DP_SEEDINGS_DIR` | Changes where hardlinks are created. |
| `U3DP_DRY_RUN_TRACKER` | When `1`, skips `/upload`. Test the pipeline without polluting the tracker. |

The CLI reads `U3DP_SEEDINGS_DIR` through `core.seedings_dir()`, so it also respects the value saved in the `.env`.

---

## Unit3DWebUp pipeline executed

`run_webup_sync()` spins a temporary asyncio loop consuming the `stream_webup` generator:

| Step | Webup endpoint | Notes |
|---|---|---|
| 1 | `POST /setenv {PREFS__SCAN_PATH: <parent>}` | Movie: parent(file). Series: parent(folder). |
| 2 | `POST /scan` | Webup performs TMDB/TVDB lookup + ffmpeg screenshots. |
| 3 | `POST /settmdbid` | Only if your inserted ID differs from webup's resolution. |
| 4 | `POST /maketorrent` | HTTP 200 = build done; final logs drained ~0.8s. |
| 5 | `POST /upload` | HTTP 200 = upload done; 2s log drain to detect success/failure. |
| 6 | `POST /seed` | 200=ok, 503/409/404 mapped to warning, others = warning. |

See [Unit3DWebUp integration](integrazione-webup.md) for architectural detail.

---

## Possible prompt answers

| Prompt | Valid answers |
|---|---|
| Binary confirmation | `y` / `yes` / `s` / `si` / `sì` → yes; anything else → no |
| Collision | `o` overwrite / `s` skip / `c` cancel |
| Final name | inline editable with readline (←→ arrows), Enter to confirm |

`Ctrl+C` during a prompt exits with code 130. During the webup pipeline, `Ctrl+C` is caught and propagated as exit code 130.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (upload completed, or user cancelled after hardlink). |
| `1` | Invalid file/folder, no Italian audio, empty name, unrecoverable TMDB or webup-bridge error. |
| `130` | `Ctrl+C` (prompt or streaming). |

---

## Differences from the Web UI wizard

| Aspect | CLI | Web wizard |
|---|---|---|
| Italian detection | Blocks if missing | Configurable (`W_AUDIO_CHECK`) |
| TMDB | Always manual (ID) | Search + automatic match |
| Final name | Inline edit | Edit with preview |
| Upload backend | HTTP bridge to Unit3DWebUp | Same HTTP bridge |
| History (`U3DP_DB_PATH`) | **Does not** write | Writes |
| Progress UI | Plain stdout logs | Live progress bar + SSE logs |
| Multi-job batch | One file/folder at a time | Quick upload + multi-select |

!!! warning "No history writes"
    The CLI does not update `~/.unit3dprep_db.json`. If you want uploads to show up in the Web UI "Uploaded" panel, go through the wizard.
