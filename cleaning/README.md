# Agrégation et nettoyage des données (C3)

Fusionne les 7 extractions brutes de `data/raw/` en **un jeu de données final
unique**, nettoyé et normalisé, dans `data/clean/`.

## Dépendances

- Python 3.12
- `pandas`, `pyarrow` (lecture et écriture Parquet)
- `rapidfuzz` (similarité de chaînes pour le rapprochement des noms)
- `pytest` (tests des règles de normalisation)

```bash
pip install -r requirements.txt
```

## Commandes

```bash
python -m extraction.main     # prérequis : produit data/raw/
python -m cleaning.aggregate  # agrégation + nettoyage -> data/clean/
python -m pytest tests -q     # tests des règles de normalisation
```

Journal : `logs/cleaning.log`. Bilan chiffré de chaque règle :
`data/clean/cleaning_report.json`.

## Jeu de données produit

Trois tables liées par `app_id`, la table `games` étant la référence :

| Fichier | Contenu | Clé |
|---|---|---|
| `games.parquet` | 1 ligne par jeu, toutes sources fusionnées (36 colonnes) | `app_id` |
| `reviews.parquet` | avis de joueurs (API Steam + big data), auteurs pseudonymisés | `review_id`, réf. `app_id` |
| `sales.parquet` | ventes par plateforme (vgsales) rapprochées des jeux Steam | réf. `app_id` |

## Enchaînement de l'algorithme

```
load_raw()      lecture des 8 fichiers bruts
   │
build_games()   1. dédoublonnage par app_id dans chaque source
   │            2. jointure gauche sur la liste de référence SteamSpy
   │            3. suppression des entrées corrompues ou hors périmètre
   │            4. choix de la valeur par ordre de priorité des sources
   │            5. homogénéisation des formats
   │
build_reviews() concaténation API + big data, nettoyage du texte, suppressions,
   │            conversion des dates et des langues
   │
build_sales()   suppressions (doublons, incohérences), rapprochement des noms
   │            avec les jeux Steam, conversion des unités
   │
validate()      10 contrôles qualité bloquants (unicité, intégrité référentielle,
   │            bornes). Le script échoue si un seul contrôle échoue.
   │
sauvegarde      games / reviews / sales en Parquet + rapport JSON
```

## Priorité des sources (table `games`)

Quand plusieurs sources fournissent une même information, on prend la première
valeur renseignée dans cet ordre :

| Champ | Priorité | Raison |
|---|---|---|
| nom | API Steam → SteamSpy → base partenaire | L'API donne le nom officiel actuel (« Counter-Strike 2 » et non « Counter-Strike: Global Offensive ») |
| date de sortie | API → page scrapée → base partenaire | |
| prix | API (centimes, si en EUR) → prix scrapé | Le prix de l'API est structuré. Le prix scrapé couvre les jeux sans `price_overview` |
| propriétaires | SteamSpy → base partenaire | SteamSpy est plus récent (2026) que le dataset Kaggle |
| genres | API → base partenaire | |
| tags | page scrapée → base partenaire | Les tags scrapés sont les tags joueurs actuels |
| Metacritic | API → base partenaire | |

La colonne `sources` garde la trace des sources qui ont contribué à chaque jeu.

## Entrées corrompues : identification et suppression

| Table | Règle | Supprimées |
|---|---|---|
| games | retiré de la vente (fiche API **et** page indisponibles) | 1 |
| games | démo ou contenu qui n'est pas un jeu (`type != game`) | 2 |
| games | nom absent dans toutes les sources | 0 |
| games | date de sortie absente ou illisible dans toutes les sources | 15 |
| reviews | texte d'avis vide | 151 |
| reviews | doublon de `review_id` (version API conservée, plus récente) | 151 |
| reviews | date de publication incohérente (avant 2003 ou dans le futur) | 0 |
| reviews | avis d'un jeu absent du jeu de données final (hors périmètre) | 14 873 |
| sales | doublon exact (jeu, plateforme, année) | 2 |
| sales | doublon partiel : même jeu et plateforme, sans année, alors qu'une ligne datée existe | 1 |
| sales | somme des ventes régionales ≠ total mondial (écart > 0,02 M) | 7 |
| sales | rapprochement ambigu : plus de 10 ans entre la sortie console et la sortie Steam | 47 |

Certaines valeurs aberrantes sont **corrigées** plutôt que supprimées, car le reste
de la ligne est valide. Par exemple, une note Metacritic de `0` signifie « non noté »
dans la base partenaire et devient une valeur manquante (901 cas).

## Homogénéisation des formats

| Donnée | Formats rencontrés | Format final |
|---|---|---|
| Noms | `Far Cry® New Dawn`, `OCTOPATH TRAVELER™` | sans ™ ® ©, espaces normalisés |
| Dates | `29 Sep, 2015` (API), `Aug 1, 2023` (partenaire), `Sep 2015`, `''` | `date` ISO 8601 |
| Années | `2006`, `N/A` | entier ou valeur manquante |
| Prix | centimes `1999`, texte `12,99€`, `9,--€`, `Free To Play`, `7,99€ / month` | euros décimaux, `0.0` si gratuit, manquant pour un abonnement |
| Propriétaires | `1,000,000 .. 2,000,000` (SteamSpy), `1000000 - 2000000` (partenaire) | `owners_min`, `owners_max` entiers |
| Ventes | millions (`41.49`) | unités (`41490000`) |
| Durées | minutes | minutes (entier) |
| Dates d'avis | timestamp Unix | `datetime` UTC |
| Langues | `schinese`, `brazilian`, `koreana` | codes BCP 47 : `zh-Hans`, `pt-BR`, `ko` |
| Plateformes | `X360`, `PS2`, `GEN` | `Xbox 360`, `PlayStation 2`, `Mega Drive` |
| Listes | tableau JSON, tableau PostgreSQL, texte `"Valve, Hidden Path"` | liste dédoublonnée |

## Rapprochement des noms (ventes ↔ jeux Steam)

vgsales n'a pas d'identifiant Steam : le lien se fait par le nom, en 3 étapes,
de la plus sûre à la moins sûre.

1. **Clé identique** : minuscules, sans accents, apostrophes, ponctuation ni ™®.
   `Assassin’s Creed® III` et `Assassin's Creed III` donnent `assassins creed iii`.
2. **Clé compacte** (sans espaces) : `Puyo PuyoTetris` = `Puyo Puyo Tetris`.
3. **Similarité ≥ 97 %** (rapidfuzz), **avec les mêmes numéros d'épisode**.

**Choix guidés par l'audit des résultats :**
- Un premier seuil à 95 % rapprochait « Final Fantasy X » de « FINAL FANTASY IX »
  (96 % de similarité). Les numéros d'épisode, en chiffres arabes **et romains**,
  doivent désormais être identiques.
- Les noms identiques peuvent désigner des jeux différents : « Resident Evil 2 »
  (PS1, 1998) n'est pas le remake Steam de 2019. Un écart de plus de 10 ans
  entre les sorties rend le rapprochement ambigu, et la ligne est écartée.
- Une clé portée par plusieurs jeux Steam est ignorée, faute de pouvoir choisir.

On privilégie la **précision** : une vente non rapprochée est une perte
d'information, alors qu'une vente mal rapprochée fausserait les analyses.
Résultat : 714 correspondances exactes, 5 compactes, 0 approchée.

## Tests

`tests/test_normalize.py` vérifie chaque règle de normalisation sur des valeurs
réelles rencontrées dans les sources (34 tests). Ces tests ont révélé un bug :
la normalisation Unicode NFKC transformait `™` en `TM` avant sa suppression.
