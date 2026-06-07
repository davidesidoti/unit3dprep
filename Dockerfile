# unit3dprep — all-in-one image (Redis + Unit3DWebUp + unit3dprep web UI).
#
# Why a single container instead of one-service-per-container?
#   Unit3DWebUp hardcodes Redis at localhost:6379 and ignores REDIS_HOST/PORT,
#   so Redis MUST share webup's network namespace. Co-locating all three
#   processes also keeps media + seedings on one filesystem (hardlinks work)
#   and lets unit3dprep reach webup over loopback for both HTTP and WebSocket.
#
# The frontend SPA is shipped pre-built (unit3dprep/web/dist/ is committed and
# packaged as package-data), so no Node toolchain is needed at build time.

# Python 3.12+ required: Unit3DwebUp (PyPI) ships only wheels for >=3.12.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    HOME=/data \
    ENVPATH=/data \
    U3DP_HOST=0.0.0.0 \
    U3DP_PORT=8765 \
    U3DP_HTTPS_ONLY=0 \
    U3DP_IN_DOCKER=1 \
    WEBUP_URL=http://127.0.0.1:8000

# libmediainfo + ffmpeg: required by webup (mediainfo extraction + screenshots).
# redis-server: webup's mandatory job store (localhost:6379).
# curl: entrypoint health probe.
# gosu: drop privileges to PUID:PGID in the entrypoint so files written under
#       the bind-mounted /data are owned by the host user, not root.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libmediainfo0v5 ffmpeg redis-server curl ca-certificates gosu \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . Unit3DwebUp

# IMPORTANT: do NOT set the DOCKER env var. Webup's config does
#   env_file = ENV_FILE if not os.getenv("DOCKER") else None
# i.e. a bare truthy check — ANY value (even "false") makes webup ignore the
# shared .env file and every TRACKER__/PREFS__ field reports "Field required".
# We share config through the .env, so DOCKER must stay unset.

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

VOLUME ["/data"]
EXPOSE 8765

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
