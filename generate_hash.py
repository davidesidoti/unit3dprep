#!/usr/bin/env python3
"""Run once locally to generate ITA_PASSWORD_HASH and ITA_SECRET for ~/.bashrc."""
import getpass
import secrets
import sys

try:
    import bcrypt
except ImportError:
    print("Installa bcrypt: pip install bcrypt")
    sys.exit(1)

pw = getpass.getpass("Scegli una password per la web UI: ").encode()
pw2 = getpass.getpass("Ripeti password: ").encode()
if pw != pw2:
    print("Le password non corrispondono.")
    sys.exit(1)

h = bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode()
secret = secrets.token_hex(32)

print(f"""
✅ Aggiungi queste righe a ~/.bashrc (o ~/.profile) sul VPS:

export ITA_PASSWORD_HASH="{h}"
export ITA_SECRET="{secret}"
export TMDB_API_KEY="<la_tua_chiave_tmdb>"
export ITA_PORT="<porta_riservata_ultracc>"
export ITA_HTTPS_ONLY="1"

Poi: source ~/.bashrc
""")
