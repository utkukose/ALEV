"""web/auth.py — Admin kimlik doğrulama — döngüsel import'u kırar"""
import os
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "alev-secret-change-in-prod")
ALGORITHM  = "HS256"
TOKEN_EXPIRE = 60 * 8


def create_token(data: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE)
    return jwt.encode({**data, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_admin(request: Request) -> dict:
    token = request.cookies.get("admin_token")
    if not token:
        raise HTTPException(302, headers={"Location": "/admin/login"})
    p = verify_token(token)
    if not p or p.get("role") != "admin":
        raise HTTPException(302, headers={"Location": "/admin/login"})
    return p
