"""Configuração por variáveis de ambiente (ver README)."""
from __future__ import annotations

import os
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1]
MODULES = MODULE.parent

DATABASE_URL = os.environ.get("PRAGA_DB", "postgresql+psycopg://localhost/praga")
SESSION_DAYS = int(os.environ.get("PRAGA_SESSION_DAYS", "14"))
COOKIE_SECURE = os.environ.get("PRAGA_COOKIE_SECURE", "0") == "1"      # 1 em produção (HTTPS)
PLAYER_DIST = MODULES / "player-client/dist"
GM_DIST = MODULES / "gm-panel/frontend/dist"
