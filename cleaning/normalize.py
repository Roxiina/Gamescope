"""Fonctions d'homogénéisation des formats, testées dans tests/test_normalize.py.

Conventions du jeu de données final :
- dates           : datetime.date (ISO 8601 à l'export)
- prix            : float en euros, 0.0 pour un jeu gratuit
- durées          : minutes (entier)
- ventes          : unités (entier), et non millions
- pourcentages    : float entre 0 et 100
- langues         : codes BCP 47 (en, zh-Hans, pt-BR...)
- noms            : sans ™ ® ©, espaces normalisés
"""
import math
import re
import unicodedata
from datetime import date, datetime

# --- Noms ------------------------------------------------------------------
TRADEMARKS_RE = re.compile(r"[™®©]")
SPACES_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")
APOSTROPHES_RE = re.compile(r"['’‘`´]")
ROMAN_RE = re.compile(r"^(?=[ivxl]+$)x{0,3}(ix|iv|v?i{0,3})$")


def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def clean_name(name) -> str | None:
    """Nom d'affichage : 'Far Cry® New Dawn ' -> 'Far Cry New Dawn'."""
    if is_missing(name):
        return None
    # Symboles retirés AVANT NFKC, qui transformerait "™" en lettres "TM"
    name = unicodedata.normalize("NFKC", TRADEMARKS_RE.sub("", str(name)))
    name = SPACES_RE.sub(" ", name).strip()
    return name or None


def name_key(name) -> str | None:
    """Clé de rapprochement entre sources : minuscules, sans accents ni ponctuation.

    'The Witcher® 3: Wild Hunt' et 'the witcher 3 - wild hunt' -> 'the witcher 3 wild hunt'
    """
    name = clean_name(name)
    if name is None:
        return None
    # Apostrophes supprimées (et non remplacées par un espace) : "Assassin’s" = "Assassin's"
    name = APOSTROPHES_RE.sub("", name)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().replace("&", " and ")
    name = NON_ALNUM_RE.sub(" ", name)
    return SPACES_RE.sub(" ", name).strip() or None


def sequel_markers(key: str) -> list[str]:
    """Numéros d'épisode d'une clé de nom : chiffres arabes et romains.

    'final fantasy x' -> ['x'] ; 'dark souls iii' -> ['iii'] ; 'call of duty 2' -> ['2']
    Deux noms très proches mais de numéros différents sont deux jeux différents.
    """
    return [w for w in key.split() if w.isdigit() or ROMAN_RE.match(w)]


def compact_key(key: str | None) -> str | None:
    """Clé sans espaces : 'puyo puyotetris' = 'puyo puyo tetris'."""
    return key.replace(" ", "") if key else None


# --- Dates -----------------------------------------------------------------
DATE_FORMATS = (
    "%d %b, %Y",   # Steam Store       : "29 Sep, 2015"
    "%b %d, %Y",   # dataset partenaire: "Aug 1, 2023"
    "%d %B, %Y",   # mois complet      : "29 September, 2015"
    "%b %Y",       # mois seul         : "Sep 2015" -> 1er du mois
    "%Y-%m-%d",    # ISO
)


def parse_date(value) -> date | None:
    """Convertit les formats de date rencontrés ; None si inexploitable ('', 'Coming soon')."""
    if is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def year_or_none(value) -> int | None:
    """Année de vgsales : '2006' -> 2006, 'N/A' -> None, hors 1970-2030 -> None."""
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    return year if 1970 <= year <= 2030 else None


# --- Prix ------------------------------------------------------------------
EURO_PRICE_RE = re.compile(r"^(\d+(?:\.\d{3})*),(\d{2}|--)\s*€$")


def parse_price_text(text) -> float | None:
    """Prix scrapé -> euros.

    '12,99€' -> 12.99 ; '9,--€' -> 9.0 ; 'Free To Play' -> 0.0 ;
    '7,99€ / month' (abonnement, non comparable) -> None ; 'Install Now' -> None
    """
    if is_missing(text):
        return None
    text = str(text).strip()
    match = EURO_PRICE_RE.match(text)
    if match:
        euros = int(match.group(1).replace(".", ""))
        cents = 0 if match.group(2) == "--" else int(match.group(2))
        return euros + cents / 100
    if "free" in text.lower() and not re.search(r"\d", text) and "trial" not in text.lower():
        return 0.0
    return None


def cents_to_euros(cents) -> float | None:
    if is_missing(cents):
        return None
    return round(int(cents) / 100, 2)


# --- Fourchettes de propriétaires -------------------------------------------
OWNERS_RE = re.compile(r"^\s*([\d,]+)\s*(?:\.\.|-)\s*([\d,]+)\s*$")


def parse_owners(value) -> tuple[int | None, int | None]:
    """'1,000,000 .. 2,000,000' (SteamSpy) ou '1000000 - 2000000' -> (1000000, 2000000)."""
    if is_missing(value):
        return None, None
    match = OWNERS_RE.match(str(value))
    if not match:
        return None, None
    low, high = (int(g.replace(",", "")) for g in match.groups())
    return (low, high) if low <= high else (None, None)


# --- Bornes de validité ----------------------------------------------------
def bounded(value, low: float, high: float):
    """Valeur hors bornes -> None (ex. note Metacritic 0 = 'non notée')."""
    if is_missing(value):
        return None
    return value if low <= value <= high else None


# --- Langues ---------------------------------------------------------------
STEAM_LANGUAGES = {
    "english": "en", "french": "fr", "german": "de", "spanish": "es", "latam": "es-419",
    "italian": "it", "portuguese": "pt", "brazilian": "pt-BR", "russian": "ru",
    "ukrainian": "uk", "polish": "pl", "czech": "cs", "hungarian": "hu",
    "romanian": "ro", "bulgarian": "bg", "greek": "el", "turkish": "tr",
    "dutch": "nl", "swedish": "sv", "danish": "da", "norwegian": "no",
    "finnish": "fi", "schinese": "zh-Hans", "tchinese": "zh-Hant",
    "japanese": "ja", "koreana": "ko", "thai": "th", "vietnamese": "vi",
    "indonesian": "id", "arabic": "ar",
}


def language_code(steam_language) -> str | None:
    if is_missing(steam_language):
        return None
    return STEAM_LANGUAGES.get(str(steam_language).strip().lower())


# --- Données personnelles dans le texte libre (RGPD) ------------------------
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def mask_personal_data(text: str) -> str:
    """Masque e-mails et liens (profils Steam, réseaux sociaux) dans un avis.

    'contact me: bob@mail.com' -> 'contact me: [email]'
    """
    return URL_RE.sub("[lien]", EMAIL_RE.sub("[email]", text))


# --- Plateformes vgsales ----------------------------------------------------
PLATFORMS = {
    "2600": "Atari 2600", "3DO": "3DO", "3DS": "Nintendo 3DS", "DC": "Dreamcast",
    "DS": "Nintendo DS", "GB": "Game Boy", "GBA": "Game Boy Advance",
    "GC": "GameCube", "GEN": "Mega Drive", "GG": "Game Gear", "N64": "Nintendo 64",
    "NES": "NES", "NG": "Neo Geo", "PC": "PC", "PCFX": "PC-FX", "PS": "PlayStation",
    "PS2": "PlayStation 2", "PS3": "PlayStation 3", "PS4": "PlayStation 4",
    "PSP": "PSP", "PSV": "PS Vita", "SAT": "Saturn", "SCD": "Sega CD",
    "SNES": "Super Nintendo", "TG16": "TurboGrafx-16", "WS": "WonderSwan",
    "Wii": "Wii", "WiiU": "Wii U", "X360": "Xbox 360", "XB": "Xbox", "XOne": "Xbox One",
}


def platform_name(code) -> str | None:
    if is_missing(code):
        return None
    return PLATFORMS.get(str(code), str(code))


def millions_to_units(value) -> int | None:
    """Ventes vgsales en millions (41.49) -> unités (41 490 000)."""
    if is_missing(value):
        return None
    return int(round(float(value) * 1_000_000))
