import hashlib
from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from . import models
from .database import get_db

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()

def require_role(allowed_roles: list[str]):
    def role_checker(user: models.User = Depends(get_current_user)):
        if not user or user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав доступа")
        return user
    return role_checker
