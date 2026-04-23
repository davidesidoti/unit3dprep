# Deployment › Ultra.cc

Specific guide for **[Ultra.cc](https://ultra.cc)**. Ultra.cc is a managed seedbox: no `sudo`, no Docker, Python from `pyenv` as an unprivileged user, nginx in "user-proxy" mode configured via files in `~/.apps/nginx/proxy.d/`.

The app runs as a **systemd user** service (not system). The final public URL looks like `https://<user>.<host>.usbx.me/itatorrents`.

Official Ultra.cc references this guide is based on:

- **Assigned ports**: <https://docs.ultra.cc/unofficial-ssh-utilities/assigned-ports-command>
- **Generic software install + nginx user-proxy**: <https://docs.ultra.cc/unofficial-application-installers/generic-software-installation>

---

## 1 — SSH and reserved port

SSH into your Ultra.cc machine.

List free ports from your assigned range:

```bash
app-ports free
```

Pick a port **inside your assigned range** (e.g. `45678`) and note it — you will use it as `ITA_PORT`. Using ports outside the range violates the Fair Usage Policy.

Show ports already allocated to other apps:

```bash
app-ports show
```

---

## 2 — Install the package

Ultra.cc ships Python via `pyenv`. Verify:

```bash
python3 --version
which python3
```

On Ultra.cc the default Python is often 3.13 in pyenv, which has a broken `_sqlite3` (`undefined symbol: sqlite3_deserialize`). **This is not a problem** for this project: the app uses JSON for history, not SQLite. But if you see other tools fail on `import sqlite3`, install Python 3.11 with `pyenv install 3.11` and `pyenv local 3.11.X`.

Clone and install:

```bash
cd ~
git clone https://github.com/davidesidoti/itatorrents-seeding.git
cd itatorrents-seeding
python3 -m venv ~/.venvs/itatorrents
source ~/.venvs/itatorrents/bin/activate
pip install -e .
pip install unit3dup
```

Check that `unit3dup` is on PATH:

```bash
which unit3dup
# expected: /home/<user>/.venvs/itatorrents/bin/unit3dup
```

---

## 3 — Secrets and environment variables

```bash
python generate_hash.py
```

The output already suggests `ITA_HTTPS_ONLY=1`. Add the lines to `~/.bashrc`:

```bash
# itatorrents-seeding
export ITA_PASSWORD_HASH="$2b$12$..."
export ITA_SECRET="..."
export TMDB_API_KEY="..."
export ITA_HOST="127.0.0.1"
export ITA_PORT="45678"                 # the port picked via `app-ports free`
export ITA_ROOT_PATH="/itatorrents"
export ITA_HTTPS_ONLY="1"

# optional — if your media live outside ~/media
# export ITA_MEDIA_ROOT="/home/<user>/files/media"
# export ITA_SEEDINGS_DIR="/home/<user>/files/seedings"
```

Reload:

```bash
source ~/.bashrc
```

!!! note "Why `ITA_ROOT_PATH=/itatorrents`"
    Ultra.cc's nginx **does not strip** the `/itatorrents` prefix when forwarding to the backend. So the FastAPI app must register every route *with* that prefix (the code does this automatically by reading `ITA_ROOT_PATH`). If you set `ITA_ROOT_PATH=""`, routes won't match and you'll see 404s.

---

## 4 — Prepare folders

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # same filesystem?
```

On Ultra.cc `$HOME` is typically all on the same device, so no problem. If you use `~/files/` or custom paths, verify.

---

## 5 — Systemd user unit

Create the folder if missing:

```bash
mkdir -p ~/.config/systemd/user
```

Create `~/.config/systemd/user/itatorrents.service`:

```ini
[Unit]
Description=itatorrents-seeding web UI
After=network-online.target

[Service]
Type=exec
# %h = user home
EnvironmentFile=%h/.config/itatorrents.env
ExecStart=%h/.venvs/itatorrents/bin/itatorrents-web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Move the variables into a dedicated file (so systemd finds them without relying on `~/.bashrc`):

```bash
mkdir -p ~/.config
cat > ~/.config/itatorrents.env <<'EOF'
ITA_PASSWORD_HASH=$2b$12$...
ITA_SECRET=...
TMDB_API_KEY=...
ITA_HOST=127.0.0.1
ITA_PORT=45678
ITA_ROOT_PATH=/itatorrents
ITA_HTTPS_ONLY=1
EOF
chmod 600 ~/.config/itatorrents.env
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now itatorrents.service
systemctl --user status itatorrents.service
journalctl --user -u itatorrents.service -f
```

Verify enable state:

```bash
systemctl --user is-enabled itatorrents.service
```

!!! tip "Linger"
    Ultra.cc enables `loginctl enable-linger` automatically for users, so the service starts even without an SSH session. If in doubt:
    ```bash
    loginctl show-user $(whoami) | grep -i linger
    ```
    If `Linger=no`, contact support.

!!! note "Renamed the unit?"
    The in-app auto-update ("Update app" button in the Sidebar) runs `systemctl --user restart <unit>` when done. Default is `itatorrents.service`; if you renamed the unit (e.g. `itatorrents-web.service`), add to the `[Service]` block:
    ```ini
    Environment=ITA_SYSTEMD_UNIT=itatorrents-web.service
    ```
    or save the name via **Settings › App Auto-Update**. Without this, `can_update_app` stays `false` and the button is disabled.

---

## 6 — Nginx user-proxy

Create (or edit) `~/.apps/nginx/proxy.d/itatorrents.conf`:

```nginx
location /itatorrents/ {
    proxy_pass              http://127.0.0.1:45678;
    proxy_http_version      1.1;
    proxy_set_header        Host              $host;
    proxy_set_header        X-Forwarded-Host  $http_host;
    proxy_set_header        X-Forwarded-Proto https;
    proxy_set_header        X-Real-IP         $remote_addr;
    proxy_set_header        Connection        "";
    proxy_buffering         off;
    proxy_read_timeout      1h;
    client_max_body_size    4g;
}
```

!!! warning "No trailing slash in `proxy_pass`"
    `proxy_pass http://127.0.0.1:45678;` (no trailing slash after the port) → nginx **does not strip** `/itatorrents` → the app receives it. This is the correct pairing with `ITA_ROOT_PATH=/itatorrents`. If you add a trailing slash (`http://127.0.0.1:45678/;`) nginx strips and you must set `ITA_ROOT_PATH=""`.

Reload nginx:

```bash
app-nginx restart
```

(or from the UCP panel → Nginx → Restart).

---

## 7 — Verify

Open in your browser:

```
https://<user>.<host>.usbx.me/itatorrents
```

You should see the login screen. Enter the password.

If you see a 404 or blank page:

1. `journalctl --user -u itatorrents -f` — is the server up?
2. `curl -I http://127.0.0.1:45678/itatorrents/` from the shell — does it answer 200?
3. Was `~/.apps/nginx/proxy.d/itatorrents.conf` loaded? Did you run `app-nginx restart`?
4. Does `ITA_ROOT_PATH` match `proxy_pass`?

---

## 8 — `unit3dup` configuration

`unit3dup` on Ultra.cc configures via the same `Unit3Dbot.json`. If it does not exist yet, the Web UI creates it on the first Settings save.

Set at least:

- `ITT_URL`, `ITT_APIKEY`, `ITT_PID` (from your ItaTorrents profile)
- `TMDB_APIKEY` (same value as `TMDB_API_KEY`)
- `TORRENT_CLIENT` = `qbittorrent` (typically), `QBIT_HOST=127.0.0.1`, `QBIT_PORT=<your Ultra.cc qBit port>`, `QBIT_USER`, `QBIT_PASS`
- `TAG` = something like `ItaTorrentsBot` (it appears in the final filename)

Or edit by hand:

```bash
nano ~/Unit3Dup_config/Unit3Dbot.json
```

(Ultra.cc may have it at `~/.config/Unit3Dup/` or similar if you installed differently — use `UNIT3DUP_CONFIG` to point explicitly.)

---

## 9 — Test upload

1. Put a `.mkv` file with Italian audio into `~/media/movies/<Title>/`.
2. Open the Web UI → Library → select `movies` → the item appears.
3. Click → Upload Wizard → follow the steps.
4. Check in History that the exit code becomes `0`.
5. In Queue the torrent should appear, seeded by your qBit.

---

## Updates

### Via Web UI (recommended)

When a new GitHub release is available, an "Update available" banner appears at the bottom-left of the Sidebar. Click → modal shows `pip install` live-streamed, followed by an auto-reload countdown, then a post-reload popup with the changelog.

The same button handles `unit3dup` (latest from PyPI). Prerequisites: the user unit must exist and be accessible via `systemctl --user cat`. See the note above if you renamed it.

### Manual

If you prefer the shell (or if in-app update fails):

```bash
# pip-from-git install (no .git checkout)
~/.venvs/itatorrents/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/itatorrents-seeding.git@vX.Y.Z"
systemctl --user restart itatorrents.service

# or, if you have a git checkout with .git present
cd ~/itatorrents-seeding
git pull --ff-only origin main
source ~/.venvs/itatorrents/bin/activate
pip install -e .
systemctl --user restart itatorrents.service
```

Frontend: the published package ships the pre-built `dist/`, no Node needed on Ultra.cc.

---

## Ultra.cc-specific troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| 404 on `/itatorrents` | nginx not reloaded | `app-nginx restart` |
| Blank page, 200 OK | `ITA_ROOT_PATH` and `proxy_pass` misaligned | No trailing slash → `ITA_ROOT_PATH=/itatorrents` |
| Cookie not persisting | missing `ITA_HTTPS_ONLY=1` or protocol mismatch | Set it and restart |
| Service does not start after logout | linger disabled | `loginctl show-user` / support ticket |
| `OSError: Invalid cross-device link` | `seedings` on a different FS | Move `~/seedings` under `$HOME` |
| `unit3dup: command not found` | venv not active for systemd | `which unit3dup` → add it to PATH via `Environment=PATH=%h/.venvs/itatorrents/bin:/usr/bin` in `.service` |

See also [general Troubleshooting](troubleshooting.md).
