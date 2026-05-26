# Uso › CLI

La CLI `unit3dprep` è pensata per l'uso interattivo via SSH o terminale locale. Workflow file → audio check → TMDB → rinomina → hardlink → upload via Unit3DWebUp HTTP.

Entry point: `unit3dprep` (registrato da `pip install -e .`).

!!! info "Backend di upload"
    Dalla v0.7.0 la CLI **non lancia più `unit3dup` come subprocess**. Anche il flusso CLI passa attraverso il bridge HTTP verso `Unit3DWebUp` (stesso del wizard Web UI), riusando `webup_client` + `webup_orchestrator`. Conseguenza pratica: Unit3DWebUp deve essere up e raggiungibile (`WEBUP_URL`, default `127.0.0.1:8000`) prima di lanciare la CLI.

---

## Sintassi

```bash
unit3dprep -u <FILE>       # film o singolo episodio
unit3dprep -f <CARTELLA>   # serie o intera stagione
```

`-u` e `-f` sono mutuamente esclusivi. Nessun altro flag: tutto il resto avviene tramite prompt interattivi (richiedono TTY — la CLI usa `readline`).

---

## Flusso `-u` (singolo file)

```bash
unit3dprep -u /mnt/media/movies/Dune.Part.Two.2024.mkv
```

1. **Check audio** — `pymediainfo` elenca le tracce. Se non c'è italiano, esce con errore.
2. **Conferma** — *"Lingua italiana trovata. Proseguo con hardlink e rinomina? [y/n]"*.
3. **TMDB ID** — prompt *"Inserisci TMDB ID per movie (guessit: 'Dune Part Two')"*. Cerca su <https://www.themoviedb.org>, copia l'ID numerico dall'URL (`/movie/693134` → `693134`) e incollalo. Serve `TMDB_API_KEY`.
4. **Nome finale** — `guessit` + `extract_specs` compongono un nome secondo la [nomenclatura](nomenclatura.md). Editabile inline (readline precarica il default).
5. **Collision check** — se il target esiste in `~/seedings/`, prompt *sovrascrivi / salta / annulla*.
6. **Hardlink** — creato in `~/seedings/.unit3dprep/<jobid>/<nome finale>.<ext>` (sandbox dedicata per evitare race del `/scan` webup; vedi [Integrazione Unit3DWebUp](integrazione-webup.md#semantica-scan_path-sandbox-per-upload)).
7. **Conferma upload** — *"Uploadare '<nome>' tramite Unit3DWebUp? [y/n]"*.
8. **Bridge HTTP** — se accetti, `run_webup_sync()` invoca il pipeline `setenv → scan → maketorrent → upload → seed` su Unit3DWebUp e stampa i log live in stdout (`[progress]`, errori in stderr). Exit code restituito al shell.

### Output atteso

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

---

## Flusso `-f` (serie / stagione)

```bash
unit3dprep -f /mnt/media/series/Severance/Season\ 02/
```

1. **Scansione** — tutti i file video nella cartella vengono analizzati.
2. **Check audio su TUTTI** — se anche uno solo manca l'italiano, esce.
3. **TMDB ID** — prompt per la **serie**, non per la stagione.
4. **Parsing episodi** — `guessit` estrae `S##E##` da ogni filename. Episodi senza S/E vengono segnalati e saltati.
5. **Nome cartella** — generato dal primo episodio come campione. Editabile.
6. **Hardlink tree** — `~/seedings/.unit3dprep/<jobid>/<nome cartella>/<nome episodio N>.<ext>` per ogni file (sandbox dedicata; vedi [Integrazione Unit3DWebUp](integrazione-webup.md#semantica-scan_path-sandbox-per-upload)).
7. **Conferma upload** — come sopra.
8. **Bridge HTTP** — `run_webup_sync()` lancia il pipeline con `kind=series`. Internamente l'orchestrator imposta `SCAN_PATH = parent(seeding_folder)` e match per subfolder, così webup riconosce il pack come Media singolo (non episodi separati).

### Puntare a una singola stagione

Puoi puntare direttamente a `Serie/Season 01/`: `guessit` opera sui filename dei singoli episodi, non sul nome della cartella. Utile per serie multi-stagione caricate una alla volta.

---

## Variabili d'ambiente CLI

| Variabile | Effetto |
|---|---|
| `TMDB_API_KEY` | Richiesta per `tmdb_fetch`. Senza, il prompt TMDB fallisce con errore. |
| `WEBUP_URL` | Indirizzo Unit3DWebUp (default `http://127.0.0.1:8000`). |
| `ENVPATH` / `U3DP_ENV_PATH` | Path del `.env` condiviso (vedi [Configurazione](configurazione.md)). |
| `U3DP_MEDIA_ROOT` | Non usata dalla CLI direttamente, ma utile se vuoi path assoluti brevi via completion. |
| `U3DP_SEEDINGS_DIR` | Cambia dove vengono creati gli hardlink. |
| `U3DP_DRY_RUN_TRACKER` | Se `1`, salta `/upload`. Test della pipeline senza polluire tracker. |

La CLI legge `U3DP_SEEDINGS_DIR` attraverso `core.seedings_dir()`, quindi rispetta anche il valore salvato nel `.env`.

---

## Pipeline Unit3DWebUp eseguita

`run_webup_sync()` avvia un loop asyncio temporaneo che consuma il generator `stream_webup`:

| Step | Endpoint webup | Note |
|---|---|---|
| 1 | `POST /setenv {PREFS__SCAN_PATH: <parent>}` | Film: parent(file). Serie: parent(folder). |
| 2 | `POST /scan` | Webup esegue lookup TMDB/TVDB + screenshot ffmpeg. |
| 3 | `POST /settmdbid` | Solo se l'ID che hai inserito differisce da quello risolto da webup. |
| 4 | `POST /maketorrent` | HTTP 200 = build completata; log finali drenati ~0.8s. |
| 5 | `POST /upload` | HTTP 200 = upload completato; drenaggio log 2s per detectare success/failure. |
| 6 | `POST /seed` | 200=ok, 503/409/404 mappati a warning, altri = warning. |

Vedi [Integrazione Unit3DWebUp](integrazione-webup.md) per il dettaglio architetturale.

---

## Scelte possibili ai prompt

| Prompt | Risposte valide |
|---|---|
| Conferma binaria | `y` / `yes` / `s` / `si` / `sì` → sì; tutto il resto → no |
| Collision | `o` sovrascrivi / `s` salta / `c` annulla |
| Nome finale | editabile inline con readline (frecce ←→), invio per confermare |

`Ctrl+C` durante un prompt termina con exit code 130. Durante il pipeline webup, `Ctrl+C` viene catturato e propagato come exit code 130.

---

## Exit code

| Codice | Significato |
|---|---|
| `0` | Successo (upload completato, oppure annullato dall'utente dopo hardlink). |
| `1` | File/cartella non valido, no italiano, nome vuoto, errore irrecuperabile in TMDB o nel bridge webup. |
| `130` | `Ctrl+C` (durante prompt o durante streaming). |

---

## Differenza dal wizard Web UI

| Aspetto | CLI | Wizard Web |
|---|---|---|
| Rilevamento italiano | Blocca se manca | Configurabile (`W_AUDIO_CHECK`) |
| TMDB | Sempre manuale (ID) | Ricerca + match automatico |
| Nome finale | Editabile inline | Editabile con preview |
| Backend upload | Bridge HTTP a Unit3DWebUp | Stesso bridge HTTP |
| Storico (`U3DP_DB_PATH`) | **Non** scrive | Scrive |
| Progress UI | Log testuali in stdout | Barra grafica + log live SSE |
| Multi-job batch | Un file/cartella per volta | Quick upload + multi-select |

!!! warning "Nessuna scrittura nello storico"
    La CLI non aggiorna `~/.unit3dprep_db.json`. Se vuoi che l'upload appaia nel pannello "Uploaded" della Web UI, passa attraverso il wizard.
