# Deploy › Ultra.cc

Guida specifica per **[Ultra.cc](https://ultra.cc)**. Ultra.cc è un seedbox managed: niente `sudo`, niente Docker, Python da `pyenv` come utente non privilegiato, nginx in modalità "user-proxy" configurato via file in `~/.apps/nginx/proxy.d/`.

Tutta l'app gira come servizio **systemd user** (non system). L'URL pubblico finale ha la forma `https://<user>.<host>.usbx.me/itatorrents`.

Link ufficiali Ultra.cc su cui si basa questa guida:

- **Porte assegnate**: <https://docs.ultra.cc/unofficial-ssh-utilities/assigned-ports-command>
- **Generic software install + nginx user-proxy**: <https://docs.ultra.cc/unofficial-application-installers/generic-software-installation>

---

## 1 — SSH e porta riservata

Collegati in SSH alla tua macchina Ultra.cc.

Elenca le porte libere del tuo range:

```bash
app-ports free
```

Scegli una porta **all'interno del range assegnato** (es. `45678`) e annotala — la userai come `ITA_PORT`. Usare porte fuori range viola la Fair Usage Policy.

Mostra anche quelle già allocate ad altre app:

```bash
app-ports show
```

---

## 2 — Installa il pacchetto

Ultra.cc ha Python via `pyenv`. Verifica:

```bash
python3 --version
which python3
```

Su Ultra.cc il Python default è spesso 3.13 in pyenv, che ha `_sqlite3` rotto (`undefined symbol: sqlite3_deserialize`). **Non è un problema** per questo progetto: l'app usa storico JSON, non SQLite. Se però vedi altri tool andare in errore su `import sqlite3`, installa un Python 3.11 con `pyenv install 3.11` e fai `pyenv local 3.11.X`.

Clona e installa:

```bash
cd ~
git clone https://github.com/davidesidoti/itatorrents-seeding.git
cd itatorrents-seeding
python3 -m venv ~/.venvs/itatorrents
source ~/.venvs/itatorrents/bin/activate
pip install -e .
pip install unit3dup
```

Verifica che `unit3dup` sia nel PATH:

```bash
which unit3dup
# atteso: /home/<user>/.venvs/itatorrents/bin/unit3dup
```

---

## 3 — Secret e variabili d'ambiente

```bash
python generate_hash.py
```

L'output suggerisce già `ITA_HTTPS_ONLY=1`. Aggiungi le righe a `~/.bashrc`:

```bash
# itatorrents-seeding
export ITA_PASSWORD_HASH="$2b$12$..."
export ITA_SECRET="..."
export TMDB_API_KEY="..."
export ITA_HOST="127.0.0.1"
export ITA_PORT="45678"                 # la porta presa da `app-ports free`
export ITA_ROOT_PATH="/itatorrents"
export ITA_HTTPS_ONLY="1"

# opzionale — se i tuoi media stanno fuori ~/media
# export ITA_MEDIA_ROOT="/home/<user>/files/media"
# export ITA_SEEDINGS_DIR="/home/<user>/files/seedings"
```

Ricarica:

```bash
source ~/.bashrc
```

!!! note "Perché `ITA_ROOT_PATH=/itatorrents`"
    L'nginx di Ultra.cc **non** strippa il prefisso `/itatorrents` quando forwarda al backend. Quindi l'app FastAPI deve registrare tutte le route *con* quel prefisso (il codice lo fa automaticamente leggendo `ITA_ROOT_PATH`). Se metti `ITA_ROOT_PATH=""`, le route non matchano e vedi solo 404.

---

## 4 — Prepara cartelle

```bash
mkdir -p ~/media/{movies,series,anime} ~/seedings
df ~/media ~/seedings   # stesso filesystem?
```

Su Ultra.cc tipicamente `$HOME` è tutto sullo stesso device, quindi nessun problema. Se usi `~/files/` o path custom, verifica.

---

## 5 — Systemd user unit

Crea la cartella (se non esiste):

```bash
mkdir -p ~/.config/systemd/user
```

Crea `~/.config/systemd/user/itatorrents.service`:

```ini
[Unit]
Description=itatorrents-seeding web UI
After=network-online.target

[Service]
Type=exec
# %h = home dell'utente
EnvironmentFile=%h/.config/itatorrents.env
ExecStart=%h/.venvs/itatorrents/bin/itatorrents-web
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Sposta le variabili in un file dedicato (così systemd le trova anche senza passare da `~/.bashrc`):

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

Abilita e avvia:

```bash
systemctl --user daemon-reload
systemctl --user enable --now itatorrents.service
systemctl --user status itatorrents.service
journalctl --user -u itatorrents.service -f
```

Verifica lo stato di enable:

```bash
systemctl --user is-enabled itatorrents.service
```

!!! tip "Linger"
    Ultra.cc abilita `loginctl enable-linger` automaticamente per gli utenti, quindi il servizio parte anche senza sessione SSH attiva. Se dubbi:
    ```bash
    loginctl show-user $(whoami) | grep -i linger
    ```
    Se `Linger=no`, contatta il supporto.

!!! note "Nome della unit diverso?"
    L'auto-update in-app (bottone "Update app" nella Sidebar) usa `systemctl --user restart <unit>` al termine dell'aggiornamento. Il default è `itatorrents.service`; se hai rinominato la unit (es. `itatorrents-web.service`), aggiungi nel `[Service]` del file:
    ```ini
    Environment=ITA_SYSTEMD_UNIT=itatorrents-web.service
    ```
    oppure salva il nome in **Settings › App Auto-Update**. Senza questa configurazione `can_update_app` rimane `false` e il bottone è disabilitato.

---

## 6 — Nginx user-proxy

Crea (o modifica) `~/.apps/nginx/proxy.d/itatorrents.conf`:

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

!!! warning "Niente slash finale in `proxy_pass`"
    `proxy_pass http://127.0.0.1:45678;` (senza slash finale dopo la porta) → nginx **non strippa** `/itatorrents` → l'app lo riceve. Questo è l'abbinamento corretto con `ITA_ROOT_PATH=/itatorrents`. Se aggiungi uno slash finale (`http://127.0.0.1:45678/;`) nginx strippa e devi resettare `ITA_ROOT_PATH=""`.

Ricarica nginx:

```bash
app-nginx restart
```

(oppure dal pannello di controllo UCP → Nginx → Restart).

---

## 7 — Verifica

Apri nel browser:

```
https://<user>.<host>.usbx.me/itatorrents
```

Dovresti vedere il login. Inserisci la password.

Se vedi 404 o la pagina bianca:

1. `journalctl --user -u itatorrents -f` — il server è up?
2. `curl -I http://127.0.0.1:45678/itatorrents/` dalla shell — risponde 200?
3. Il file `~/.apps/nginx/proxy.d/itatorrents.conf` è stato caricato? `app-nginx restart` fatto?
4. `ITA_ROOT_PATH` combacia tra env e `proxy_pass`?

---

## 8 — Configurazione `unit3dup`

`unit3dup` su Ultra.cc si configura tramite lo stesso `Unit3Dbot.json`. Se non esiste ancora, la Web UI lo crea al primo salvataggio da Settings.

Imposta almeno:

- `ITT_URL`, `ITT_APIKEY`, `ITT_PID` (dal tuo profilo ItaTorrents)
- `TMDB_APIKEY` (stesso valore di `TMDB_API_KEY`)
- `TORRENT_CLIENT` = `qbittorrent` (tipicamente), `QBIT_HOST=127.0.0.1`, `QBIT_PORT=<porta qBit Ultra.cc>`, `QBIT_USER`, `QBIT_PASS`
- `TAG` = qualcosa tipo `ItaTorrentsBot` (appare nel nome file finale)

Alternativamente edita a mano:

```bash
nano ~/Unit3Dup_config/Unit3Dbot.json
```

(Ultra.cc potrebbe averlo in `~/.config/Unit3Dup/` o simile se lo hai installato diversamente — usa `UNIT3DUP_CONFIG` per puntarlo esplicitamente.)

---

## 9 — Upload di test

1. Metti un file `.mkv` con audio italiano in `~/media/movies/<Titolo>/`.
2. Apri la Web UI → Library → seleziona `movies` → l'item appare.
3. Click → Upload Wizard → segui i passi.
4. Verifica nello Storico che l'exit code diventi `0`.
5. In Queue dovrebbe comparire il torrent seedato dal tuo qBit.

---

## Aggiornamenti

### Via Web UI (consigliato)

Quando è disponibile una nuova release GitHub, in basso a sinistra nella Sidebar compare un banner "Update available". Click → il modal mostra `pip install` live-streamed, al termine countdown di reload automatico, post-reload popup con il changelog.

Lo stesso bottone gestisce anche `unit3dup` (latest da PyPI). Pre-requisiti: la user unit deve esistere ed essere accessibile a `systemctl --user cat`. Vedi la nota sopra se hai rinominato la unit.

### Manuale

Se preferisci aggiornare da shell (o se l'in-app update fallisce):

```bash
# installazione via pip-from-git (no checkout .git)
~/.venvs/itatorrents/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/davidesidoti/itatorrents-seeding.git@vX.Y.Z"
systemctl --user restart itatorrents.service

# oppure, se hai un checkout git con .git presente
cd ~/itatorrents-seeding
git pull --ff-only origin main
source ~/.venvs/itatorrents/bin/activate
pip install -e .
systemctl --user restart itatorrents.service
```

Frontend: il pacchetto pubblicato include già la `dist/` buildata, non serve Node su Ultra.cc.

---

## Troubleshooting specifico Ultra.cc

| Problema | Causa | Fix |
|---|---|---|
| 404 su `/itatorrents` | nginx non ricaricato | `app-nginx restart` |
| Pagina bianca, 200 OK | `ITA_ROOT_PATH` e `proxy_pass` disallineati | Senza slash → `ITA_ROOT_PATH=/itatorrents` |
| Cookie non persistenti | mancanza `ITA_HTTPS_ONLY=1` o mismatch protocollo | Impostalo e riavvia |
| Service non parte dopo logout | linger disabilitato | `loginctl show-user` / ticket supporto |
| `OSError: Invalid cross-device link` | `seedings` su FS diverso | Sposta `~/seedings` sotto `$HOME` |
| `unit3dup: command not found` | venv non attivo per systemd | `which unit3dup` → inseriscilo nel PATH via `Environment=PATH=%h/.venvs/itatorrents/bin:/usr/bin` in `.service` |

Vedi anche [Troubleshooting generale](troubleshooting.md).
