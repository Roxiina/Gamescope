"""Agrégation et nettoyage des 7 extractions brutes en un jeu de données final unique.

Usage :
    python -m cleaning.aggregate

Entrée  : data/raw/ (produit par `python -m extraction.main`)
Sortie  : data/clean/games.parquet    1 ligne par jeu (table centrale)
          data/clean/reviews.parquet  avis, reliés à games par app_id
          data/clean/sales.parquet    ventes par plateforme, reliées par app_id
          data/clean/cleaning_report.json  bilan chiffré de chaque règle

Enchaînement : chargement -> jeux -> avis -> ventes -> contrôles qualité -> sauvegarde.
Chaque suppression est comptée par règle, avec des exemples, dans le rapport.
"""
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from cleaning import normalize as n
from extraction import config
from extraction.utils import setup_logging

log = logging.getLogger("cleaning")

CLEAN_DIR = config.DATA_DIR / "clean"
RAW = config.RAW_DIR
FUZZY_THRESHOLD = 97      # score minimal (0-100) pour un rapprochement approché de noms
MAX_VOTES = 1_000_000     # au-delà : valeur corrompue (le record réel est ~17 000)
MAX_YEAR_GAP = 10         # écart max entre sortie console (vgsales) et sortie Steam
SALES_TOLERANCE = 0.02    # écart toléré (millions) entre somme des régions et total mondial


class CleaningReport:
    """Trace chaque règle : nombre de lignes supprimées / corrigées et exemples."""

    def __init__(self):
        self.steps = defaultdict(list)

    def drop(self, table: str, rule: str, rows: pd.DataFrame, label: str) -> None:
        self.steps[table].append({"règle": rule, "action": "suppression", "lignes": len(rows),
                                  "exemples": rows[label].astype(str).head(5).tolist()})
        log.info("[%s] %s : %d lignes supprimées", table, rule, len(rows))

    def fix(self, table: str, rule: str, count: int) -> None:
        self.steps[table].append({"règle": rule, "action": "correction", "lignes": int(count)})
        log.info("[%s] %s : %d valeurs corrigées", table, rule, count)

    def info(self, table: str, key: str, value) -> None:
        self.steps[table].append({"règle": key, "action": "info", "valeur": value})


def drop_where(df: pd.DataFrame, mask: pd.Series, report: CleaningReport,
               table: str, rule: str, label: str) -> pd.DataFrame:
    report.drop(table, rule, df[mask], label)
    return df[~mask]


# ---------------------------------------------------------------------------
# Chargement
# ---------------------------------------------------------------------------
def load_raw() -> dict[str, pd.DataFrame]:
    reviews = pd.read_json(RAW / "steam_reviews_api.jsonl", lines=True,
                           dtype={"review_id": "Int64"}, convert_dates=False)
    if "marker" in reviews:  # lignes techniques de reprise de collecte
        reviews = reviews[reviews["marker"].isna()].drop(columns="marker")
    raw = {
        "steamspy": pd.DataFrame(json.loads((RAW / "steamspy_games.json").read_text(encoding="utf-8"))),
        "details": pd.read_json(RAW / "steam_appdetails.jsonl", lines=True, convert_dates=False),
        "pages": pd.read_json(RAW / "steam_store_pages.jsonl", lines=True, convert_dates=False),
        "api_reviews": reviews,
        "partner": pd.read_parquet(RAW / "partner_games.parquet"),
        "vgsales": pd.read_parquet(RAW / "vgsales.parquet"),
        "bd_stats": pd.read_parquet(RAW / "bigdata_reviews_stats.parquet"),
        "bd_sample": pd.read_parquet(RAW / "bigdata_reviews_sample.parquet"),
    }
    for name, df in raw.items():
        log.info("Chargé %-12s : %d lignes", name, len(df))
    return raw


def file_date(path) -> pd.Timestamp:
    """Date de collecte d'une source = date du fichier brut (base de la durée de conservation RGPD)."""
    return pd.Timestamp(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))


def as_list(value) -> list[str]:
    """Liste propre et dédoublonnée, quel que soit le format source (liste, tableau, texte)."""
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    cleaned = (n.clean_name(v) for v in value)
    return list(dict.fromkeys(v for v in cleaned if v))


def first_valid(*values):
    """Première valeur renseignée, dans l'ordre de priorité des sources."""
    for value in values:
        if isinstance(value, (list, np.ndarray)):
            if len(value):
                return value
        elif not n.is_missing(value):
            return value
    return None


# ---------------------------------------------------------------------------
# Jeux
# ---------------------------------------------------------------------------
def build_games(raw: dict, report: CleaningReport) -> pd.DataFrame:
    t = "games"
    # Un enregistrement par app_id et par source (dernier extrait = plus récent)
    for name, key in (("steamspy", "appid"), ("details", "appid"), ("pages", "appid"),
                      ("partner", "app_id"), ("bd_stats", "app_id")):
        before = len(raw[name])
        raw[name] = raw[name].drop_duplicates(key, keep="last")
        if before != len(raw[name]):
            report.fix(t, f"doublons d'app_id dans la source {name}", before - len(raw[name]))

    df = (raw["steamspy"].add_prefix("spy_").rename(columns={"spy_appid": "app_id"})
          .merge(raw["details"].add_prefix("api_").rename(columns={"api_appid": "app_id"}), on="app_id", how="left")
          .merge(raw["pages"].add_prefix("web_").rename(columns={"web_appid": "app_id"}), on="app_id", how="left")
          .merge(raw["partner"].add_prefix("db_").rename(columns={"db_app_id": "app_id"}), on="app_id", how="left")
          .merge(raw["bd_stats"].add_prefix("bd_").rename(columns={"bd_app_id": "app_id"}), on="app_id", how="left"))
    report.info(t, "jeux de référence (SteamSpy)", len(df))

    # --- Entrées corrompues ou hors périmètre ---------------------------------
    api_ko = df["api_unavailable"].eq(True) if "api_unavailable" in df else False
    web_ko = df["web_unavailable"].eq(True) if "web_unavailable" in df else False
    df = drop_where(df, api_ko & web_ko, report, t,
                    "retiré de la vente (fiche API et page Steam indisponibles)", "spy_name")
    df = drop_where(df, df["api_type"].notna() & df["api_type"].ne("game"), report, t,
                    "hors périmètre : démo ou contenu qui n'est pas un jeu", "api_name")

    df["name"] = [first_valid(n.clean_name(a), n.clean_name(s), n.clean_name(d))
                  for a, s, d in zip(df["api_name"], df["spy_name"], df["db_name"])]
    df = drop_where(df, df["name"].isna(), report, t, "nom absent dans toutes les sources", "app_id")

    dates = [(n.parse_date(a), n.parse_date(w), n.parse_date(d))
             for a, w, d in zip(df["api_release_date"], df["web_release_date_text"], df["db_release_date"])]
    df["release_date"] = [first_valid(*d) for d in dates]
    report.fix(t, "date de sortie reprise d'une source secondaire (API vide)",
               sum(d[0] is None and (d[1] or d[2]) is not None for d in dates))
    df = drop_where(df, df["release_date"].isna(), report, t,
                    "date de sortie absente ou illisible dans toutes les sources", "name")

    # --- Homogénéisation -----------------------------------------------------
    api_price = [0.0 if free is True else (n.cents_to_euros(c) if cur == "EUR" else None)
                 for free, c, cur in zip(df["api_is_free"], df["api_price_final_cents"], df["api_currency"])]
    web_price = df["web_price_text"].map(n.parse_price_text)
    df["price_eur"] = [first_valid(a, w) for a, w in zip(api_price, web_price)]
    report.fix(t, "prix repris du texte scrapé ('12,99€', 'Free To Play' -> euros)",
               sum(a is None and not n.is_missing(w) for a, w in zip(api_price, web_price)))
    df["price_initial_eur"] = df["api_price_initial_cents"].map(n.cents_to_euros)
    df["discount_pct"] = np.where(
        df["price_initial_eur"].gt(0),
        ((1 - df["price_eur"].astype(float) / df["price_initial_eur"]) * 100).round(),
        np.nan)
    df["is_free"] = df["price_eur"].eq(0.0)

    owners = [first_valid(n.parse_owners(s)[0] and n.parse_owners(s), n.parse_owners(d)[0] and n.parse_owners(d))
              for s, d in zip(df["spy_owners"], df["db_estimated_owners"])]
    df["owners_min"] = [o[0] if o else None for o in owners]
    df["owners_max"] = [o[1] if o else None for o in owners]

    meta_raw = [first_valid(a, d) for a, d in zip(df["api_metacritic_score"], df["db_metacritic_score"])]
    meta = [n.bounded(m, 1, 100) for m in meta_raw]
    report.fix(t, "note Metacritic 0 ou hors 1-100 -> valeur manquante",
               sum(m is not None and v is None for m, v in zip(meta_raw, meta)))
    df["metacritic_score"] = meta

    df["required_age"] = df["api_required_age"].map(lambda v: n.bounded(v, 0, 21)).astype("Int64")
    df["developers"] = [as_list(first_valid(a, s)) for a, s in zip(df["api_developers"], df["spy_developer"])]
    df["publishers"] = [as_list(first_valid(a, s)) for a, s in zip(df["api_publishers"], df["spy_publisher"])]
    df["genres"] = [as_list(first_valid(a, d)) for a, d in zip(df["api_genres"], df["db_genres"])]
    df["categories"] = df["api_categories"].map(as_list)
    df["tags"] = [as_list(first_valid(w, d)) for w, d in zip(df["web_tags"], df["db_top_tags"])]
    df["platforms"] = [as_list(first_valid(a, [p for p, ok in (("windows", w), ("mac", m), ("linux", l)) if ok is True]))
                       for a, w, m, l in zip(df["api_platforms"], df["db_windows"], df["db_mac"], df["db_linux"])]

    df["positive_reviews"] = df["spy_positive"].astype("Int64")
    df["negative_reviews"] = df["spy_negative"].astype("Int64")
    total = df["positive_reviews"] + df["negative_reviews"]
    df["pct_positive"] = (df["positive_reviews"] / total.replace(0, pd.NA) * 100).astype(float).round(2)
    df["recent_review_pct"] = df["web_recent_review_pct"].map(lambda v: n.bounded(v, 0, 100))
    df["recent_review_count"] = df["web_recent_review_count"].astype("Int64")
    df["recent_review_desc"] = df["web_recent_review_desc"]
    df["languages_count"] = df["web_languages_count"].astype("Int64")
    df["avg_playtime_min"] = [first_valid(s or None, d or None) for s, d in zip(df["spy_average_forever"], df["db_avg_playtime_min"])]
    df["median_playtime_min"] = [first_valid(s or None, d or None) for s, d in zip(df["spy_median_forever"], df["db_median_playtime_min"])]
    df["peak_ccu"] = df["spy_ccu"].astype("Int64")
    df["dlc_count"] = df["api_dlc_count"].astype("Int64")
    df["achievements"] = df["db_achievements"].astype("Int64")
    df["recommendations"] = df["api_recommendations"].astype("Int64")

    for col in ("nb_reviews", "pct_recommended", "median_playtime_at_review_min", "nb_languages"):
        df[f"reviews2021_{col}"] = df[f"bd_{col}"]

    df["sources"] = [
        [s for s, ok in (("steamspy", True), ("steam_api", api), ("scraping", web),
                         ("partner_db", db), ("bigdata", bd)) if ok]
        for api, web, db, bd in zip(df["api_name"].notna(), df["web_tags"].notna(),
                                    df["db_name"].notna(), df["bd_nb_reviews"].notna())
    ]
    df["name_key"] = df["name"].map(n.name_key)

    columns = ["app_id", "name", "name_key", "release_date", "price_eur", "price_initial_eur",
               "discount_pct", "is_free", "required_age", "owners_min", "owners_max", "metacritic_score",
               "positive_reviews", "negative_reviews", "pct_positive", "recent_review_pct",
               "recent_review_count", "recent_review_desc", "avg_playtime_min", "median_playtime_min",
               "peak_ccu", "dlc_count", "achievements", "recommendations", "languages_count",
               "developers", "publishers", "genres", "categories", "tags", "platforms",
               "reviews2021_nb_reviews", "reviews2021_pct_recommended",
               "reviews2021_median_playtime_at_review_min", "reviews2021_nb_languages", "sources"]
    games = df[columns].reset_index(drop=True)
    for col in ("owners_min", "owners_max", "metacritic_score", "avg_playtime_min", "median_playtime_min",
                "reviews2021_nb_reviews", "reviews2021_nb_languages"):
        games[col] = pd.to_numeric(games[col]).astype("Int64")
    report.info(t, "jeux dans le jeu de données final", len(games))
    return games


# ---------------------------------------------------------------------------
# Avis
# ---------------------------------------------------------------------------
def build_reviews(raw: dict, games: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    t = "reviews"
    api = raw["api_reviews"].rename(columns={
        "appid": "app_id", "voted_up": "recommended", "votes_up": "votes_helpful"})
    api["source"] = "steam_api"
    api["collected_at"] = file_date(RAW / "steam_reviews_api.jsonl")
    bd = raw["bd_sample"].rename(columns={
        "review": "review_text", "author_playtime_at_review": "author_playtime_min"})
    bd["language"] = "english"  # échantillon filtré sur l'anglais par la requête Spark
    bd["source"] = "bigdata_2021"
    # Date de l'extraction Spark (et non du CSV Kaggle, absent d'un clone du dépôt)
    bd["collected_at"] = file_date(RAW / "bigdata_reviews_sample.parquet")
    cols = ["review_id", "app_id", "author_hash", "language", "review_text", "recommended",
            "votes_helpful", "author_playtime_min", "timestamp_created", "source", "collected_at"]
    df = pd.concat([api[cols], bd[cols]], ignore_index=True)  # API en premier : prioritaire
    report.info(t, "avis bruts (API + big data)", len(df))

    df["review_text"] = (df["review_text"].fillna("").str.replace("\r\n", "\n")
                         .str.replace(r"[ \t]+", " ", regex=True).str.strip())
    df = drop_where(df, df["review_text"].eq(""), report, t, "texte d'avis vide", "review_id")
    df = drop_where(df, df["review_id"].isna(), report, t, "identifiant d'avis absent", "app_id")
    df = drop_where(df, df.duplicated("review_id", keep="first"), report, t,
                    "doublon d'avis (même review_id, version API conservée)", "review_id")
    df = drop_where(df, ~df["app_id"].isin(games["app_id"]), report, t,
                    "hors périmètre : avis d'un jeu absent du jeu de données final", "app_id")
    now = pd.Timestamp.now(tz="UTC").timestamp()
    bad_ts = ~df["timestamp_created"].between(1_041_379_200, now)  # Steam lancé en 2003
    df = drop_where(df, bad_ts, report, t, "date de publication incohérente", "review_id")
    df = drop_where(df, df["author_hash"].isna(), report, t, "auteur non identifiable", "review_id")

    masked = df["review_text"].map(n.mask_personal_data)
    report.fix(t, "RGPD : e-mails et liens masqués dans le texte des avis",
               int((masked != df["review_text"]).sum()))
    df["review_text"] = masked
    df["created_at"] = pd.to_datetime(df["timestamp_created"], unit="s", utc=True)
    langs = df["language"].map(n.language_code)
    report.fix(t, "langue Steam ('schinese', 'brazilian'...) -> code BCP 47", int(langs.notna().sum()))
    df["language"] = langs
    df["author_playtime_min"] = df["author_playtime_min"].where(df["author_playtime_min"] >= 0).round().astype("Int64")
    aberrant = df["votes_helpful"] > MAX_VOTES
    report.fix(t, f"votes 'utile' aberrants (> {MAX_VOTES:,}) -> valeur manquante", int(aberrant.sum()))
    df["votes_helpful"] = df["votes_helpful"].mask(aberrant).astype("Int64")
    df["review_id"] = df["review_id"].astype("int64")
    df["recommended"] = df["recommended"].astype(bool)
    reviews = df.drop(columns="timestamp_created").reset_index(drop=True)
    report.info(t, "avis dans le jeu de données final", len(reviews))
    return reviews


# ---------------------------------------------------------------------------
# Ventes
# ---------------------------------------------------------------------------
def match_games(df: pd.DataFrame, games: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    """Associe chaque ligne vgsales à un app_id Steam, du plus sûr au moins sûr.

    1. clé de nom identique          ('Far Cry® 4' = 'Far Cry 4')
    2. clé compacte (sans espaces)    ('Puyo PuyoTetris' = 'Puyo Puyo Tetris')
    3. similarité >= FUZZY_THRESHOLD ET mêmes numéros d'épisode
       ('Final Fantasy X' ≠ 'FINAL FANTASY IX' malgré 96 % de similarité)
    Les clés portées par plusieurs jeux Steam sont ambiguës et ignorées.
    """
    t = "sales"
    by_key, by_compact = defaultdict(set), defaultdict(set)
    for app_id, key in zip(games["app_id"], games["name_key"]):
        by_key[key].add(app_id)
        by_compact[n.compact_key(key)].add(app_id)
    unique_key = {k: next(iter(v)) for k, v in by_key.items() if len(v) == 1}
    unique_compact = {k: next(iter(v)) for k, v in by_compact.items() if len(v) == 1}

    df["name_key"] = df["name"].map(n.name_key)
    df["app_id"] = df["name_key"].map(unique_key)
    df["match_method"] = np.where(df["app_id"].notna(), "exact", None)

    todo = df["app_id"].isna()
    compact = df.loc[todo, "name_key"].map(n.compact_key).map(unique_compact)
    df.loc[compact.dropna().index, ["app_id", "match_method"]] = list(zip(compact.dropna(), ["compact"] * compact.notna().sum()))

    choices = list(unique_key)
    for idx in df.index[df["app_id"].isna()]:
        key = df.at[idx, "name_key"]
        best = process.extractOne(key, choices, scorer=fuzz.ratio, score_cutoff=FUZZY_THRESHOLD)
        if best and n.sequel_markers(key) == n.sequel_markers(best[0]):
            df.at[idx, "app_id"] = unique_key[best[0]]
            df.at[idx, "match_method"] = "fuzzy"

    report.info(t, "lignes hors périmètre (jeu absent des jeux Steam suivis), écartées",
                int(df["app_id"].isna().sum()))
    df = df[df["app_id"].notna()].copy()
    # Homonymes : 'Resident Evil 2' (PS1, 1998) n'est pas le remake Steam de 2019
    steam_year = df["app_id"].map(dict(zip(games["app_id"], games["release_date"].map(lambda d: d.year))))
    remake = (steam_year - df["year"]).abs() > MAX_YEAR_GAP
    df = drop_where(df, remake.fillna(False), report, t,
                    f"rapprochement ambigu : plus de {MAX_YEAR_GAP} ans entre sortie console et "
                    "sortie Steam (remake homonyme possible)", "name")
    report.info(t, "lignes rapprochées (exact / compact / approché)",
                " / ".join(str(int((df["match_method"] == m).sum())) for m in ("exact", "compact", "fuzzy")))
    return df


def build_sales(raw: dict, games: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    t = "sales"
    df = raw["vgsales"].copy()
    report.info(t, "lignes de ventes brutes", len(df))

    df["year"] = df["year"].map(n.year_or_none).astype("Int64")
    df = drop_where(df, df.duplicated(["name", "platform", "year"], keep="first"), report, t,
                    "doublon exact (même jeu, plateforme et année)", "name")
    dated = set(zip(df.loc[df["year"].notna(), "name"], df.loc[df["year"].notna(), "platform"]))
    partial = df["year"].isna() & pd.Series([(a, b) in dated for a, b in zip(df["name"], df["platform"])], index=df.index)
    df = drop_where(df, partial, report, t,
                    "doublon partiel sans année d'une ligne datée existante", "name")
    regions = df[["na_sales", "eu_sales", "jp_sales", "other_sales"]].sum(axis=1)
    df = drop_where(df, (regions - df["global_sales"]).abs() > SALES_TOLERANCE, report, t,
                    "incohérence : somme des régions différente du total mondial", "name")

    # --- Rapprochement des noms avec les jeux Steam ----------------------------
    df = match_games(df, games, report)

    df["platform"] = df["platform"].map(n.platform_name)
    df["publisher"] = df["publisher"].where(~df["publisher"].isin(["Unknown", "N/A", ""]))
    for region in ("na", "eu", "jp", "other", "global"):
        df[f"sales_{region}_units"] = df[f"{region}_sales"].map(n.millions_to_units).astype("Int64")
    report.fix(t, "ventes converties de millions en unités", len(df))

    sales = df.rename(columns={"name": "vgsales_name", "year": "release_year"})[
        ["app_id", "vgsales_name", "platform", "release_year", "genre", "publisher",
         "sales_na_units", "sales_eu_units", "sales_jp_units", "sales_other_units",
         "sales_global_units", "match_method"]].reset_index(drop=True)
    sales["app_id"] = sales["app_id"].astype("int64")
    return sales


# ---------------------------------------------------------------------------
# Contrôles qualité finaux (le script échoue si une règle n'est pas respectée)
# ---------------------------------------------------------------------------
def validate(games: pd.DataFrame, reviews: pd.DataFrame, sales: pd.DataFrame) -> None:
    checks = {
        "app_id unique": games["app_id"].is_unique,
        "nom toujours renseigné": games["name"].notna().all(),
        "date toujours renseignée": games["release_date"].notna().all(),
        "prix positifs": (games["price_eur"].dropna() >= 0).all(),
        "pourcentages entre 0 et 100": games["pct_positive"].dropna().between(0, 100).all(),
        "review_id unique": reviews["review_id"].is_unique,
        "avis -> jeu existant": reviews["app_id"].isin(games["app_id"]).all(),
        "aucun avis vide": reviews["review_text"].str.len().gt(0).all(),
        "ventes -> jeu existant": sales["app_id"].isin(games["app_id"]).all(),
        "ventes positives": (sales["sales_global_units"] >= 0).all(),
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        log.info("Contrôle %-30s %s", name, "OK" if ok else "ÉCHEC")
    if failed:
        raise ValueError(f"Contrôles qualité en échec : {failed}")


def main() -> int:
    setup_logging("cleaning")
    report = CleaningReport()
    try:
        raw = load_raw()
        games = build_games(raw, report)
        reviews = build_reviews(raw, games, report)
        sales = build_sales(raw, games, report)
        validate(games, reviews, sales)
    except FileNotFoundError as exc:
        log.error("Fichier brut manquant (lancer d'abord l'extraction) : %s", exc)
        return 1
    except Exception:
        log.exception("Échec de l'agrégation")
        return 1

    CLEAN_DIR.mkdir(exist_ok=True)
    games.to_parquet(CLEAN_DIR / "games.parquet", index=False)
    reviews.to_parquet(CLEAN_DIR / "reviews.parquet", index=False)
    sales.to_parquet(CLEAN_DIR / "sales.parquet", index=False)
    (CLEAN_DIR / "cleaning_report.json").write_text(
        json.dumps(report.steps, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log.info("Jeu de données final : %d jeux, %d avis, %d lignes de ventes -> %s",
             len(games), len(reviews), len(sales), CLEAN_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
