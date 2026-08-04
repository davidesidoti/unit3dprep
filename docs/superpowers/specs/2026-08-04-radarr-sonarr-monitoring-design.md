# Integrazione Radarr / Sonarr — rimozione del monitoraggio dalla libreria

Data: 2026-08-04
Stato: approvato, pronto per il piano di implementazione

## Problema

Il flusso attuale è manuale. L'utente scorre la libreria di unit3dprep, individua i
titoli che risultano avere audio italiano, apre Radarr o Sonarr in un'altra scheda,
cerca il titolo e ne disattiva il monitoraggio — perché la versione che serve è già
stata scaricata e non ha senso continuare a cercarla.

Ogni titolo costa una ricerca manuale e un cambio di contesto. Con una libreria di
qualche centinaio di elementi il lavoro diventa la parte più lenta della giornata.

## Obiettivo

Portare l'azione dentro unit3dprep: vedere lo stato di monitoraggio direttamente
nella libreria e rimuoverlo con un click — sul film, sulla serie, sulla singola
stagione, sul singolo episodio — oltre che in blocco sulla selezione multipla.

Il caso d'uso che deve diventare banale: filtro `Lingua = ITA` → seleziona tutto →
un click.

## Decisioni prese

| Decisione | Scelta | Motivo |
|---|---|---|
| Accoppiamento libreria ↔ \*arr | **Path su disco** | Radarr/Sonarr espongono `path` per ogni film/serie e girano sullo stesso filesystem: match esatto, nessuna ambiguità su remake o anime. |
| Traduzione dei path | **Nessuna** | I root sono identici da entrambe le parti. Nessun campo di remap. |
| Stato nella UI | **Stato + azione** | Badge di monitoraggio visibile, così si vede a colpo d'occhio cosa resta da fare. |
| Istanze | **Una Radarr + una Sonarr** | YAGNI. Il match per path rende la categoria della libreria irrilevante. |
| Azione di massa | **Sì** | È il vero acceleratore del flusso descritto sopra. |
| Semantica sulla serie | **Cascata completa** | Serie spenta → stagioni ed episodi spenti. Stato coerente in Sonarr. |
| Architettura | **Endpoint separato + merge nel frontend** | La libreria resta indipendente da due servizi esterni. |

Il monitoraggio si può solo **rimuovere**, non riattivare: è l'unica direzione che
serve al flusso ed evita superficie inutile.

## Architettura

```
GET /api/library/{cat}   ──────────────►  griglia (invariata, nessuna dipendenza da *arr)
GET /api/arr/status      ──────────────►  indice path → monitored (Radarr + Sonarr)
                                              │
                                              └─► merge nel frontend per item.path
```

`GET /api/arr/status` restituisce l'indice completo di entrambe le istanze in **una**
chiamata, con cache lato backend di 60 secondi. LibraryView lo carica dopo aver
renderizzato la griglia e associa ogni item per path. Gli episodi si caricano
on-demand, solo all'apertura del pannello dettaglio di una serie presente
nell'indice.

Conseguenza voluta: se Radarr o Sonarr sono lenti, irraggiungibili o non
configurati, la libreria funziona esattamente come prima.

## Componenti

### `unit3dprep/web/arr.py` — nuovo

Logica pura e client HTTP. Nessuna dipendenza da FastAPI. Header `X-Api-Key`,
timeout 15 s, `follow_redirects=True`.

Funzioni pubbliche:

- `configured(kind) -> bool` — URL e API key presenti per `"radarr"` / `"sonarr"`.
- `build_index() -> ArrIndex` — `GET /api/v3/movie` e `GET /api/v3/series`, una
  chiamata per istanza. Restituisce:

  ```python
  {
    "configured": {"radarr": bool, "sonarr": bool},
    "movies": {norm_path: {"id": int, "monitored": bool, "title": str}},
    "series": {norm_path: {"id": int, "monitored": bool,
                           "seasons": {season_number: bool}, "title": str}},
    "errors": {"radarr": str | None, "sonarr": str | None},
  }
  ```

  Cache a livello di modulo con TTL 60 s, invalidata da ogni mutazione.

- `fetch_episodes(series_id)` — `GET /api/v3/episode?seriesId=&includeEpisodeFile=true`.
  Il mapping episodio-libreria → episodio-Sonarr avviene su `episodeFile.path`.
  Un episodio senza file in Sonarr non è associabile: nessun pulsante.

- `unmonitor_movies(ids)` — `PUT /api/v3/movie/editor` con
  `{"movieIds": ids, "monitored": false}`. Una sola chiamata anche per il bulk.

- `unmonitor_series(id)` — `GET /api/v3/series/{id}` → `monitored=false` e tutte le
  stagioni a `false` → `PUT /api/v3/series/{id}`. Poi tutti gli `episodeIds` della
  serie → `PUT /api/v3/episode/monitor` con `{"episodeIds": [...], "monitored": false}`.

- `unmonitor_season(id, season_number)` — stessa PUT sulla serie con solo quella
  stagione a `false`, più gli episodi di quella stagione.

- `unmonitor_episodes(ids)` — `PUT /api/v3/episode/monitor`.

- `test_connection(kind)` — `GET /api/v3/system/status` → `{ok, version, instance_name}`.

Normalizzazione dei path: `os.path.normpath` più rimozione del separatore finale,
confronto case-sensitive (Linux).

### `unit3dprep/web/api/arr.py` — nuovo router

Registrato in `app.py` come gli altri, sotto `ROOT_PATH`.

| Metodo | Rotta | Corpo / query | Risposta |
|---|---|---|---|
| GET | `/api/arr/status` | — | `ArrIndex` |
| GET | `/api/arr/series/{id}/episodes` | — | `{episodes: [{id, season_number, episode_number, title, monitored, path}]}` |
| POST | `/api/arr/unmonitor` | `{kind, path?, season_number?, episode_ids?}` | `{ok, changed}` |
| POST | `/api/arr/unmonitor/bulk` | `{paths: [...]}` | `{ok, done, failed: [{path, error}]}` |
| GET | `/api/arr/test?kind=` | — | `{ok, version, instance_name, error?}` |

`kind` in `/unmonitor` è uno fra `movie`, `series`, `season`, `episodes`:

- `movie` e `series` richiedono solo `path`; l'id Radarr/Sonarr viene risolto
  dall'indice, non arriva dal client.
- `season` richiede `path` (della serie) e `season_number`.
- `episodes` richiede `episode_ids`, che il client ha ottenuto da
  `/api/arr/series/{id}/episodes`. Sono gli unici id che il client passa
  direttamente, perché gli episodi non sono nell'indice.

`/unmonitor/bulk` raggruppa: tutti i film in una singola `movie/editor`, ogni serie
con la propria cascata. Prosegue sui fallimenti e li elenca in `failed`.

Ogni mutazione invalida la cache dell'indice prima di rispondere.

### Configurazione

Quattro chiavi nuove in `DEFAULT_CONFIG` (`web/config.py`), aggiunte al gruppo
"Seeding Flow" di `_GROUPS`:

| Chiave | Default |
|---|---|
| `W_RADARR_URL` | `""` |
| `W_RADARR_APIKEY` | `""` |
| `W_SONARR_URL` | `""` |
| `W_SONARR_APIKEY` | `""` |

Le due API key entrano in `MASKED_KEYS`: mascherate come `__SET__` in
`GET /api/settings`, ripristinate dal valore esistente in PUT. Sono chiavi `W_*`,
quindi non partecipano alla traduzione canonica verso i nomi webup.

Lette a runtime via `config.runtime_setting()`: cambiare URL o key non richiede
riavvio.

### Frontend

**`frontend/src/components/ArrMonitor.tsx` — nuovo.** Esporta `MonitorBadge` e
`UnmonitorBtn` con varianti `icon` / `full` / `chip`, coerenti con lo stile
condiviso `seasonIconBtn` e con `MarkUploadedBtn`. Sta in un file proprio perché
`LibraryView.tsx` è già a 2144 righe e non va gonfiato ulteriormente.

**`api.ts`**: `arrStatus()`, `arrEpisodes(seriesId)`, `arrUnmonitor(body)`,
`arrUnmonitorBulk(paths)`, `arrTest(kind)`.

**`types.ts`**: `ArrIndex`, `ArrEntry`, `ArrEpisode`.

**`LibraryView.tsx`**:

- `arr` in stato locale, caricato una volta al mount e ricaricato dopo ogni azione.
- Lookup per `item.path` su `arr.movies` e `arr.series`.
- **Card della griglia**: badge "Monitorato" solo quando `monitored === true`. Chi
  non è monitorato o non è nell'indice non mostra nulla: la griglia resta pulita e
  salta all'occhio esattamente ciò che resta da fare.
- **Pannello dettaglio film**: pulsante full-width accanto a `MarkUploadedBtn` e
  `ToCheckBtn`.
- **Pannello dettaglio serie**: pulsante a livello serie; quarta icona nella toolbar
  dell'header di stagione, accanto alle tre esistenti; chip sulla riga episodio.
- **Episodi**: `arrEpisodes(seriesId)` chiamato solo all'apertura del pannello di una
  serie presente nell'indice.
- **Barra azioni bulk**: terzo pulsante "Rimuovi monitoraggio", una sola
  `arrUnmonitorBulk`, toast con il conteggio.

**`SettingsView.tsx`**: nuova sezione `arr` in `SECTIONS`, con URL e API key per
istanza e un pulsante "Test connessione" per ciascuna che mostra versione e nome
dell'istanza.

## Gestione degli errori

| Situazione | Comportamento |
|---|---|
| Nessuna istanza configurata | `configured` a `false`, mappe vuote. Il frontend non mostra né badge né pulsanti. Impatto zero per chi non usa \*arr. |
| Rete irraggiungibile, 401, URL errato | `errors[kind]` popolato. Riga d'avviso discreta in cima alla libreria, non un toast ricorrente. Nessun pulsante. |
| Path assente dall'indice | Nessun badge, nessun pulsante su quell'item. |
| Episodio senza file in Sonarr | Chip assente su quella riga. |
| Bulk parzialmente fallito | Toast "N rimossi, M falliti"; il dettaglio finisce nei Logs via `logbuf.emit(source="arr")`. |

Nessun errore di Radarr o Sonarr può impedire il caricamento della libreria.

## Contorno

- Chiavi i18n in `frontend/src/i18n/locales/en.ts` e `it.ts` (namespace `arr.*` più
  `settings.navArr` e le etichette dei campi). `Catalog = typeof en` impone la parità.
- `docs/configurazione.md` e `docs/configurazione.en.md`: righe nella tabella delle
  chiavi.
- `docs/uso-web.md` e `docs/uso-web.en.md`: sezione sull'uso dei pulsanti in libreria.
- `CHANGELOG.md`: voce sotto `[Unreleased] ### Added`.

## Verifica

Nell'ordine:

1. `python -m py_compile` sui file backend nuovi e modificati.
2. `cd frontend && npm run build` (`tsc -b && vite build`) — è anche il type-check.
3. `python -m mkdocs build --strict -d "$TEMP/claude/mkdocs-check"`.

Poi test funzionale su dati reali: push su `main`, reinstall
`git+https://github.com/davidesidoti/unit3dprep.git@main` e restart sul VPS.

**Punto aperto**: il VPS Ultra.cc deve poter raggiungere Radarr e Sonarr via rete. Se
girano solo in LAN, il test funzionale va fatto sull'istanza di sviluppo WSL invece
che in produzione.

## Fuori ambito

- Riattivare il monitoraggio.
- Istanze multiple di Radarr o Sonarr.
- Traduzione dei path fra root diversi.
- Automatismi: nessuna rimozione automatica del monitoraggio al termine di un
  upload o allo scan delle lingue. L'azione resta sempre esplicita.
