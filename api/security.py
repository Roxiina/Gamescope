"""Authentification (JWT) et autorisations par rôle.

- Mots de passe : bcrypt (lent par conception, salé), jamais stockés en clair
- Jeton JWT signé HS256, durée de vie courte (30 min par défaut)
- À chaque requête, l'utilisateur est relu en base : un compte supprimé ou
  rétrogradé perd ses droits immédiatement, sans attendre l'expiration du jeton
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.models import ApiUser
from api.schemas import Role

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

ROLE_LEVEL = {Role.reader: 1, Role.analyst: 2, Role.admin: 3}
# Hash factice : vérifié quand l'e-mail est inconnu, pour que la durée de réponse
# ne révèle pas si un compte existe (énumération des comptes)
_DUMMY_HASH = bcrypt.hashpw(b"compte-inexistant", bcrypt.gensalt())

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentification requise ou jeton invalide",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password_hash.encode() if password_hash else _DUMMY_HASH
    return bcrypt.checkpw(password.encode()[:72], candidate) and password_hash is not None


def create_access_token(user: ApiUser) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.user_id),
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> ApiUser:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],   # liste fermée : refuse alg=none
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise CREDENTIALS_ERROR
    user = db.get(ApiUser, user_id)
    if user is None:
        raise CREDENTIALS_ERROR
    return user


def require_role(minimum: Role):
    """Dépendance : refuse (403) un utilisateur dont le rôle est insuffisant (OWASP API5)."""
    def checker(user: ApiUser = Depends(get_current_user)) -> ApiUser:
        if ROLE_LEVEL[Role(user.role)] < ROLE_LEVEL[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Rôle '{minimum.value}' ou supérieur requis")
        return user
    return checker
