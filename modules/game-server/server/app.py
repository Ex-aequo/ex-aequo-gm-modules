"""API do jogo. Correr a partir de modules/game-server:
    uvicorn server.app:app --port 8000
Primeiro criar o jogo: python scripts/new_game.py (ver README).

  /            cliente dos jogadores (modules/player-client, compilado)
  /gm/         painel do mestre de jogo (modules/gm-panel, compilado)
  /api/...     API; /api/map/... mapa do Province-Forge (client map e tiles), filtrado por jogador
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

from pathlib import Path

from sqlalchemy import select, update

from . import auth, db
from .config import COOKIE_SECURE, GM_DIST, PLAYER_DIST, SESSION_DAYS, WORLDS_DIR
from .game import Game, GameError
from .forgemap import get_forgemap
from .worlds import JOBS, list_worlds

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
    if not GAME.loaded:
        GAME.reload()
    g = GAME if GAME.loaded else None                 # o GM entra mesmo sem jogo (para criar o primeiro mundo)
    f = g.state.factions.get(user["faction_id"]) if g and user["faction_id"] else None
    return {"username": user["username"], "role": user["role"], "faction": user["faction_id"],
            "faction_name": f.name if f else None, "world": g.raw_world.get("name") if g else None,
            "has_game": g is not None}


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
def _visible(user: dict):
    """(mapa, ids visíveis do Province-Forge ou None para o GM, chave de cache)."""
    g = game()
    fm = get_forgemap(str(g.world_dir))
    if user["role"] == "gm":
        return fm, None, None
    fid = user["faction_id"]
    return fm, fm.visible_pf(g.known_regions(fid)), (fid, g.state.turn)


@app.get("/api/map/client-map.json")
def map_client(user: dict = Depends(auth.current_user)):
    fm, vis, key = _visible(user)
    return Response(fm.client_map(vis, key), media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/api/map/{ver}/tiles/{z}/{x}/{y}.webp")
def map_tile(ver: str, z: int, x: int, y: int, user: dict = Depends(auth.current_user)):
    fm, vis, key = _visible(user)
    if vis is None:
        p = fm.tile_path(z, x, y)
        if p is None:
            raise HTTPException(404, "tile inexistente")
        return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})
    data = fm.player_tile(z, x, y, vis, key)
    if data is None:
        raise HTTPException(404, "tile inexistente")
    # muda quando o jogador conhece mais: o cliente põe o turno no URL ({ver}), por isso pode guardar-se
    return Response(data, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})


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


# ---------------------------------------------------------------------- mundos novos (GM)
def gm_only(user: dict = Depends(auth.current_user)) -> dict:
    auth.require_gm(user)
    return user


class NewWorld(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    seed: str = Field(..., min_length=1, max_length=60)
    params: dict = {}
    max_level: int = Field(4, ge=2, le=5)


@app.get("/api/gm/worlds")
def gm_worlds(_: dict = Depends(gm_only)):
    if not GAME.loaded:
        GAME.reload()
    return {"worlds": list_worlds(), "job": JOBS.status(),
            "current": str(GAME.world_dir) if GAME.loaded else None}


@app.post("/api/gm/worlds")
def gm_new_world(req: NewWorld, _: dict = Depends(gm_only)):
    try:
        return {"job": JOBS.start(req.name.strip(), req.seed.strip(), req.params, req.max_level)}
    except RuntimeError as e:
        raise HTTPException(409, str(e))


class StartGame(BaseModel):
    dir: str


@app.post("/api/gm/new-game")
def gm_new_game(req: StartGame, _: dict = Depends(gm_only)):
    """Começa um jogo novo num mundo gerado. APAGA o jogo atual; as contas dos jogadores ficam e cada uma recebe
    um reino do mundo novo (o mais intacto, como quem entra a meio, §7)."""
    d = Path(req.dir).resolve()
    if d.parent != WORLDS_DIR.resolve() or not (d / "world.json").exists():
        raise HTTPException(404, "mundo desconhecido")
    g = Game.create(d, f"s{int(time.time()) % 100000}")
    with db.engine.begin() as conn:
        players = conn.execute(select(db.users.c.id, db.users.c.username)
                               .where(db.users.c.role == "player").order_by(db.users.c.id)).all()
    assigned = []
    for uid, uname in players:
        try:
            fid = g.assign_kingdom()
        except GameError:
            fid = None
        with db.engine.begin() as conn:
            conn.execute(update(db.users).where(db.users.c.id == uid).values(faction_id=fid))
        assigned.append({"username": uname, "faction": fid})
    GAME.reload()
    return {"ok": True, "players": assigned}


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
