# Usage › CLI

The `unit3dprep` CLI is intended for interactive use over SSH or a local terminal. It does not need the Web UI: it is a straight file → hardlink → `unit3dup` workflow.

Entry point: `unit3dprep` (registered by `pip install -e .`).

---

## Syntax

```bash
unit3dprep -u <FILE>        # movie or single episode
unit3dprep -f <FOLDER>      # series or entire season
```

`-u` and `-f` are mutually exclusive. No other flags: everything else happens through interactive prompts.

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
6. **Hardlink** — created at `~/seedings/<final name>.<ext>`.
7. **Upload confirmation** — *"Upload '<name>' to ItaTorrents? [y/n]"*.
8. **`unit3dup`** — if accepted, runs `unit3dup -b -u <absolute path>`. Exit code propagated to the shell.

### Expected output

```
Analisi tracce audio: Dune.Part.Two.2024.mkv ...
Lingua italiana trovata. Proseguo con hardlink e rinomina? [y/n]: y
Inserisci TMDB ID per movie (guessit: 'Dune Part Two'): 693134
Nome finale: Dune Parte Due (2024) 2160p UHD BluRay TrueHD 7.1 HDR10 H.265 - ItaTorrentsBot
Hardlink creato: /home/user/seedings/Dune Parte Due (2024) ... .mkv
Uploadare 'Dune Parte Due ... .mkv' su ItaTorrents? [y/n]: y
[unit3dup output ...]
```

(CLI strings are in Italian by design — the tracker audience is Italian.)

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
6. **Hardlink tree** — `~/seedings/<folder name>/<episode name>.<ext>` for each file.
7. **Upload confirmation** — as above.
8. **`unit3dup`** — runs `unit3dup -b -f <absolute folder path>`.

### Pointing at a single season

You can point directly at `Series/Season 01/`: `guessit` works on individual episode filenames, not on the folder name, so it still works. Useful for multi-season series you want to upload one season at a time.

---

## CLI environment variables

| Variable | Effect |
|---|---|
| `TMDB_API_KEY` | Required by `tmdb_fetch`. Without it the TMDB prompt fails with an error. |
| `U3DP_MEDIA_ROOT` | Not used directly by the CLI, but useful for short absolute paths via completion. |
| `U3DP_SEEDINGS_DIR` | Changes where hardlinks are created. |

The CLI reads `U3DP_SEEDINGS_DIR` through `core.seedings_dir()`, so it also respects `Unit3Dbot.json`.

---

## `unit3dup` commands launched

- Movie / single episode: `unit3dup -b -u <absolute file path>`
- Series / season: `unit3dup -b -f <absolute folder path>`

The path is always `.resolve()`-d (absolute, symlinks resolved). `-b` = batch mode (non-interactive on the `unit3dup` side).

---

## Possible prompt answers

| Prompt | Valid answers |
|---|---|
| Binary confirmation | `y` / `yes` / `s` / `si` / `sì` → yes; anything else → no |
| Collision | `o` overwrite / `s` skip / `c` cancel |
| Final name | inline editable with readline (←→ arrows), Enter to confirm |

`Ctrl+C` during a prompt exits with code 130.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (upload completed or user cancelled after hardlink). |
| `1` | Invalid file/folder, no Italian audio, empty name, unrecoverable TMDB error. |
| `127` | `unit3dup` not found on PATH. |
| `130` | `Ctrl+C`. |
| other | Exit code propagated from `unit3dup`. |

---

## Differences from the Web UI wizard

| Aspect | CLI | Web wizard |
|---|---|---|
| Italian detection | Blocks if missing | Configurable (`W_AUDIO_CHECK`) |
| TMDB | Always manual (ID) | Search + automatic match |
| Final name | Inline edit | Edit with preview |
| Upload | `unit3dup` foreground | `unit3dup` in a PTY with SSE stream |
| History | **Does not** write to the DB | Writes `U3DP_DB_PATH` |
| Batch | One file/folder at a time | Same |

!!! warning "No history writes"
    The CLI does not update `~/.unit3dprep_db.json`. If you want uploads to show up in the Web UI "Uploaded" panel, go through the wizard or `quickupload`.
