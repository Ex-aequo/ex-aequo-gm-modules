"""API do jogo. Correr a partir de modules/game-server:
    uvicorn server.app:app --port 8000
Primeiro criar o jogo: python scripts/new_game.py (ver README).

  /            cliente dos jogadores (modules/player-client, compilado)
  /gm/         painel do mestre de jogo (modules/gm-panel, compilado)
  /api/...     API; /api/map/... ficheiros do mapa, filtrados por jogador
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth
from .config import COOKIE_SECURE, GM_DIST, PLAYER_DIST, SESSION_DAYS
from .game import Game, GameError
from .mapdata import get_mapdata

app = FastAPI(title="Praga — servidor do jogo")
GAME = Game()


def game() -> Game:
    if not GAME.loaded:
        GAME.reload()
    if not GAME.loaded:
        raise HTTPException(503, "ainda não há jogo: corre scripts/new_game.py")
    return GAME


@app.exception_handler(GameError)
def game_error(_, e: GameError):
    return JSONResponse({"detail": str(e)}, status_code=400)


# ---------------------------------------------------------------------- relógio dos turnos
def _clock():
    while True:
        time.sleep(10)
        try:
            g = GAME
            if g.loaded and g.deadline and datetime.now(timezone.utc) >= g.deadline:
                g.resolve()
        except Exception as e:                        # o relógio nunca pode morrer por um turno que falha
            print("relógio: erro ao resolver o turno:", e)


@app.on_event("startup")
def start_clock():
    threading.Thread(target=_clock, daemon=True).start()


# ---------------------------------------------------------------------- contas
class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: Login, response: Response):
    token = auth.login(body.username.strip(), body.password)
    if not token:
        raise HTTPException(401, "nome ou palavra-passe errados")
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", secure=COOKIE_SECURE,
                        max_age=SESSION_DAYS * 86400, path="/")
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response, user: dict = Depends(auth.current_user)):
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    g = game()
    f = g.state.factions.get(user["faction_id"]) if user["faction_id"] else None
    return {"username": user["username"], "role": user["role"], "faction": user["faction_id"],
            "faction_name": f.name if f else None, "world": g.raw_world.get("name")}


# ---------------------------------------------------------------------- jogador
@app.get("/api/player/state")
def player_state(user: dict = Depends(auth.current_user)):
    auth.require_player(user)
    return game().player_state(user["faction_id"])


@app.put("/api/player/orders")
def player_orders(orders: list[dict] = Body(..., embed=True), user: dict = Depends(auth.current_user)):
    auth.require_player(user)
    return game().submit_orders(user["faction_id"], orders)


# ---------------------------------------------------------------------- mapa (filtrado por jogador)
def _known(user: dict):
    g = game()
    if user["role"] == "gm":
        return g, None, None
    fid = user["faction_id"]
    return g, g.known_regions(fid), (fid, g.state.turn)


@app.get("/api/map/world.json")
def map_world(user: dict = Depends(auth.current_user)):
    g, known, key = _known(user)
    names = None
    if known is not None:
        v = g.player_state(user["faction_id"])
        names = {f["id"]: f for f in v["map_factions"]}
    return Response(get_mapdata(str(g.world_dir)).world_json(known, names, key), media_type="application/json")


@app.get("/api/map/regions.png")
def map_regions(user: dict = Depends(auth.current_user)):
    g, known, key = _known(user)
    return Response(get_mapdata(str(g.world_dir)).regions_png(known, key), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/map/base.jpg")
def map_base(user: dict = Depends(auth.current_user)):
    g, known, key = _known(user)
    return Response(get_mapdata(str(g.world_dir)).base_jpg(known, key), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/map/tiles.json")
def map_tiles_json(user: dict = Depends(auth.current_user)):
    g, _, _ = _known(user)
    data = get_mapdata(str(g.world_dir)).tiles_json()
    if data is None:
        raise HTTPException(404, "este mundo não tem tiles")
    return Response(data, media_type="application/json")


@app.get("/api/map/tiles/{z}/{name}")
def map_tile(z: int, name: str, user: dict = Depends(auth.current_user)):
    g, known, _ = _known(user)
    p = get_mapdata(str(g.world_dir)).tile_path(z, name, known)
    if p is None:
        raise HTTPException(404, "tile inexistente ou desconhecido")
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------- mestre de jogo (mesma API que o sandbox)
def gm(user: dict = Depends(auth.current_user)) -> Game:
    auth.require_gm(user)
    return game()


class GMOrder(BaseModel):
    type: Literal["plague_state", "plague_focus", "plague_intensity", "rumor"]
    value: str | None = None
    region: int | None = None
    text: str | None = None
    factions: list[int] | None = None
    radius: int | None = None


@app.get("/api/gm/state")
def gm_state(g: Game = Depends(gm)):
    return g.gm_full()


@app.get("/api/gm/region/{rid}")
def gm_region(rid: int, g: Game = Depends(gm)):
    try:
        return g.gm_region(rid)
    except KeyError:
        raise HTTPException(404, "região inexistente")


@app.get("/api/gm/view/{fid}")
def gm_view(fid: int, g: Game = Depends(gm)):
    if fid not in g.state.factions:
        raise HTTPException(404, "fação inexistente")
    v = g.player_state(fid)
    v["known_share"] = round(len(v["regions"]) / len(g.state.regions), 4)
    v["faction"]["command_points"] = g.state.command_points(fid, g.rules)
    return v


@app.post("/api/gm/orders")
def gm_add(order: GMOrder, g: Game = Depends(gm)):
    return {"pending": g.add_gm_order({k: v for k, v in order.model_dump().items() if v is not None})}


@app.delete("/api/gm/orders/{i}")
def gm_remove(i: int, g: Game = Depends(gm)):
    return {"pending": g.remove_gm_order(i)}


@app.post("/api/gm/turn")
def gm_turn(g: Game = Depends(gm)):
    return g.resolve()


class Preview(BaseModel):
    turns: int = Field(10, ge=1, le=30)


@app.post("/api/gm/preview")
def gm_preview(req: Preview, g: Game = Depends(gm)):
    return g.preview(req.turns)


class Timer(BaseModel):
    minutes: int = Field(0, ge=0, le=60 * 24 * 7)


@app.post("/api/gm/timer")
def gm_timer(req: Timer, g: Game = Depends(gm)):
    g.set_timer(req.minutes)
    return g.gm_full()


# ---------------------------------------------------------------------- interfaces compiladas
if GM_DIST.exists():
    app.mount("/gm", StaticFiles(directory=GM_DIST, html=True), name="gm")
if PLAYER_DIST.exists():
    app.mount("/assets", StaticFiles(directory=PLAYER_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def player_spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(PLAYER_DIST / "index.html")
