#!/usr/bin/env bash
# Boot the all-in-one stack: drop privileges -> Redis -> seed .env ->
# Unit3DWebUp -> unit3dprep.
set -euo pipefail

DATA_DIR="${ENVPATH:-/data}"

# ---------------------------------------------------------------------------
# Privilege drop. The container starts as root so it can chown the bind-mounted
# /data and create the runtime user, then re-execs itself as PUID:PGID. This
# makes every file written under /data (config, db, torrents, hardlinks) owned
# by the host user instead of root — no more `sudo` to manage media/seedings.
#
# Defaults 1000:1000 = the first Linux/WSL user. Override in config.env:
#   PUID=$(id -u)   PGID=$(id -g)
# Set PUID=0 to keep running as root (legacy behaviour).
# ---------------------------------------------------------------------------
if [ "$(id -u)" = "0" ]; then
    PUID="${PUID:-1000}"
    PGID="${PGID:-1000}"
    echo "[entrypoint] dropping privileges to ${PUID}:${PGID}"

    # Create a group/user with the requested ids if they don't already exist.
    if ! getent group "${PGID}" >/dev/null 2>&1; then
        groupadd -g "${PGID}" app
    fi
    if ! getent passwd "${PUID}" >/dev/null 2>&1; then
        useradd -u "${PUID}" -g "${PGID}" -d "${DATA_DIR}" -M -s /usr/sbin/nologin app
    fi

    mkdir -p "${DATA_DIR}" "${DATA_DIR}/media" "${DATA_DIR}/seedings"
    # Own all app state (config .env, JSON db, caches, torrent archive, seedings
    # hardlinks) so the unprivileged process can read AND rewrite it — this also
    # migrates a /data left root-owned by an older (root) image. media/ is the
    # one tree we DON'T recurse: it may be huge or a read-only mount, and reading
    # it only needs the read bit anyway.
    chown "${PUID}:${PGID}" "${DATA_DIR}" "${DATA_DIR}/media" 2>/dev/null || true
    find "${DATA_DIR}" -mindepth 1 -maxdepth 1 ! -name media \
        -exec chown -R "${PUID}:${PGID}" {} + 2>/dev/null || true

    # Hand site-packages + console scripts to the runtime user so the in-UI
    # update button (Settings → Version) can `pip install --upgrade` in place.
    # The package is installed as root at build time; without this chown the
    # unprivileged process can't write site-packages and the update fails.
    PYLIB="$(python -c 'import sysconfig; print(sysconfig.get_path("purelib"))' 2>/dev/null || true)"
    if [ -n "${PYLIB}" ]; then
        chown -R "${PUID}:${PGID}" "${PYLIB}" /usr/local/bin 2>/dev/null || true
    fi

    # Re-exec this same script as the unprivileged user.
    exec gosu "${PUID}:${PGID}" "$0" "$@"
fi

# ---- From here on we run as the unprivileged user. ------------------------
echo "[entrypoint] running as $(id -u):$(id -g)"
echo "[entrypoint] data dir: ${DATA_DIR}"
mkdir -p "${DATA_DIR}" "${DATA_DIR}/media" "${DATA_DIR}/seedings"

# 1. Redis — webup hardcodes localhost:6379 (REDIS_HOST/PORT are ignored).
#    Persistence is disabled (--save "" --appendonly no): webup uses Redis as a
#    transient job store, so there's nothing worth saving across restarts. This
#    also means no background-save fork (so the kernel "Memory overcommit must be
#    enabled" warning is moot) and no dump.rdb cluttering the /data volume.
echo "[entrypoint] starting redis on 127.0.0.1:6379"
redis-server --bind 127.0.0.1 --port 6379 --daemonize yes --dir "${DATA_DIR}" \
    --save "" --appendonly no

# 2. Seed the shared .env on first boot so webup starts cleanly. seed_initial_env()
#    materializes safe defaults (TORRENT_ARCHIVE_PATH, SCAN_PATH=".",
#    PREFERRED_LANG="it") that satisfy webup's empty_to_none / Path.exists()
#    boot checks, and folds in API keys / client settings supplied via env vars
#    (config.env: TMDB_API_KEY, ITT_APIKEY, QBIT_*, …) so webup reads them at
#    startup instead of logging "*_APIKEY not set". No-op if the .env exists.
if [ ! -f "${DATA_DIR}/.env" ]; then
    echo "[entrypoint] seeding ${DATA_DIR}/.env"
    python -c "from unit3dprep.web import config; ks = config.seed_initial_env(); print('[entrypoint] seeded from env:', ', '.join(ks) or '(none)')"
fi

# 3. Unit3DWebUp (internal only) with a tiny auto-restart loop so a webup crash
#    doesn't silently leave the stack half-up. unit3dprep talks to it over
#    loopback (WEBUP_URL=http://127.0.0.1:8000) for both HTTP and WebSocket.
echo "[entrypoint] starting Unit3DWebUp on 127.0.0.1:8000"
(
    while true; do
        uvicorn unit3dwup.start:app --host 127.0.0.1 --port 8000 || true
        echo "[entrypoint] webup exited, restarting in 3s" >&2
        sleep 3
    done
) &

# 4. Wait (best-effort) for webup to answer before the UI comes up.
echo "[entrypoint] waiting for webup health…"
for _ in $(seq 1 30); do
    if curl -fsS -X POST http://127.0.0.1:8000/setting \
            -H 'Content-Type: application/json' -d '{}' >/dev/null 2>&1; then
        echo "[entrypoint] webup is up"
        break
    fi
    sleep 1
done

# 5. unit3dprep web UI in the foreground (binds 0.0.0.0:8765 via U3DP_HOST).
echo "[entrypoint] starting unit3dprep-web on ${U3DP_HOST:-0.0.0.0}:${U3DP_PORT:-8765}"
exec unit3dprep-web
