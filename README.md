# GameScope

Plateforme de collecte, stockage et mise à disposition de données réelles sur
les jeux vidéo Steam. Projet de certification Simplon, bloc E1 (RNCP 37827).

**Pourquoi ce projet ?** C'est un projet personnel : je souhaite développer un jour
mon propre jeu sur Steam. GameScope rassemble les données qui permettent de
comprendre ce qui fait le succès d'un jeu (genres et tags porteurs, prix, accueil des
joueurs et de la presse, ventes) avant de me lancer.

```
 Sources (6)                 Extraction (C1, C2)    Nettoyage (C3)        Stockage (C4)       Mise à disposition (C5)
 ─────────────               ──────────────────     ──────────────        ─────────────       ───────────────────────
 SteamSpy API      ─┐
 Steam Store API   ─┤
 Pages Steam       ─┤        extraction/            cleaning/             PostgreSQL          API REST
 vgsales.csv       ─┼──────► data/raw/ ───────────► data/clean/ ────────► gamescope ────────► /api/v1 (14 routes)
 PostgreSQL partenaire ─┤                           games / reviews /     21 tables       FastAPI + JWT
 Spark (data lake) ─┘                               sales
```

| Étape | Dossier | Documentation |
|---|---|---|
| Extraction (C1) | `extraction/` | [ci-dessous](#1-extraction-c1) |
| Requêtes SQL (C2) | `sql/` | [`sql/README.md`](sql/README.md) |
| Nettoyage et agrégation (C3) | `cleaning/` | [`cleaning/README.md`](cleaning/README.md) |
| Base de données (C4) | `database/` | [ci-dessous](#4-base-de-données-c4), [`docs/merise.md`](docs/merise.md) |
| RGPD (C4) | `database/rgpd_cleanup.py` | [`docs/rgpd/`](docs/rgpd/registre_traitements.md) |
| API REST (C5) | `api/` | [`api/README.md`](api/README.md), Swagger UI : http://localhost:8000/docs |

## Installation

Prérequis : Python 3.12, Git, Docker Desktop (au moins 4 Go de RAM disponibles).

```bash
git clone https://github.com/Roxiina/gamescope.git && cd gamescope
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
python scripts/init_env.py      # crée .env et génère tous les secrets
```

`scripts/init_env.py` copie `.env.example` en `.env` et génère aléatoirement les
8 secrets (mots de passe des bases et de la supervision, sel de pseudonymisation,
clé des jetons JWT).
Il n'écrase jamais un `.env` existant.

> **Attention :** les mots de passe des bases sont fixés à leur **première**
> création. Si le `.env` est régénéré après coup, les connexions échouent
> (`password authentication failed`). Il faut alors soit restaurer l'ancien `.env`,
> soit recréer les bases avec `docker compose down -v`, ce qui **supprime leurs données**.
> Le sel `PSEUDO_SALT` ne doit pas non plus changer tant que des données sont
> conservées, sinon le droit à l'effacement ne retrouve plus les personnes.

### Données Kaggle (compte gratuit requis)

À télécharger dans `data/external/` :

| Fichier | Dataset |
|---|---|
| `vgsales.csv` | [Video Game Sales](https://www.kaggle.com/datasets/gregorut/videogamesales) |
| `games.csv` | [Steam Games Dataset](https://www.kaggle.com/datasets/fronkongames/steam-games-dataset) |
| `steam_reviews.csv` | [Steam Reviews 2021](https://www.kaggle.com/datasets/najzeko/steam-reviews-2021) |

### Services Docker

| Service | Rôle | Port |
|---|---|---|
| `partner-db` | SOURCE : base PostgreSQL du partenaire | 5435 |
| `spark` | SOURCE : Spark Thrift Server (big data) | 10000 |
| `gamescope-db` | STOCKAGE : base du projet | 5436 |
| `api` | MISE À DISPOSITION : API REST | 8000 |
| `uptime-kuma` | SUPERVISION : disponibilité de l'API | 3001 |

```bash
docker compose up -d --build --wait            # démarre tous les services
docker compose stop                            # les arrête (données conservées)
```

### Mise en place des systèmes sources (une seule fois)

```bash
python -m sources.partner_db.seed_partner_db   # games.csv -> PostgreSQL partenaire (~1 min)
python -m sources.bigdata.ingest_reviews       # CSV 8 Go -> data lake Parquet (~2 min)
```

> **Note :** aucune base Steam publique n'est accessible en connexion directe. La
> base « partenaire » et le data lake sont donc **mis en place** à partir de
> jeux de données réels (dossier `sources/`), pour simuler les systèmes d'un
> partenaire. Le code d'`extraction/` les traite comme des systèmes externes :
> compte en lecture seule, connexion réseau, requêtes SQL.

## Chaîne complète

```bash
python -m extraction.main        # 1. collecte des 6 sources -> data/raw/      (~3 h la 1re fois)
python -m cleaning.aggregate     # 2. agrégation + nettoyage -> data/clean/
python -m database.import_db     # 3. import dans PostgreSQL GameScope
python -m api.create_user --email admin@example.com --role admin   # 4. premier compte (mot de passe demandé)
python scripts/setup_monitoring.py   # 5. supervision (Uptime Kuma)
python -m pytest tests -q        # tests (normalisation, RGPD, API)
```

### Reproductibilité vérifiée

L'installation complète a été rejouée depuis un **clone vierge** du dépôt GitHub,
en suivant ce README : génération du `.env`, mise en place des deux systèmes sources,
extraction, nettoyage, création de la base, import, premier compte, API. Les
résultats sont identiques à l'installation d'origine (1 860 jeux du partenaire,
315 statistiques Spark, 61 099 avis, 1 982 jeux finaux) et les 66 tests passent.

---

## 1. Extraction (C1)

### Sources de données (toutes réelles)

| Type | Source | Module | Sortie |
|---|---|---|---|
| API REST | SteamSpy (`request=all`) | `extraction/steamspy.py` | `data/raw/steamspy_games.json` |
| API REST | Steam Store (`appdetails`, `appreviews`) | `extraction/steam_store_api.py` | `data/raw/steam_appdetails.jsonl`, `steam_reviews_api.jsonl` |
| Web scraping | Pages du Steam Store | `extraction/steam_scraper.py` | `data/raw/steam_store_pages.jsonl` |
| Fichier | Kaggle *Video Game Sales* (CSV) | `extraction/file_vgsales.py` | `data/raw/vgsales.parquet` |
| Base de données | Kaggle *Steam Games* dans PostgreSQL (base « partenaire ») | `extraction/db_partner.py` | `data/raw/partner_games.parquet` |
| Big data | Kaggle *Steam Reviews 2021* (21 M avis) en data lake Parquet, interrogé via Spark Thrift Server | `extraction/bigdata_reviews.py` | `data/raw/bigdata_reviews_*.parquet` |

### Commandes

```bash
python -m extraction.main --limit 20          # test rapide (~1 min)
python -m extraction.main                     # collecte complète, 2000 jeux (~3 h)
python -m extraction.main --sources scraping  # une seule source
# sources : api, scraping, file, database, bigdata
```

La collecte est **reprenable** : si elle est interrompue (Ctrl+C, coupure réseau),
relancer la même commande reprend là où elle s'était arrêtée. Journal :
`logs/extraction.log`.

### Déroulé du script

1. **Initialisation** : lecture du `.env`, création des dossiers, journalisation
2. **SteamSpy** : liste des N jeux les plus possédés (1 appel par page de 1000 jeux)
3. **Steam Store API** : fiche détaillée et 20 avis récents par jeu
4. **Scraping** : tags joueurs, avis des 30 derniers jours, langues, prix affiché
5. **Fichier, base de données, big data** : lecture et filtrage du CSV, requête
   SQL sur PostgreSQL (compte en lecture seule), requêtes Spark SQL sur le data lake
6. **Gestion des erreurs** : relances automatiques (429/5xx, backoff exponentiel).
   Une erreur sur un jeu ou sur une source est journalisée sans arrêter les autres.
7. **Sauvegarde** : écriture ligne par ligne (JSONL), sans perte en cas d'arrêt

### Contraintes des sources

- **Limites de débit** : SteamSpy 1 req/s (1 req/min pour `request=all`),
  Steam Store environ 200 req / 5 min, donc 1,8 s entre deux appels
- **Bridage de Steam** : Steam signale un dépassement par des **erreurs 502** (et non
  429). `throttled_get` (`extraction/utils.py`) fait alors des pauses de 1, 2 puis
  4 minutes et réessaie la même requête. Un jeu abandonné après 4 échecs n'est pas
  enregistré, et il sera retenté à la relance suivante.
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

## 2. Requêtes SQL (C2)

Requêtes versionnées et documentées (choix, filtres, jointures, optimisations
mesurées avec `EXPLAIN ANALYZE`) : [`sql/README.md`](sql/README.md).

## 3. Nettoyage et agrégation (C3)

```bash
python -m cleaning.aggregate   # data/raw/ -> data/clean/ (games, reviews, sales)
```

Règles de suppression, d'homogénéisation et de rapprochement :
[`cleaning/README.md`](cleaning/README.md).

## 4. Base de données (C4)

### Choix du SGBD : PostgreSQL 17

| Critère | PostgreSQL | MySQL | MongoDB | SQLite |
|---|---|---|---|---|
| Données fortement relationnelles (6 relations n,n, clés étrangères) | ✅ | ✅ | ❌ jointures limitées | ✅ |
| Contraintes `CHECK`, `UNIQUE NULLS NOT DISTINCT` | ✅ | partiel | ❌ | partiel |
| Rôles et droits fins (moindre privilège, RGPD) | ✅ | ✅ | ✅ | ❌ (fichier) |
| Accès concurrent API + équipe data | ✅ | ✅ | ✅ | ❌ |
| Déjà utilisé pour la base partenaire (une seule technologie à maîtriser) | ✅ | | | |

Les données sont structurées et fortement liées, et le RGPD impose un contrôle
d'accès fin : un SGBD relationnel serveur s'impose. PostgreSQL l'emporte par ses
contraintes avancées et la cohérence avec la base partenaire.

Modélisation Merise (MCD, MLD, MPD, optimisation, tests) : [`docs/merise.md`](docs/merise.md).

### Installation de la base

```bash
docker compose up -d --wait gamescope-db
```

Au **premier** démarrage, PostgreSQL exécute automatiquement les scripts de
`database/init/` :
- `01_schema.sql` crée les 21 tables, les contraintes et les index (MPD)
- `02_roles.sh` crée les rôles `gamescope_api` et `gamescope_analyst`

Vérification : `docker exec gamescope_db psql -U gamescope_admin -d gamescope -c "\dt"`.

Pour **réinitialiser** la base (supprime toutes les données) :
`docker compose down gamescope-db -v && docker compose up -d --wait gamescope-db`.

### Accès à la base

| Compte | Droits | Usage |
|---|---|---|
| `gamescope_admin` | propriétaire | import, procédures RGPD |
| `gamescope_api` | lecture des données, écriture de `api_user` | API REST (C5) |
| `gamescope_analyst` | lecture seule, **sans** `api_user` ni `rgpd_log` | équipe data (analyses, ML) |

Connexion : hôte `localhost`, port `5436`, base `gamescope`, mots de passe dans `.env`.

```python
# Exemple pour l'équipe data
import pandas as pd
from sqlalchemy import create_engine
engine = create_engine("postgresql+psycopg2://gamescope_analyst:<mot_de_passe>@localhost:5436/gamescope")
pd.read_sql("SELECT name, metacritic_score FROM game ORDER BY metacritic_score DESC NULLS LAST LIMIT 10", engine)
```

### Script d'import : `database/import_db.py`

```bash
python -m database.import_db
```

| | |
|---|---|
| **Dépendances** | Python 3.12, `pandas`, `pyarrow`, `psycopg2-binary` (voir `requirements.txt`) ; base `gamescope-db` démarrée ; jeu de données `data/clean/` produit par `python -m cleaning.aggregate` |
| **Configuration** | `.env` : `GAMESCOPE_DB_HOST`, `GAMESCOPE_DB_PORT`, `GAMESCOPE_DB_USER`, `GAMESCOPE_DB_PASSWORD` |
| **Entrée** | `data/clean/games.parquet`, `reviews.parquet`, `sales.parquet` |
| **Durée** | ~10 s |
| **Journal** | `logs/import_db.log` |

**Enchaînement** (ordre imposé par les clés étrangères) :

1. **Jeux** : `game`, puis pour chaque référentiel (développeurs, éditeurs, genres,
   catégories, tags, systèmes), insertion des valeurs nouvelles, récupération des
   identifiants et remplacement des liens du jeu. Ensuite `game_review_stats_2021`.
2. **Avis** : référentiel `language`, auteurs pseudonymisés (`author`), puis `review`
3. **Ventes** : référentiel `platform`, éditeurs, puis `sale`
4. **Maintenance** : `VACUUM ANALYZE` (espace réutilisable, statistiques du planificateur à jour)

**Garanties :**
- **Transactionnel** : tout l'import est une seule transaction. En cas d'erreur, un
  rollback laisse la base dans son état précédent.
- **Idempotent** : `INSERT ... ON CONFLICT DO UPDATE` sur les clés (`app_id`,
  `review_id`, clé naturelle des ventes). Relancer l'import met à jour les données
  sans créer de doublons.
- **Insertion par lots** de 5 000 lignes (`execute_values`) : 85 000 avis en quelques secondes.

### RGPD

| Document | Contenu |
|---|---|
| [`docs/rgpd/registre_traitements.md`](docs/rgpd/registre_traitements.md) | registre des 3 traitements de données personnelles (art. 30) |
| [`docs/rgpd/procedure_tri.md`](docs/rgpd/procedure_tri.md) | procédures de tri, fréquences, planification, droit à l'effacement |

```bash
python -m database.rgpd_cleanup --dry-run                  # simulation
python -m database.rgpd_cleanup                            # purge mensuelle
python -m database.rgpd_cleanup --erase-steamid <steamid>  # droit à l'effacement
```

## 5. API REST (C5)

```bash
docker compose up -d --build --wait api   # http://localhost:8000/docs
```

API FastAPI sécurisée (JWT, 3 rôles, OWASP API Top 10), documentée au standard
OpenAPI 3.1. Points de terminaison, authentification, sécurité, supervision et tests :
[`api/README.md`](api/README.md).
