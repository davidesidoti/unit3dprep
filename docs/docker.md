# Deploy › Docker

Setup **all-in-one**: un singolo container con Redis + Unit3DWebUp + unit3dprep, avviati
da un entrypoint. È il modo più semplice e robusto per mettere in piedi lo stack — non
serve `sudo`, systemd o Node.

```
┌─────────────────── container unit3dprep ───────────────────┐
│                                                             │
│  unit3dprep-web (0.0.0.0:8765)                              │
│        │  HTTP + WS                                         │
│        └─────────> Unit3DWebUp (127.0.0.1:8000)             │
│                          │                                  │
│                          ├─> Redis (127.0.0.1:6379)         │
│                          └─> qBittorrent (esterno / host)   │
│                                                             │
│  .env condivisa + media + seedings sotto /data (un volume)  │
└─────────────────────────────────────────────────────────────┘
```

!!! info "Perché un solo container?"
    Unit3DWebUp **hardcoda** Redis su `localhost:6379` e ignora `REDIS_HOST`/`REDIS_PORT`.
    Redis deve quindi condividere il network namespace di webup. Tenere tutto insieme
    mantiene anche `media` e `seedings` sullo **stesso filesystem** (gli hardlink funzionano)
    e fa raggiungere webup a unit3dprep via loopback (HTTP **e** WebSocket).

---

## 1 — Prerequisiti

- [Docker Engine](https://docs.docker.com/engine/install/) + **Compose v2** (`docker compose version`).
  **Compose v2 è richiesto** (installazione sotto, se manca). La vecchia `docker-compose` v1 (1.29.2,
  Python — EOL) **non** è supportata: è incompatibile con Docker Engine 25+ e fa crashare
  `docker compose up` con `KeyError: 'ContainerConfig'` (vedi [Troubleshooting](#troubleshooting)).
- qBittorrent raggiungibile (sul tuo host o in un altro container) **se** vuoi fare il
  seed reale. Per provare solo l'interfaccia non serve subito.

**Installare Compose v2** (se `docker compose version` non funziona) — plugin CLI utente, senza repo né `sudo`:

```bash
mkdir -p ~/.docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
```

In alternativa, se hai configurato il [repo APT ufficiale Docker](https://docs.docker.com/engine/install/): `sudo apt-get install docker-compose-plugin` (il pacchetto **non** è nei repo standard di Debian/Ubuntu).

---

## 2 — Clona il repo e prepara la config

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
cp config.env.example config.env
```

!!! warning "Serve Compose v2 — leggi prima di continuare"
    I comandi usano `docker compose` (Compose **v2**). Verifica con `docker compose version`; se
    manca, installalo come mostrato in [§1](#1-prerequisiti). **Non** usare la vecchia
    `docker-compose` v1 (1.29.2): con Docker Engine 25+ fa crashare `docker compose up` con
    `KeyError: 'ContainerConfig'`.

Genera l'hash della password della web UI (interattivo):

```bash
docker compose run --rm --entrypoint python unit3dprep /app/generate_hash.py
```

Copia il valore `$2b$…` in `config.env` alla voce `U3DP_PASSWORD_HASH` (senza virgolette).
Compila anche gli altri campi:

```ini
U3DP_PASSWORD_HASH=$2b$12$....................................................
U3DP_SECRET=<stringa-random-lunga>
TMDB_API_KEY=<la-tua-chiave-tmdb>
U3DP_HTTPS_ONLY=0
PUID=1000
PGID=1000
```

!!! tip "Genera il secret"
    `python -c "import secrets; print(secrets.token_urlsafe(48))"`

!!! tip "Setup headless: precompila le chiavi"
    `TMDB_API_KEY` (e, opzionali, `ITT_APIKEY`/`ITT_PID`/`TVDB_APIKEY`/`QBIT_*` —
    vedi `config.env.example`) vengono iniettate nella `.env` al **primo boot**, così
    Unit3DWebUp le legge subito e niente più warning `*_APIKEY not set`. Sono lette solo
    quando la `.env` non esiste ancora: dopo, la `.env` è autoritativa e modifichi tutto da
    **Settings** nella web UI (queste env var vengono ignorate ai boot successivi).

!!! tip "PUID/PGID — niente `sudo` per gestire i media"
    Lo stack gira dentro al container come `PUID:PGID`, quindi i file scritti nel volume
    `./data` (config, db, torrent, hardlink) appartengono a quegli id. Imposta **il tuo
    utente host** così puoi mettere/togliere media in `./data/media` senza `sudo`:
    lancia `id` sull'host e copia `uid`/`gid` in `config.env`. Default `1000:1000` (il primo
    utente Linux/WSL). `PUID=0` per girare come root (comportamento legacy).

!!! warning "L'hash bcrypt contiene `$`"
    `config.env` è passato al container via `env_file:` → i valori sono **letterali**, quindi
    l'hash con i `$` va bene così. **Non** usare l'interpolazione `${U3DP_PASSWORD_HASH}` nel
    `docker-compose.yml` (richiederebbe di raddoppiare ogni `$` in `$$`).

---

## 3 — Avvia

```bash
docker compose up -d
docker compose logs -f
```

Il `docker-compose.yml` usa già l'immagine pubblicata su Docker Hub
([`hashdeveloper512/unit3dprep`](https://hub.docker.com/r/hashdeveloper512/unit3dprep),
tag `latest`/`X.Y.Z`): `docker compose up -d` la scarica automaticamente senza build.

!!! tip "Vuoi buildare l'immagine in locale?"
    Apri `docker-compose.yml`, commenta `image:` e decommenta `build: .`, poi lancia
    `docker compose build && docker compose up -d`.

Nei log dovresti vedere, in ordine (prefisso `[entrypoint]`): `starting redis on 127.0.0.1:6379`,
`seeding /data/.env`, `webup is up`, e infine `starting unit3dprep-web on 0.0.0.0:8765` seguito
dalla riga di uvicorn `Application startup complete`.

Apri **<http://127.0.0.1:8765>** e fai login con la password scelta al punto 2.

In **Settings** la card *Unit3DWebUp* deve essere **verde** (online): unit3dprep la raggiunge
su `127.0.0.1:8000` dentro al container.

---

## 4 — qBittorrent esterno e mapping dei path

Il container **non** include qBittorrent. Quando webup fa il `/seed`, passa a qBittorrent il
percorso del file **così come lo vede dentro al container** (di default `/data/seedings/…`).
Perché qBittorrent lo trovi davvero, quel percorso deve essere valido anche dal suo punto di vista.

Ricetta consigliata — **monta gli stessi path assoluti** dell'host:

```yaml
    volumes:
      - ./data:/data
      - /srv/media:/srv/media:ro
      - /srv/seedings:/srv/seedings
    environment:
      U3DP_MEDIA_ROOT: /srv/media
      U3DP_SEEDINGS_DIR: /srv/seedings
```

Così il file in `/srv/seedings/…` ha lo stesso percorso dentro al container e sull'host dove
gira qBittorrent. In **Settings → Client** punta `QBIT_HOST`/`QBIT_PORT` al tuo qBittorrent
(per il qBit dell'host da dentro al container usa `host.docker.internal`, oppure l'IP dell'host).

!!! danger "Hardlink = stesso filesystem"
    L'hardlink tra `media` e `seedings` riesce solo se le due cartelle stanno sullo **stesso
    filesystem**. Con il default (tutto sotto `/data`) è garantito. Se monti path host separati,
    assicurati che `media` e `seedings` siano sullo stesso filesystem dell'host.

!!! tip "Provare senza toccare il tracker"
    Aggiungi `U3DP_DRY_RUN_TRACKER=1` in `config.env` per eseguire scan → maketorrent → seed
    saltando l'upload al tracker. Utile per validare il setup end-to-end senza pubblicare nulla.

---

## 5 — HTTPS / reverse proxy

Il compose pubblica la porta **solo su loopback** (`127.0.0.1:8765`). Per l'accesso remoto
metti davanti un reverse proxy con TLS (Caddy, Traefik, nginx) che punta a `127.0.0.1:8765`,
e imposta `U3DP_HTTPS_ONLY=1` in `config.env`.

!!! warning "`U3DP_HTTPS_ONLY=1` solo dietro HTTPS"
    Con `U3DP_HTTPS_ONLY=1` il cookie di sessione diventa `https-only`: servito su HTTP puro,
    il login *sembra* riuscire ma la sessione non persiste → **401 perenne**. Tienilo a `0`
    finché non hai un proxy TLS davanti.

---

## 6 — Aggiornamento

```bash
docker compose pull
docker compose up -d
```

I dati (config, db, media, seedings) vivono nel volume `./data` e sopravvivono all'aggiornamento.
Questo è il metodo **canonico**: scarica la nuova immagine e ricrea il container.

!!! tip "Usi la build locale?"
    Se hai decommentato `build: .` nel `docker-compose.yml`, aggiorna con
    `git pull && docker compose build && docker compose up -d`.

### Aggiornamento dal bottone in UI

Anche in Docker puoi lanciare l'aggiornamento dell'app e di Unit3DWebUp dal bottone
**Impostazioni → Versione** quando è disponibile una nuova release. L'update viene applicato
*in-place* dentro al container (`pip install --upgrade`) e poi il container si **riavvia da solo**.

!!! warning "L'update in-UI è temporaneo"
    L'aggiornamento in-UI vive nel filesystem del container: sopravvive ai riavvii ma viene
    **azzerato al successivo `docker compose pull`** (che riparte dalla versione dell'immagine).
    È una comodità per aggiornare subito senza toccare la shell; il metodo definitivo resta
    `docker compose pull && docker compose up -d`.

    Il riavvio si basa sulla restart policy del container: il `docker-compose.yml` fornito ha
    `restart: unless-stopped`, quindi il container riparte da solo. Se lanci l'immagine con un
    `docker run` senza `--restart`, dopo l'update il container resterà fermo e dovrai riavviarlo
    a mano.

---

## Troubleshooting

| Sintomo | Causa probabile | Fix |
| --- | --- | --- |
| `KeyError: 'ContainerConfig'` su `docker compose up` | `docker-compose` v1 (1.29.2) incompatibile con Docker Engine 25+ | Installa **Compose v2** ([§1](#1-prerequisiti)), rimuovi i container orfani (`docker rm -f unit3dprep`), poi `docker compose up -d` |
| Login "riesce" ma resti sloggato (401) | `U3DP_HTTPS_ONLY=1` su HTTP puro | Metti `U3DP_HTTPS_ONLY=0` (o un proxy TLS davanti) |
| `http://127.0.0.1:8765` non risponde | container non in salute | `docker compose logs -f`; verifica che compaia `starting unit3dprep-web on 0.0.0.0:8765` + `Application startup complete` |
| Card Unit3DWebUp **grigia/rossa** | webup non parte | Controlla i log; al primo boot la `.env` viene seminata automaticamente |
| webup logga "Field required" | env `DOCKER` impostata | Non impostare mai `DOCKER` (l'immagine non lo fa: lascialo così) |
| Redis logga "Memory overcommit must be enabled" | sysctl host `vm.overcommit_memory != 1` | **Innocuo**: la persistenza di Redis è disabilitata (job-store transitorio), nessun background-save. Per silenziarlo sull'host: `sudo sysctl vm.overcommit_memory=1` |
| `Permission denied` su `./data` (mkdir/cp media) | `PUID`/`PGID` ≠ tuo utente host | Metti `PUID`/`PGID` = `id -u`/`id -g` in `config.env`, poi `docker compose up -d`. Per i file già root-owned: `sudo chown -R $(id -u):$(id -g) ./data` |
| Seed fallisce / "InfoHash not found" | path qBit non allineati | Vedi [§4](#4-qbittorrent-esterno-e-mapping-dei-path) |
