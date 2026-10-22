"""Crée le fichier .env à partir de .env.example en générant chaque secret manquant.

Usage :
    python scripts/init_env.py

Un .env existant n'est jamais écrasé : le sel de pseudonymisation (PSEUDO_SALT)
doit rester le même tant que les données collectées sont conservées, sinon un
même joueur aurait deux empreintes différentes et le droit à l'effacement ne
pourrait plus le retrouver.
"""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = {
    "PSEUDO_SALT": lambda: secrets.token_hex(32),
    "PARTNER_DB_PASSWORD": lambda: secrets.token_urlsafe(18),
    "PARTNER_READER_PASSWORD": lambda: secrets.token_urlsafe(18),
    "GAMESCOPE_DB_PASSWORD": lambda: secrets.token_urlsafe(18),
    "GAMESCOPE_API_PASSWORD": lambda: secrets.token_urlsafe(18),
    "GAMESCOPE_ANALYST_PASSWORD": lambda: secrets.token_urlsafe(18),
    "JWT_SECRET_KEY": lambda: secrets.token_urlsafe(48),
}


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env existe déjà : rien n'est modifié.")
        return 0
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key in SECRETS and not value:
            line = f"{key}={SECRETS[key]()}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f".env créé avec {len(SECRETS)} secrets générés aléatoirement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
