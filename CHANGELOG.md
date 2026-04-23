# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- **Auto-update unit3dup: pulsante restava visibile dopo l'update**. Il `_cache` di `/api/version/info` (TTL 10min) non veniva invalidato al termine dell'install, quindi la UI continuava a vedere `{newer: true}` fino alla scadenza naturale. Ora il cache viene azzerato sull'evento `done` dell'endpoint SSE `update/unit3dup/stream`.
- **Auto-update: service non veniva realmente riavviato su systemd user services**. Il `systemctl --user restart` spawnato come figlio detached restava nel cgroup del service genitore e veniva ucciso da systemd prima di poter eseguire. Ora il restart viene schedulato via `systemd-run --user --on-active=3s` in uno scope transient fuori dal cgroup del service, garantendo che il restart avvenga davvero. Fallback al metodo precedente se `systemd-run` non è disponibile.
- **Auto-update: versione mostrata in UI non si aggiornava dopo `git pull`**. `importlib.metadata.version()` poteva ritornare valori stantii per via di `itatorrents.egg-info/` nella source dir o `dist-info` orfani nei site-packages. In git mode il backend ora legge la versione direttamente da `pyproject.toml` (fonte autorevole, aggiornata atomicamente da `git pull`).
- **Auto-update git mode**: pre-pulizia di `itatorrents.egg-info`, `itatorrents-*.dist-info` orfani e `__editable__.itatorrents-*.pth` residui prima di `pip install -e .`, più loop di `pip uninstall` finché "not installed". Elimina il problema delle metadata stantie che pip non rimuove completamente.

---

## [0.4.0] - 2026-04-23

Nuove funzionalità per la Media Library e per la gestione runtime del service systemd, più un fix al flow di auto-update.

### Added
- Nuova checkbox **"Only with Italian audio"** nella Media Library: filtra i media il cui audio è già stato scansionato ma non contiene una traccia ITA (gli item non ancora scansionati restano visibili). Default configurabile da **Settings › Wizard Defaults** tramite la nuova chiave `W_HIDE_NO_ITALIAN`.
- `ITA_SYSTEMD_UNIT` è ora editabile da **Settings › App Auto-Update** e persiste in `Unit3Dbot.json`. La chiave viene letta runtime (non solo all'import) così il bottone "Update app" rileva subito il cambio di nome della unit senza dover riavviare il service.
- Documentazione aggiornata (`docs/configurazione.md`, `docs/uso-web.md`, `docs/deploy-ultracc.md` + mirror inglesi) con una sezione dedicata all'auto-update in-app, ai pre-requisiti systemd e alla gestione di `ITA_SYSTEMD_UNIT` / `WorkingDirectory` su Ultra.cc.
- README: menzione del sistema di auto-update nella descrizione del progetto.

### Fixed
- **UpdateProgressModal entrava in loop infinito dopo il restart del service**: l'`EventSource` riconnetteva automaticamente quando il service veniva riavviato e il backend rieseguiva l'update da capo. Ora la connessione SSE viene chiusa esplicitamente alla ricezione dell'evento `done` e `onError` non riattiva lo stream se l'update è già concluso.

---

## [0.3.1] - 2026-04-23

Primo rilascio funzionante del sistema di auto-update introdotto in v0.3.0.

### Fixed
- **Update app non funzionava su installazioni pip-from-git**: il flow assumeva un git checkout ma `pip install git+URL@tag` non lascia la cartella `.git`. Aggiunto rilevamento automatico della modalità di installazione (`git` vs `pip`) con flow dedicato per pip: `pip install --upgrade --force-reinstall git+URL@vX`.
- **Check systemd troppo stretto**: `systemctl --user is-enabled` restituisce rc≠0 per unit in stato `linked` (symlink, comune su Ultra.cc) o `static` → pulsante "Update app" erroneamente disabilitato con `systemd unit not available in this environment`. Passato a `systemctl --user cat UNIT` che ritorna 0 iff il file unit esiste, indipendentemente dallo stato di abilitazione.

### Upgrade notes
Se stai aggiornando da v0.3.0, il codice attualmente installato contiene i bug sopra quindi non può aggiornarsi autonomamente. Fai il bootstrap una volta manualmente:
```
~/.venvs/itatorrents/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/itatorrents-seeding.git@v0.3.1"
systemctl --user restart itatorrents.service
```
Dalla v0.3.1 in poi il pulsante "Update app" funziona dall'UI.

---

## [0.3.0] - 2026-04-23

### Added
- Web UI React SPA (Vite + TypeScript) con FastAPI backend, servita via systemd user service su Ultra.cc
- Wizard multi-step: audio check → TMDB lookup → rinomina → hardlink → unit3dup PTY stream
- Quick Upload modal per power users (senza wizard)
- Libreria media con categorie dinamiche da `W_MEDIA_ROOT`
- Queue torrent via qBittorrent client con filtro per nome
- Upload History con stati e exit code
- Logs tab con filtri source/kind persistiti in localStorage; classificazione automatica log unit3dup
- Settings runtime `ITA_*` / `W_*` via env o `Unit3Dbot.json` (no restart necessario)
- Auth con sessione + bcrypt; OpenAPI/Swagger protetto
- Mobile responsive: sidebar drawer, overlay panel dettaglio, layout a 1 colonna
- Runtime-configurable media root e seedings dir
- Documentazione MkDocs su GitHub Pages
- Check compatibilità filesystem per hardlink
- Tracker sidebar con badge Online/Offline/Not set (inclusi tracker non configurati)