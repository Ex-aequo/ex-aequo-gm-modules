"""Base de dados (SQLAlchemy Core). PostgreSQL em produção; o JSON fica em JSONB.

Um só mundo por servidor (decisão de 2026-10-16): a tabela `game` tem uma única linha.
"""
from __future__ import annotations

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, create_engine,
                        func)
from sqlalchemy.dialects.postgresql import JSONB

from .config import DATABASE_URL

J = JSON().with_variant(JSONB(), "postgresql")
meta = MetaData()

users = Table(
    "users", meta,
    Column("id", Integer, primary_key=True),
    Column("username", String(40), unique=True, nullable=False),
    Column("pw_hash", Text, nullable=False),
    Column("role", String(10), nullable=False),            # "gm" | "player"
    Column("faction_id", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
sessions = Table(
    "sessions", meta,
    Column("token", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
game = Table(
    "game", meta,
    Column("id", Integer, primary_key=True),               # sempre 1
    Column("world_dir", Text, nullable=False),
    Column("state", J, nullable=False),
    Column("pending_gm", J, nullable=False),
    Column("history", J, nullable=False),
    Column("chronicle", J, nullable=False),
    Column("colors", J, nullable=False),
    Column("timer_minutes", Integer, nullable=False, server_default="0"),
    Column("deadline", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)
turn_log = Table(
    "turn_log", meta,
    Column("turn", Integer, primary_key=True),             # turno resolvido
    Column("state", J, nullable=False),                    # estado no início desse turno
    Column("orders", J, nullable=False),
    Column("gm_orders", J, nullable=False),
    Column("events", J, nullable=False),
    Column("resolved_at", DateTime(timezone=True), server_default=func.now()),
)
orders = Table(
    "orders", meta,
    Column("faction_id", Integer, primary_key=True),
    Column("turn", Integer, primary_key=True),
    Column("orders", J, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def create_all():
    meta.create_all(engine)


def drop_all():
    meta.drop_all(engine)
