"""Procédure de tri des données personnelles (RGPD) de la base GameScope.

Usage :
    python -m database.rgpd_cleanup --dry-run           # simulation, rien n'est supprimé
    python -m database.rgpd_cleanup                     # purge planifiée (mensuelle)
    python -m database.rgpd_cleanup --erase-steamid 7656119...   # droit à l'effacement

Traitements (détaillés dans docs/rgpd/procedure_tri.md) :
  1. avis collectés depuis plus de REVIEW_RETENTION_YEARS ans -> supprimés
  2. auteurs qui n'ont plus aucun avis -> supprimés (plus aucune finalité)
  3. comptes API inactifs depuis plus de API_USER_INACTIVITY_YEARS ans -> supprimés
  4. sur demande : tous les avis d'une personne, identifiée par son steamid

Chaque traitement est tracé dans la table rgpd_log (principe de responsabilité).
"""
import argparse
import logging
import os
import sys

from database.import_db import connect
from extraction.utils import pseudonymize, setup_logging

log = logging.getLogger("rgpd_cleanup")

REVIEW_RETENTION_YEARS = int(os.getenv("REVIEW_RETENTION_YEARS", 3))
API_USER_INACTIVITY_YEARS = int(os.getenv("API_USER_INACTIVITY_YEARS", 2))

PURGES = [
    ("purge avis > durée de conservation", "review",
     "DELETE FROM review WHERE collected_at < now() - make_interval(years => %(review_years)s)"),
    ("purge auteurs sans avis", "author",
     "DELETE FROM author a WHERE NOT EXISTS (SELECT 1 FROM review r WHERE r.author_id = a.author_id)"),
    ("purge comptes API inactifs", "api_user",
     "DELETE FROM api_user WHERE COALESCE(last_login_at, created_at)"
     " < now() - make_interval(years => %(user_years)s)"),
]


def run(cur, action: str, table: str, sql: str, params: dict, detail: str, dry_run: bool) -> int:
    cur.execute(sql, params)
    count = cur.rowcount
    log.info("%-40s : %d ligne(s)%s", action, count, " [simulation]" if dry_run else "")
    if not dry_run:
        cur.execute("INSERT INTO rgpd_log (action, table_name, rows_affected, detail) "
                    "VALUES (%s, %s, %s, %s)", (action, table, count, detail))
    return count


def erase_person(cur, steamid: str, dry_run: bool) -> None:
    """Droit à l'effacement (art. 17) : on recalcule le hash pour retrouver la personne."""
    author_hash = pseudonymize(steamid)
    # ON DELETE CASCADE : la suppression de l'auteur supprime tous ses avis
    run(cur, "effacement sur demande (art. 17)", "author",
        "DELETE FROM author WHERE author_hash = %(hash)s", {"hash": author_hash},
        "demande d'effacement d'une personne (identifiant non conservé)", dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Procédure de tri RGPD")
    parser.add_argument("--dry-run", action="store_true", help="simulation : annule tout à la fin")
    parser.add_argument("--erase-steamid", help="steamid d'une personne exerçant son droit à l'effacement")
    args = parser.parse_args()
    setup_logging("rgpd_cleanup")
    # Un identifiant vide ne doit jamais déclencher la purge générale par erreur
    if args.erase_steamid is not None and not args.erase_steamid.strip().isdigit():
        log.error("steamid invalide : 17 chiffres attendus (ex. 76561198000000000)")
        return 2

    params = {"review_years": REVIEW_RETENTION_YEARS, "user_years": API_USER_INACTIVITY_YEARS}
    try:
        conn = connect()
        with conn.cursor() as cur:
            if args.erase_steamid is not None:
                erase_person(cur, args.erase_steamid.strip(), args.dry_run)
            else:
                log.info("Conservation : avis %d ans, comptes inactifs %d ans",
                         REVIEW_RETENTION_YEARS, API_USER_INACTIVITY_YEARS)
                for action, table, sql in PURGES:
                    run(cur, action, table, sql, params,
                        f"conservation avis {REVIEW_RETENTION_YEARS} ans, "
                        f"inactivité comptes {API_USER_INACTIVITY_YEARS} ans", args.dry_run)
        if args.dry_run:
            conn.rollback()
            log.info("Simulation terminée : aucune modification enregistrée")
        else:
            conn.commit()
            log.info("Procédure de tri terminée")
        conn.close()
    except Exception:
        log.exception("Échec de la procédure de tri (aucune modification enregistrée)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
