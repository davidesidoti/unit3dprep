# Deploy › Docker

**All-in-one** setup: a single container running Redis + Unit3DWebUp + unit3dprep, started
by one entrypoint. The simplest, most robust way to stand the stack up — no `sudo`, systemd
or Node required.

```
┌─────────────────── unit3dprep container ───────────────────┐
│                                                             │
│  unit3dprep-web (0.0.0.0:8765)                              │
│        │  HTTP + WS                                         │
│        └─────────> Unit3DWebUp (127.0.0.1:8000)             │
│                          │                                  │
│                          ├─> Redis (127.0.0.1:6379)         │
│                          └─> qBittorrent (external / host)  │
│                                                             │
│  shared .env + media + seedings under /data (one volume)    │
└─────────────────────────────────────────────────────────────┘
```

!!! info "Why a single container?"
    Unit3DWebUp **hardcodes** Redis at `localhost:6379` and ignores `REDIS_HOST`/`REDIS_PORT`,
    so Redis must share webup's network namespace. Keeping everything together also keeps
    `media` and `seedings` on the **same filesystem** (hardlinks work) and lets unit3dprep
    reach webup over loopback (HTTP **and** WebSocket).

---

## 1 — Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/) + **Compose v2**.
  Check with `docker compose version`. If it fails, on Debian/Ubuntu install the plugin with
  `sudo apt-get install docker-compose-plugin`. Alternatively, with the legacy
  **`docker-compose` v1** (hyphenated, `docker-compose version`) the commands still work:
  replace `docker compose` with `docker-compose` in **all** the commands below.
- A reachable qBittorrent (on your host or another container) **if** you want real seeding.
  Not needed just to try the UI.

---

## 2 — Clone the repo and prepare config

```bash
git clone https://github.com/davidesidoti/unit3dprep.git
cd unit3dprep
cp config.env.example config.env
```

!!! warning "`docker compose` (v2) vs `docker-compose` (v1) — read before continuing"
    The commands in this guide use `docker compose` (Compose **v2**). If `docker compose version`
    fails and you only have `docker-compose` v1 (hyphenated), use **`docker-compose`** in **all**
    the commands below: `docker-compose run …`, `docker-compose build`, `docker-compose up -d`,
    `docker-compose logs -f`. (See [§1](#1-prerequisites) to install the v2 plugin.)

Generate the web UI password hash (interactive):

```bash
docker compose run --rm --entrypoint python unit3dprep /app/generate_hash.py
```

Copy the `$2b$…` value into `config.env` under `U3DP_PASSWORD_HASH` (no quotes), and fill in
the rest:

```ini
U3DP_PASSWORD_HASH=$2b$12$....................................................
U3DP_SECRET=<long-random-string>
TMDB_API_KEY=<your-tmdb-key>
U3DP_HTTPS_ONLY=0
PUID=1000
PGID=1000
```

!!! tip "Generate the secret"
    `python -c "import secrets; print(secrets.token_urlsafe(48))"`

!!! tip "Headless setup: pre-seed your keys"
    `TMDB_API_KEY` (plus optional `ITT_APIKEY`/`ITT_PID`/`TVDB_APIKEY`/`QBIT_*` — see
    `config.env.example`) are injected into the `.env` on **first boot**, so Unit3DWebUp
    reads them right away and the `*_APIKEY not set` warnings go away. They're read only
    while the `.env` doesn't exist yet: afterwards the `.env` is authoritative and you edit
    everything from **Settings** in the web UI (these env vars are ignored on later boots).

!!! tip "PUID/PGID — no `sudo` to manage media"
    The stack runs inside the container as `PUID:PGID`, so files written to the `./data`
    volume (config, db, torrents, hardlinks) are owned by those ids. Set them to **your host
    user** so you can add/remove media under `./data/media` without `sudo`: run `id` on the
    host and copy `uid`/`gid` into `config.env`. Defaults to `1000:1000` (the first Linux/WSL
    user). Use `PUID=0` to run as root (legacy behaviour).

!!! warning "The bcrypt hash contains `$`"
    `config.env` is passed to the container via `env_file:` → values are **literal**, so the
    hash with its `$` characters is fine as-is. Do **not** use `${U3DP_PASSWORD_HASH}`
    interpolation in `docker-compose.yml` (that would require doubling every `$` to `$$`).

---

## 3 — Start it

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

In the logs you should see, in order (prefixed `[entrypoint]`): `starting redis on 127.0.0.1:6379`,
`seeding /data/.env`, `webup is up`, and finally `starting unit3dprep-web on 0.0.0.0:8765` followed
by uvicorn's `Application startup complete`.

Open **<http://127.0.0.1:8765>** and log in with the password from step 2.

In **Settings** the *Unit3DWebUp* card must be **green** (online): unit3dprep reaches it at
`127.0.0.1:8000` inside the container.

---

## 4 — External qBittorrent and path mapping

The container does **not** include qBittorrent. When webup runs `/seed` it hands qBittorrent
the file path **as seen inside the container** (by default `/data/seedings/…`). For
qBittorrent to actually find it, that path must be valid from its point of view too.

Recommended recipe — **mount the same absolute host paths**:

```yaml
    volumes:
      - ./data:/data
      - /srv/media:/srv/media:ro
      - /srv/seedings:/srv/seedings
    environment:
      U3DP_MEDIA_ROOT: /srv/media
      U3DP_SEEDINGS_DIR: /srv/seedings
```

Now the file in `/srv/seedings/…` has the same path inside the container and on the host where
qBittorrent runs. In **Settings → Client** point `QBIT_HOST`/`QBIT_PORT` at your qBittorrent
(for the host's qBit from inside the container use `host.docker.internal`, or the host IP).

!!! danger "Hardlinks = same filesystem"
    Hardlinking between `media` and `seedings` only works if both directories live on the
    **same filesystem**. With the default (everything under `/data`) that's guaranteed. If you
    mount separate host paths, make sure `media` and `seedings` are on the same host filesystem.

!!! tip "Try it without touching the tracker"
    Add `U3DP_DRY_RUN_TRACKER=1` to `config.env` to run scan → maketorrent → seed while
    skipping the tracker upload. Handy to validate the setup end-to-end without publishing.

---

## 5 — HTTPS / reverse proxy

Compose publishes the port on **loopback only** (`127.0.0.1:8765`). For remote access put a
TLS reverse proxy (Caddy, Traefik, nginx) in front pointing at `127.0.0.1:8765`, and set
`U3DP_HTTPS_ONLY=1` in `config.env`.

!!! warning "`U3DP_HTTPS_ONLY=1` only behind HTTPS"
    With `U3DP_HTTPS_ONLY=1` the session cookie becomes `https-only`: served over plain HTTP
    the login *appears* to succeed but the session never persists → **endless 401**. Keep it
    at `0` until you have a TLS proxy in front.

---

## 6 — Updating

```bash
git pull
docker compose build
docker compose up -d
```

Your data (config, db, media, seedings) lives in the `./data` volume and survives the rebuild.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Login "succeeds" but you stay logged out (401) | `U3DP_HTTPS_ONLY=1` over plain HTTP | Set `U3DP_HTTPS_ONLY=0` (or put a TLS proxy in front) |
| `http://127.0.0.1:8765` doesn't respond | container unhealthy | `docker compose logs -f`; check for `starting unit3dprep-web on 0.0.0.0:8765` + `Application startup complete` |
| Unit3DWebUp card **grey/red** | webup didn't start | Check the logs; the `.env` is seeded automatically on first boot |
| webup logs "Field required" | `DOCKER` env var is set | Never set `DOCKER` (the image doesn't — leave it that way) |
| Redis logs "Memory overcommit must be enabled" | host sysctl `vm.overcommit_memory != 1` | **Harmless**: Redis persistence is disabled (transient job store), no background save. To silence it on the host: `sudo sysctl vm.overcommit_memory=1` |
| `Permission denied` on `./data` (mkdir/cp media) | `PUID`/`PGID` ≠ your host user | Set `PUID`/`PGID` to `id -u`/`id -g` in `config.env`, then `docker compose up -d`. For files already owned by root: `sudo chown -R $(id -u):$(id -g) ./data` |
| Seed fails / "InfoHash not found" | qBit paths not aligned | See [§4](#4-external-qbittorrent-and-path-mapping) |
