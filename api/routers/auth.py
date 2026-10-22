"""Authentification : obtention d'un jeton et consultation de son propre compte."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.database import get_db
from api.limiter import limiter
from api.models import ApiUser
from api.schemas import Token, UserOut
from api.security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/token", response_model=Token, summary="Obtenir un jeton d'accès",
             responses={401: {"description": "Identifiants invalides"},
                        429: {"description": "Trop de tentatives"}})
@limiter.limit(get_settings().rate_limit_login)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Échange e-mail (`username`) et mot de passe contre un jeton JWT.

    Limité à 5 tentatives par minute et par adresse IP (protection contre le brute force).
    """
    user = db.scalar(select(ApiUser).where(func.lower(ApiUser.email) == form.username.lower()))
    # Même message que le compte existe ou non : pas d'énumération des comptes
    if not verify_password(form.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect",
                            headers={"WWW-Authenticate": "Bearer"})
    # Date de dernière connexion : base de la purge RGPD des comptes inactifs
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return Token(access_token=create_access_token(user),
                 expires_in=get_settings().jwt_expire_minutes * 60)


@router.get("/me", response_model=UserOut, summary="Mon compte")
def me(user: ApiUser = Depends(get_current_user)):
    """Renvoie uniquement le compte du porteur du jeton."""
    return user
