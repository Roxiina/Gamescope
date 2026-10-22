"""Gestion des comptes de l'API : réservée au rôle admin."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.database import get_db
from api.models import ApiUser
from api.schemas import Role, UserCreate, UserOut
from api.security import hash_password, require_role

router = APIRouter(prefix="/users", tags=["Comptes (admin)"],
                   dependencies=[Depends(require_role(Role.admin))])


@router.get("", response_model=list[UserOut], summary="Lister les comptes")
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(ApiUser).order_by(ApiUser.user_id)).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             summary="Créer un compte", responses={409: {"description": "E-mail déjà utilisé"}})
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(ApiUser).where(func.lower(ApiUser.email) == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail")
    user = ApiUser(email=body.email.lower(), password_hash=hash_password(body.password),
                   role=body.role.value)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # création simultanée du même e-mail
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail")
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer un compte",
               responses={404: {"description": "Compte inexistant"}})
def delete_user(user_id: int, db: Session = Depends(get_db),
                admin: ApiUser = Depends(require_role(Role.admin))):
    if user_id == admin.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Impossible de supprimer son propre compte")
    user = db.get(ApiUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte inexistant")
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
