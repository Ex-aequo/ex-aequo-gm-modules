"""Contas e sessões. Palavras-passe com scrypt (biblioteca padrão); sessão num cookie httpOnly."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException
from sqlalchemy import delete, insert, select

from . import db
from .config import SESSION_DAYS

COOKIE = "praga_session"


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
    except ValueError:
        return False
    test = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(test.hex(), h)


def create_user(conn, username: str, password: str, role: str, faction_id: int | None = None) -> int:
    return conn.execute(insert(db.users).values(username=username, pw_hash=hash_password(password), role=role,
                                                faction_id=faction_id).returning(db.users.c.id)).scalar_one()


def login(username: str, password: str) -> str | None:
    with db.engine.begin() as conn:
        u = conn.execute(select(db.users).where(db.users.c.username == username)).mappings().first()
        if not u or not check_password(password, u["pw_hash"]):
            return None
        token = secrets.token_hex(32)
        conn.execute(insert(db.sessions).values(token=token, user_id=u["id"],
                                                expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
        return token


def logout(token: str | None):
    if token:
        with db.engine.begin() as conn:
            conn.execute(delete(db.sessions).where(db.sessions.c.token == token))


def current_user(praga_session: str | None = Cookie(default=None)) -> dict:
    """Dependência FastAPI: o utilizador da sessão, ou 401."""
    if not praga_session:
        raise HTTPException(401, "sessão em falta")
    with db.engine.begin() as conn:
        row = conn.execute(
            select(db.users.c.id, db.users.c.username, db.users.c.role, db.users.c.faction_id, db.sessions.c.expires_at)
            .join(db.sessions, db.sessions.c.user_id == db.users.c.id)
            .where(db.sessions.c.token == praga_session)).mappings().first()
    if not row or row["expires_at"].replace(tzinfo=row["expires_at"].tzinfo or timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "sessão inválida ou expirada")
    return dict(row)


def require_gm(user: dict) -> dict:
    if user["role"] != "gm":
        raise HTTPException(403, "só o mestre de jogo")
    return user


def require_player(user: dict) -> dict:
    if user["role"] != "player" or not user["faction_id"]:
        raise HTTPException(403, "só jogadores com reino")
    return user
