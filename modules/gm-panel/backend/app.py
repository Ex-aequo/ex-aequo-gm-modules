"""API do painel do GM (sandbox local).

Correr a partir de modules/gm-panel:
    uvicorn backend.app:app --port 8000
Variáveis de ambiente:
    PRAGA_WORLD  caminho para world.json (padrão: ../world-map/web/data/world.json)
    PRAGA_DATA   pasta onde se guardam os turnos (padrão: build/sandbox)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .sandbox import GMError, Sandbox

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
WORLD = Path(os.environ.get("PRAGA_WORLD", MODULE.parent / "world-map/web/data/world.json"))
DATA = Path(os.environ.get("PRAGA_DATA", MODULE / "build/sandbox"))

if not WORLD.exists():
    raise SystemExit(f"Falta {WORLD}. Gera o mundo com o módulo world-map (ver o README).")

sandbox = Sandbox(WORLD, DATA)
app = FastAPI(title="Praga — painel do GM (sandbox)")


class GMOrder(BaseModel):
    type: Literal["plague_state", "plague_focus", "plague_intensity"]
    value: str | None = None
    region: int | None = None

    def to_order(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class PreviewRequest(BaseModel):
    turns: int = Field(10, ge=1, le=30)


class ResetRequest(BaseModel):
    seed: str = "s0"


@app.get("/api/state")
def get_state():
    return sandbox.full_state()


@app.get("/api/region/{rid}")
def get_region(rid: int):
    try:
        return sandbox.region(rid)
    except KeyError:
        raise HTTPException(404, "região inexistente")


@app.post("/api/gm/orders")
def add_order(order: GMOrder):
    try:
        return {"pending": sandbox.add_order(order.to_order())}
    except GMError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/gm/orders/{index}")
def remove_order(index: int):
    try:
        return {"pending": sandbox.remove_order(index)}
    except GMError as e:
        raise HTTPException(404, str(e))


@app.post("/api/turn")
def resolve_turn():
    return sandbox.resolve()


@app.post("/api/preview")
def preview(req: PreviewRequest):
    return sandbox.preview(req.turns)


@app.post("/api/reset")
def reset(req: ResetRequest):
    sandbox.reset(req.seed)
    return sandbox.full_state()


# dados do mapa (base.jpg, regions.png, world.json) servidos tal como o módulo world-map os gera
app.mount("/data", StaticFiles(directory=WORLD.parent), name="data")

# interface já compilada (npm run build), se existir
DIST = MODULE / "frontend/dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(DIST / "index.html")
