# Procédures de tri des données personnelles - GameScope

Ces procédures appliquent les durées de conservation du
[registre des traitements](registre_traitements.md). Elles sont implémentées dans
[`database/rgpd_cleanup.py`](../../database/rgpd_cleanup.py) et testées dans
[`tests/test_rgpd.py`](../../tests/test_rgpd.py).

## Vue d'ensemble

| # | Traitement | Données visées | Règle | Mode | Fréquence |
|---|---|---|---|---|---|
| 1 | Minimisation à la collecte | steamid, pseudo, avatar, profil | steamid haché (SHA-256 salé), autres champs non collectés | automatisé (`extraction/`, `sources/bigdata/`) | à chaque collecte |
| 2 | Masquage dans le texte libre | e-mails, liens dans les avis | remplacés par `[email]`, `[lien]` | automatisé (`cleaning/`) | à chaque nettoyage |
| 3 | Purge des avis anciens | `review` | `collected_at` plus vieux que **3 ans** → suppression | automatisé | **mensuelle** |
| 4 | Purge des auteurs orphelins | `author` | auteur sans aucun avis → suppression | automatisé | **mensuelle** (après 3) |
| 5 | Purge des comptes inactifs | `api_user` | aucune connexion depuis **2 ans** → suppression | automatisé | **mensuelle** |
| 6 | Droit à l'effacement | `author` et ses `review` | sur demande, avec le steamid de la personne | manuel, outillé | **sous 1 mois** après la demande (art. 12.3) |
| 7 | Contrôle du registre | tout le schéma | toute nouvelle colonne personnelle est ajoutée au registre | manuel | à chaque évolution du schéma, et au minimum **annuelle** |

Les durées sont paramétrables dans `.env` (`REVIEW_RETENTION_YEARS`, `API_USER_INACTIVITY_YEARS`).

## Procédures 3 à 5 : purge mensuelle automatisée

```bash
python -m database.rgpd_cleanup --dry-run   # 1. simulation : affiche ce qui serait supprimé
python -m database.rgpd_cleanup             # 2. exécution
```

- Les trois purges s'exécutent dans **une seule transaction** : en cas d'erreur,
  rien n'est supprimé.
- Chaque exécution ajoute une ligne par purge dans la table `rgpd_log` (date,
  action, nombre de lignes), ce qui sert de preuve de conformité.
- La recherche des avis à purger utilise l'index `idx_review_collected_at`.

**Planification**, le 1er de chaque mois à 3 h :

```powershell
# Windows (Planificateur de tâches)
schtasks /Create /SC MONTHLY /D 1 /ST 03:00 /TN "GameScope RGPD" ^
  /TR "cmd /c cd /d C:\chemin\gamescope && .venv\Scripts\python -m database.rgpd_cleanup"
```

```bash
# Linux (crontab -e)
0 3 1 * * cd /opt/gamescope && .venv/bin/python -m database.rgpd_cleanup >> logs/cron.log 2>&1
```

**Contrôle :** consulter le journal après chaque exécution.

```sql
SELECT executed_at, action, rows_affected FROM rgpd_log ORDER BY executed_at DESC LIMIT 10;
```

## Procédure 6 : demande d'effacement d'une personne

GameScope ne stocke **jamais** le steamid. Pour retrouver une personne, on recalcule
l'empreinte à partir du steamid qu'elle fournit. Sans le sel secret, l'opération
inverse est impossible.

1. **Réception** de la demande (e-mail). La personne fournit son steamid
   (17 chiffres, visible dans l'URL de son profil Steam).
2. **Vérification d'identité** : la personne prouve qu'elle contrôle ce compte, par
   exemple en ajoutant temporairement un code donné par le studio dans le résumé de
   son profil Steam public.
3. **Simulation**, pour connaître le nombre d'avis concernés :
   ```bash
   python -m database.rgpd_cleanup --dry-run --erase-steamid 76561198xxxxxxxxx
   ```
4. **Exécution** :
   ```bash
   python -m database.rgpd_cleanup --erase-steamid 76561198xxxxxxxxx
   ```
   La suppression de l'auteur entraîne celle de tous ses avis (`ON DELETE CASCADE`).
5. **Fichiers intermédiaires** : supprimer aussi les avis de cette personne dans
   `data/raw/`, `data/clean/` et le data lake. Le plus simple est de relancer la
   chaîne complète (extraction, nettoyage, import), qui ne collecte plus ses avis
   s'ils ont été retirés de Steam. Sinon, on les filtre par empreinte.
6. **Réponse** à la personne sous 1 mois, en confirmant la suppression. Le steamid
   n'est conservé ni dans les journaux ni dans `rgpd_log`.

Un identifiant vide ou invalide est refusé : il ne peut pas déclencher la purge
générale par erreur.

## Vérification

```bash
python -m pytest tests/test_rgpd.py -v
```

| Test | Vérifie |
|---|---|
| `test_old_reviews_and_orphan_authors_are_purged` | un avis collecté il y a 4 ans est supprimé, celui d'il y a 1 an est conservé, l'auteur orphelin disparaît |
| `test_inactive_api_users_are_purged` | un compte inactif depuis 3 ans est supprimé, un compte actif est conservé |
| `test_erasure_request_deletes_all_reviews_of_a_person` | le steamid fourni permet de retrouver et de supprimer les avis de la personne |

Les tests travaillent dans une transaction annulée : la base réelle n'est pas modifiée.
