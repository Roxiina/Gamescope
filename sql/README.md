# Requêtes SQL d'extraction (C2)

| Fichier | Système | Exécuté par | Résultat |
|---|---|---|---|
| `partner/01_extraction.sql` | PostgreSQL 17 (`steam_partner`) | `extraction/db_partner.py` | `data/raw/partner_games.parquet` |
| `partner/02_optimisation.sql` | PostgreSQL 17 | manuellement (psql) | mesures `EXPLAIN ANALYZE` |
| `bigdata/01_reviews_stats.sql` | Spark SQL 3.5 (Thrift Server) | `extraction/bigdata_reviews.py` | `data/raw/bigdata_reviews_stats.parquet` |
| `bigdata/02_reviews_sample.sql` | Spark SQL 3.5 | `extraction/bigdata_reviews.py` | `data/raw/bigdata_reviews_sample.parquet` |

---

## 1. Base partenaire : `partner/01_extraction.sql`

**Objectif :** récupérer, pour les ~2 000 jeux suivis, la fiche catalogue et ses
référentiels (développeurs, éditeurs, genres, tags).

| Choix | Justification |
|---|---|
| **Sélection** par CTE `cible` (`unnest(:appids)`) | On ne lit que les jeux suivis (2 000) et non tout le catalogue (110 000). La liste est passée en **paramètre lié**, jamais concaténée dans le SQL : pas d'injection possible. |
| **Colonnes** | Seules les colonnes utiles à l'analyse sont sélectionnées. Les textes longs (description, URLs d'images, captures d'écran) ne sont pas lus. |
| `JOIN games` (jointure interne) | Un jeu absent du catalogue partenaire (sorti après la date du dataset) n'est pas renvoyé. Résultat obtenu : 1 860 jeux sur 2 000. |
| `LEFT JOIN LATERAL` + `array_agg` | Une ligne par jeu, avec les relations n,n agrégées en tableaux. `LEFT` conserve un jeu sans développeur renseigné. |
| **Filtrage** `tag_rank <= 10` | Seuls les 10 tags les plus votés sont gardés. Au-delà, les tags sont marginaux et bruités. |
| Compte `gamescope_reader` | Accès en lecture seule (`GRANT SELECT`) : l'extraction ne peut pas modifier la source. |

**Optimisation :** chaque sous-requête `LATERAL` filtre sur `app_id`, qui est la
**première colonne de la clé primaire** des tables d'association
(`game_tags (app_id, tag_id)`…). PostgreSQL utilise donc directement l'index de
la clé primaire, sans parcours complet des 1,2 million de liens jeu–tag.

## 2. Optimisation par index : `partner/02_optimisation.sql`

Mesures `EXPLAIN (ANALYZE, BUFFERS)`, cache chaud, PostgreSQL 17 :

| Cas | Avant | Après | Plan avant → après | Gain |
|---|---|---|---|---|
| **A.** jeux portant le tag « Rogue-like » | 58,0 ms | 13,7 ms | `Parallel Seq Scan` sur 1,2 M liens → `Bitmap Index Scan` (4 951 lignes) | ×4 |
| **B.** jeux Metacritic ≥ 80 sortis depuis 2015 | 9,9 ms | 1,1 ms | `Seq Scan` sur 110 000 jeux → `Bitmap Index Scan` (971 lignes) | ×9 |

- **Cas A :** la clé primaire `(app_id, tag_id)` ne sert pas pour une recherche par
  `tag_id` seul, qui n'est pas la première colonne de l'index. Index ajouté :
  `idx_game_tags_tag_id (tag_id)`.
- **Cas B :** index **composite** `(metacritic_score, release_date)` dans l'ordre des
  filtres, et **partiel** (`WHERE metacritic_score > 0`). Seuls les 4 258 jeux notés
  sont indexés, d'où un index de **112 Ko** seulement.
- **Constat honnête :** combinés sur une même requête (Rogue-like ET Metacritic ≥ 80),
  ces index n'apportaient presque rien (17 → 15 ms). Le planificateur commençait déjà
  par le filtre le plus sélectif. Un index ne sert que s'il correspond au chemin
  d'accès réellement choisi, d'où la mesure systématique avec `EXPLAIN ANALYZE`.

## 3. Big data : `bigdata/01_reviews_stats.sql`

**Objectif :** statistiques d'avis par jeu sur ~21 millions d'avis (5 Go en Parquet).

| Choix | Justification |
|---|---|
| Agrégation **dans Spark** | Seules ~300 lignes sont rapatriées au lieu de 21 M : le calcul est fait là où sont les données. |
| `AVG(CAST(recommended AS INT))` | Taux de recommandation : la moyenne d'un booléen converti en 0/1. |
| `PERCENTILE_APPROX(..., 0.5)` | Médiane approchée. Une médiane exacte imposerait un tri complet distribué, très coûteux. |
| `WHERE author_playtime_at_review IS NOT NULL` | Exclut les avis sans temps de jeu, qui fausseraient la médiane. |
| `HAVING COUNT(*) >= 50` | En dessous de 50 avis, un pourcentage n'est pas représentatif. |

## 4. Big data : `bigdata/02_reviews_sample.sql`

**Objectif :** au plus 200 avis en anglais par jeu, les plus utiles en premier,
pour l'analyse de sentiment (blocs E2/E3).

| Choix | Justification |
|---|---|
| `ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY votes_helpful DESC, ...)` | Limite par jeu (et non globale) : chaque jeu est représenté équitablement. |
| `WHERE year >= 2019` | **Partition pruning** : le data lake est partitionné par année (`year=2010/`...`year=2021/`), Spark ne lit que 3 dossiers sur 12. |
| `language = 'english'`, `LENGTH(review) >= 20` | **Predicate pushdown** : Parquet stocke des statistiques min/max par bloc, ce qui permet d'ignorer des blocs entiers sans les lire. |
| Colonnes listées explicitement | **Lecture en colonnes** : Parquet ne lit sur disque que les 8 colonnes demandées sur 22. |
| `author_hash` | Identifiant déjà pseudonymisé à l'ingestion (RGPD) : le `steamid` réel n'existe pas dans le data lake. |
