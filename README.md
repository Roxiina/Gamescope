# GameScope

Plateforme de collecte, stockage et mise à disposition de données réelles sur
les jeux vidéo Steam. Projet de certification Simplon, bloc E1 (RNCP 37827).

## Sources de données (toutes réelles)

| Type | Source | Module | Sortie |
|---|---|---|---|
| API REST | SteamSpy (`request=all`) | `extraction/steamspy.py` | `data/raw/steamspy_games.json` |
| API REST | Steam Store (`appdetails`, `appreviews`) | `extraction/steam_store_api.py` | `data/raw/steam_appdetails.jsonl`, `steam_reviews_api.jsonl` |
| Web scraping | Pages du Steam Store | `extraction/steam_scraper.py` | `data/raw/steam_store_pages.jsonl` |
| Fichier | Kaggle *Video Game Sales* (CSV) | `extraction/file_vgsales.py` | `data/raw/vgsales.parquet` |
| Base de données | Kaggle *Steam Games* chargé dans PostgreSQL (base « partenaire ») | `extraction/db_partner.py` | `data/raw/partner_games.parquet` |
| Big data | Kaggle *Steam Reviews 2021* (21 M avis) en data lake Parquet, interrogé via Spark Thrift Server | `extraction/bigdata_reviews.py` | `data/raw/bigdata_reviews_*.parquet` |

Les requêtes SQL sont versionnées et documentées dans [`sql/`](sql/README.md).

> **Note :** aucune base Steam publique n'est accessible en connexion directe. La
> base « partenaire » et le data lake sont donc **mis en place** à partir de
> jeux de données réels (dossier `sources/`), pour simuler les systèmes d'un
> partenaire. Le code d'`extraction/` les traite comme des systèmes externes :
> compte en lecture seule, connexion réseau, requêtes SQL.

## Installation

Prérequis : Python 3.12, Git, Docker Desktop (au moins 4 Go de RAM disponibles).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # puis renseigner les secrets (voir commentaires)
```

### Données Kaggle (compte gratuit requis)

À télécharger dans `data/external/` :

| Fichier | Dataset |
|---|---|
| `vgsales.csv` | [Video Game Sales](https://www.kaggle.com/datasets/gregorut/videogamesales) |
| `games.csv` | [Steam Games Dataset](https://www.kaggle.com/datasets/fronkongames/steam-games-dataset) |
| `steam_reviews.csv` | [Steam Reviews 2021](https://www.kaggle.com/datasets/najzeko/steam-reviews-2021) |

### Mise en place des systèmes sources (une seule fois)

```bash
docker compose up -d --wait partner-db       # PostgreSQL, port 5435
python -m sources.partner_db.seed_partner_db  # charge games.csv (~15 min)
python -m sources.bigdata.ingest_reviews      # CSV 8 Go -> Parquet (~5 min)
docker compose up -d --wait spark            # Spark Thrift Server, port 10000
```

## Lancer l'extraction

```bash
python -m extraction.main --limit 20          # test rapide (~1 min)
python -m extraction.main                     # collecte complète, 2000 jeux (~2 h)
python -m extraction.main --sources scraping  # une seule source
# sources : api, scraping, file, database, bigdata
```

La collecte est **reprenable** : si elle est interrompue (Ctrl+C, coupure réseau),
relancer la même commande reprend là où elle s'était arrêtée. Les journaux sont
écrits dans `logs/extraction.log`.

## Nettoyage et agrégation (C3)

```bash
python -m cleaning.aggregate   # data/raw/ -> data/clean/ (games, reviews, sales)
python -m pytest tests -q
```

Détails des règles : [`cleaning/README.md`](cleaning/README.md).

## Déroulé du script

1. **Initialisation** : lecture du `.env`, création des dossiers, journalisation
2. **SteamSpy** : liste des N jeux les plus possédés (1 appel par page de 1000 jeux)
3. **Steam Store API** : fiche détaillée et 20 avis récents par jeu
4. **Scraping** : tags joueurs, avis des 30 derniers jours, langues, prix affiché
5. **Fichier, base de données, big data** : lecture et filtrage du CSV, requête
   SQL sur PostgreSQL (compte en lecture seule), requêtes Spark SQL sur le data lake
6. **Gestion des erreurs** : relances automatiques (429/5xx, backoff exponentiel),
   une erreur sur un jeu est journalisée sans arrêter la collecte
7. **Sauvegarde** : écriture ligne par ligne (JSONL), sans perte en cas d'arrêt

## Contraintes des sources

- **Limites de débit** : SteamSpy 1 req/s (1 req/min pour `request=all`),
  Steam Store environ 200 req / 5 min, donc 1,8 s entre deux appels
- **robots.txt** du Steam Store : `/app/` autorisé
- **Vérification d'âge** : cookies `birthtime` / `wants_mature_content`
- **games.csv** : en-tête défectueux (`DiscountDLC count` = deux colonnes
  fusionnées, 39 noms pour 40 valeurs), corrigé à la lecture. Le dataset contient
  aussi des jeux sans nom, conservés tels quels dans la source.
- **steam_reviews.csv** (8 Go) : trop volumineux pour la mémoire, il est lu en
  flux par blocs de 64 Mo. Les avis contiennent des retours à la ligne entre guillemets.
- **Spark sous Windows** : Spark ne peut pas lire de fichiers en local sans
  `winutils.exe`. Il tourne donc dans Docker, ce qui rend aussi l'installation reproductible.
- **RGPD** : l'identifiant Steam des auteurs d'avis est pseudonymisé (SHA-256 salé)
  dès la collecte (API) et dès l'ingestion dans le data lake (big data). Le pseudo,
  l'avatar et l'URL du profil ne sont pas collectés.

### Bridage de Steam

Steam signale un dépassement de débit par des **erreurs 502** (et non 429).
Dans ce cas, `throttled_get` (`extraction/utils.py`) fait des pauses de 1, 2
puis 4 minutes et réessaie la même requête. Un jeu n'est abandonné qu'après
4 échecs. Comme il n'est alors pas enregistré, il sera retenté à la relance suivante.
