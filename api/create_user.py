"""Création d'un compte en ligne de commande (premier administrateur notamment).

Usage :
    python -m api.create_user --email admin@example.com --role admin
Le mot de passe est demandé de façon masquée : il n'apparaît ni à l'écran ni
dans l'historique du terminal. Pour un script ou une CI :
    echo "$MOT_DE_PASSE" | python -m api.create_user --email ... --password-stdin
"""
import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import func, select

from api.database import SessionLocal
from api.models import ApiUser
from api.schemas import Role, UserCreate
from api.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Créer un compte de l'API GameScope")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=[r.value for r in Role], default="reader")
    parser.add_argument("--password-stdin", action="store_true",
                        help="lire le mot de passe sur l'entrée standard (scripts, CI)")
    args = parser.parse_args()

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Mot de passe (12 caractères minimum) : ")
        if password != getpass.getpass("Confirmation : "):
            print("Les mots de passe ne correspondent pas.")
            return 1
    try:
        body = UserCreate(email=args.email, password=password, role=args.role)
    except ValidationError as exc:
        print(f"Données invalides : {exc.errors()[0]['msg']}")
        return 1

    with SessionLocal() as db:
        if db.scalar(select(ApiUser).where(func.lower(ApiUser.email) == body.email.lower())):
            print("Un compte existe déjà avec cet e-mail.")
            return 1
        db.add(ApiUser(email=body.email.lower(), password_hash=hash_password(body.password),
                       role=body.role.value))
        db.commit()
    print(f"Compte {body.email} ({body.role.value}) créé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
