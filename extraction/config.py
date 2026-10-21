"""Configuration centralisée de l'extraction (chemins, URLs, limites de débit).

Les secrets (sel de pseudonymisation, identifiants BDD) sont lus depuis le
fichier .env, jamais écrits en dur dans le code.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- Dossiers de données ---------------------------------------------------
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"            # sorties brutes de l'extraction
EXTERNAL_DIR = DATA_DIR / "external"  # fichiers téléchargés (Kaggle)
LOG_DIR = ROOT_DIR / "logs"

# --- Sources web -----------------------------------------------------------
STEAMSPY_URL = "https://steamspy.com/api.php"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
STEAM_STORE_PAGE_URL = "https://store.steampowered.com/app/{appid}/"

# Paramètres régionaux : prix en euros, textes en anglais (dates parsables)
STEAM_COUNTRY = "fr"
STEAM_LANGUAGE = "english"

# --- Limites de débit (secondes entre deux requêtes) ----------------------
# SteamSpy : 1 req/s, et 1 req/60 s pour request=all (doc officielle)
STEAMSPY_DELAY = 1.0
STEAMSPY_ALL_DELAY = 60.0
# Steam Store : ~200 requêtes / 5 min tolérées (non documenté officiellement)
STEAM_DELAY = 1.8

# --- Périmètre -------------------------------------------------------------
DEFAULT_GAME_LIMIT = int(os.getenv("GAME_LIMIT", 2000))
REVIEWS_PER_GAME = int(os.getenv("REVIEWS_PER_GAME", 20))

USER_AGENT = "GameScope/1.0 (projet pedagogique Simplon)"

# --- RGPD ------------------------------------------------------------------
# Sel utilisé pour pseudonymiser les identifiants Steam dès la collecte
PSEUDO_SALT = os.getenv("PSEUDO_SALT", "")
