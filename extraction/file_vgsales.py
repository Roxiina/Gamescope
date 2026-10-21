"""Source 6 - Fichier de données : ventes de jeux vidéo (Kaggle, VGChartz).

Fichier CSV : ventes physiques en millions d'unités par région et plateforme,
jusqu'en 2016. Contraintes : données arrêtées en 2016, années "N/A",
éditeurs "Unknown", un même jeu présent une fois par plateforme.
"""
import logging

import pandas as pd

from extraction import config

log = logging.getLogger("extraction.file_vgsales")

SOURCE = config.EXTERNAL_DIR / "vgsales.csv"
OUTPUT = config.RAW_DIR / "vgsales.parquet"

DTYPES = {
    "Rank": "Int64", "Name": "string", "Platform": "string", "Genre": "string",
    "Publisher": "string", "NA_Sales": "float64", "EU_Sales": "float64",
    "JP_Sales": "float64", "Other_Sales": "float64", "Global_Sales": "float64",
}


def extract() -> pd.DataFrame:
    # Year lu en texte : il contient des "N/A", converti à l'étape de nettoyage
    df = pd.read_csv(SOURCE, dtype={**DTYPES, "Year": "string"}, na_values=[], keep_default_na=False)
    lines = len(df)

    # Filtrage : lignes sans nom ou sans ventes mondiales inexploitables
    df = df[df["Name"].str.strip().ne("") & df["Global_Sales"].notna()]
    df = df.rename(columns=str.lower).drop(columns=["rank"])

    df.to_parquet(OUTPUT, index=False)
    log.info("Fichier vgsales : %d/%d lignes conservées, sauvegardées dans %s",
             len(df), lines, OUTPUT.name)
    return df
