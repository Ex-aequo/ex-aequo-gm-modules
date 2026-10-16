"""O jogo: um mundo, um estado, jogadores reais, GM e reinos-guardiões.

Tudo o que muda o estado passa por aqui e fica gravado na base de dados (tabela `game` + histórico em `turn_log`).
O motor (modules/turn-engine) é o mesmo do sandbox e da simulação.
"""
from __future__ import annotations

import copy
import json
import sys
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import OperationalError, ProgrammingError

from . import db
from .config import MODULES

sys.path.insert(0, str(MODULES / "turn-engine"))
from praga import DEFAULT, FREE, PRAGA, GameState, WorldMap, claim_kingdom, new_game, resolve_turn, validate  # noqa
from praga.bots import bot_orders  # noqa: E402
from praga.engine import validate_gm  # noqa: E402
from praga.orders import fort_cost  # noqa: E402
from praga.vision import plague_band, player_view  # noqa: E402

from .forgemap import get_forgemap  # noqa: E402

PRAGA_FACTION = {"id": PRAGA, "name": "A Praga", "color": "#3a1d40"}
BAND_TO_PLAGUE = (0.0, 0.3, 0.6, 1.0)


class GameError(ValueError):
    """Pedido recusado; a mensagem é mostrada a quem o fez."""


class Game:
    def __init__(self):
        self.lock = threading.RLock()
        self.loaded = False
        self.reload()

    # ------------------------------------------------------------------ carregar / gravar
    def reload(self):
        try:
            with db.engine.begin() as conn:
                row = conn.execute(select(db.game).where(db.game.c.id == 1)).mappings().first()
        except (ProgrammingError, OperationalError) as e:      # base sem tabelas ou inacessível: ainda não há jogo
            print("servidor: ainda não há jogo na base de dados:", str(e).splitlines()[0])
            row = None
        if not row:
            self.loaded = False
            return
        self.world_dir = Path(row["world_dir"])
        self.raw_world = json.loads((self.world_dir / "world.json").read_text())
        self.world = WorldMap(self.raw_world, DEFAULT)
        self.rules = DEFAULT
        self.state = GameState.from_dict(row["state"])
        self.pending: list[dict] = list(row["pending_gm"])
        self.history: list[dict] = list(row["history"])
        self.chronicle: list[dict] = list(row["chronicle"])
        self.colors = {int(k): v for k, v in row["colors"].items()}
        self.timer_minutes = row["timer_minutes"]
        self.deadline = row["deadline"]
        self.region_name = {r["id"]: r["name"] for r in self.raw_world["regions"]}
        self.full_names = {f["id"]: f.get("fullName", f["name"]) for f in self.raw_world["factions"]}
        self.start_names = {f["id"]: f["name"] for f in self.raw_world["factions"]}
        self.loaded = True

    def _save(self, conn):
        conn.execute(update(db.game).where(db.game.c.id == 1).values(
            state=self.state.to_dict(), pending_gm=self.pending, history=self.history,
            chronicle=self.chronicle[-500:], timer_minutes=self.timer_minutes, deadline=self.deadline))

    @staticmethod
    def create(world_dir: Path, rng_seed: str = "s0") -> "Game":
        """Mundo novo: todos os reinos começam como guardiões; os jogadores ficam com eles ao entrar (§7)."""
        world_dir = Path(world_dir).resolve()
        raw = json.loads((world_dir / "world.json").read_text())
        world = WorldMap(raw, DEFAULT)
        state = new_game(world, DEFAULT, None, rng_seed, players=set())
        colors = {str(f["id"]): f["color"] for f in raw["factions"]}
        g = {"id": 1, "world_dir": str(world_dir), "state": state.to_dict(), "pending_gm": [],
             "history": [], "chronicle": [{"turn": 1, "kind": "info",
                                           "text": "O mundo começa. A Praga dorme; só o mestre de jogo a pode despertar."}],
             "colors": colors, "timer_minutes": 0, "deadline": None}
        with db.engine.begin() as conn:
            conn.execute(delete(db.orders))
            conn.execute(delete(db.turn_log))
            conn.execute(delete(db.game))
            conn.execute(insert(db.game).values(**g))
        game = Game()
        game.history = [game._metrics(game.state)]
        with db.engine.begin() as conn:
            game._save(conn)
        return game

    # ------------------------------------------------------------------ jogadores
    def assign_kingdom(self, name: str | None = None) -> int:
        """Um jogador novo recebe o reino-guardião mais intacto (§7)."""
        with self.lock:
            fid = claim_kingdom(self.state, self.world, self.rules, name)
            if fid is None:
                raise GameError("não há reinos disponíveis")
            f = self.state.factions[fid]
            self.chronicle.append({"turn": self.state.turn, "kind": "faction", "regions": self.state.regions_of(fid)[:1],
                                   "text": f"Um jogador assume {f.name} ({len(self.state.regions_of(fid))} regiões)."})
            with db.engine.begin() as conn:
                self._save(conn)
            return fid

    def players(self) -> list[dict]:
        with db.engine.begin() as conn:
            us = conn.execute(select(db.users.c.username, db.users.c.faction_id)
                              .where(db.users.c.role == "player")).mappings().all()
            sent = {r["faction_id"] for r in conn.execute(select(db.orders.c.faction_id)
                                                          .where(db.orders.c.turn == self.state.turn)).mappings()}
        out = []
        for u in us:
            f = self.state.factions.get(u["faction_id"])
            out.append({"username": u["username"], "faction": u["faction_id"], "name": f.name if f else "—",
                        "active": bool(f and f.active), "controller": f.controller if f else None,
                        "submitted": u["faction_id"] in sent,
                        "idle": self.state.turn - f.last_orders if f else None})
        return out

    # ------------------------------------------------------------------ ordens dos jogadores
    def submit_orders(self, fid: int, orders: list[dict]) -> dict:
        with self.lock:
            f = self.state.factions.get(fid)
            if not f or not f.active:
                raise GameError("o teu reino já não está em jogo")
            if f.controller != "player":
                raise GameError("este reino passou a guardião por inatividade; pede ao GM para o recuperar")
            accepted, errors = validate(self.state, self.world, self.rules, fid, orders)
            with db.engine.begin() as conn:
                conn.execute(delete(db.orders).where((db.orders.c.faction_id == fid) &
                                                     (db.orders.c.turn == self.state.turn)))
                conn.execute(insert(db.orders).values(faction_id=fid, turn=self.state.turn, orders=accepted))
            return {"accepted": accepted, "errors": errors}

    def orders_of(self, fid: int) -> list[dict]:
        with db.engine.begin() as conn:
            r = conn.execute(select(db.orders.c.orders).where((db.orders.c.faction_id == fid) &
                                                              (db.orders.c.turn == self.state.turn))).first()
        return list(r[0]) if r else []

    # ------------------------------------------------------------------ vistas
    def _metrics(self, s: GameState) -> dict:
        total = len(s.regions)
        owners = Counter(r.owner for r in s.regions.values())
        sizes = {f.id: owners.get(f.id, 0) for f in s.factions.values() if f.active}
        leader = max(sizes, key=sizes.get) if sizes else None
        return {"turn": s.turn, "lost": round(owners.get(PRAGA, 0) / total, 4),
                "contaminated": round(sum(1 for r in s.regions.values() if r.owner != PRAGA and r.plague > 0) / total, 4),
                "free": round(owners.get(FREE, 0) / total, 4), "plague_active": s.plague_active,
                "leader": leader, "leader_regions": sizes.get(leader, 0), "sizes": {str(k): v for k, v in sizes.items()}}

    def gm_state(self, s: GameState | None = None) -> dict:
        """O mesmo formato que o sandbox (o painel do GM é o mesmo), mais o que só existe no jogo real."""
        s = s or self.state
        n = len(s.regions)
        owner, plague = [0] * (n + 1), [0.0] * (n + 1)
        for rid, r in s.regions.items():
            owner[rid], plague[rid] = r.owner, round(r.plague / 100, 3)
        men = Counter()
        for a in s.armies.values():
            men[a.owner] += a.men
        regs = Counter(r.owner for r in s.regions.values())
        past = self.history[-11]["sizes"] if len(self.history) > 10 else (self.history[0]["sizes"] if self.history else {})
        users = {p["faction"]: p for p in self.players()} if s is self.state else {}
        factions = sorted(({
            "id": f.id, "name": f.name, "color": self.colors.get(f.id, "#8a8070"), "active": f.active,
            "style": "guardião" if f.controller == "bot" else f"jogador: {users[f.id]['username']}" if f.id in users else "jogador",
            "bot": f.controller == "bot", "regions": regs.get(f.id, 0), "men": men.get(f.id, 0),
            "growth10": regs.get(f.id, 0) - past.get(str(f.id), 0), "stock": {k: round(v) for k, v in f.stock.items()},
            "protected": f.protected_until >= s.turn,
            "submitted": users[f.id]["submitted"] if f.id in users else None,
        } for f in s.factions.values()), key=lambda f: (-f["active"], f["bot"], -f["regions"], f["name"]))
        bands = [0] * (n + 1)
        for rid, r in s.regions.items():
            bands[rid] = 3 if r.owner == PRAGA else plague_band(r.plague, self.rules)
        return {"turn": s.turn, "owner": owner, "plague": plague, "bands": bands, "plague_active": s.plague_active,
                "plague_intensity": s.plague_intensity,
                "suggested_foci": [rid for rid in s.foci if s.regions[rid].owner != PRAGA],
                "factions": factions, "praga": PRAGA_FACTION, "metrics": self._metrics(s)}

    # ------------------------------------------------------------------ vista para o mapa do Province-Forge
    def _country(self, f) -> dict:
        full = self.full_names.get(f.id, f.name) if f.name == self.start_names.get(f.id) else f.name
        return {"id": str(f.id), "name": {"pt": f.name, "en": f.name}, "fullName": {"pt": full, "en": full},
                "color": self.colors.get(f.id, "#8a8070")}

    @staticmethod
    def _province(owner: int, band: int) -> dict:
        o = str(owner) if owner not in (FREE, PRAGA) else None
        return {"owner": o, "controller": o, "praga": 3 if owner == PRAGA else int(band)}

    def viewer_player(self, fid: int, v: dict) -> dict:
        """ViewerState do Province-Forge a partir do que o jogador sabe (fotografias do motor, §8)."""
        fm = get_forgemap(str(self.world_dir))
        known = {int(k) for k in v["regions"]}
        provinces, stale = {}, []
        for k, e in v["regions"].items():
            band = plague_band(e["plague"], self.rules) if "plague" in e else e.get("p", 0)
            provinces[int(k) - 1] = self._province(e["o"], band)
            if e["level"] == 1:
                stale.append(int(k) - 1)
        seen = {f["id"] for f in v["factions"]} | {fid}
        details = {}
        for rid in known:
            info = self.world.regions[rid]
            if info.resource:
                details[rid - 1] = {"resource": info.resource, "amount": info.amount}
        return {"turn": self.state.turn, "viewer": str(fid), "known": {str(fid): [r - 1 for r in known]},
                "countries": [self._country(f) for f in self.state.factions.values() if f.id in seen],
                "provinces": provinces, "visible": sorted(fm.visible_pf(known)), "stale": stale,
                "details": details, "reserved": []}

    def gm_full(self) -> dict:
        snap = self.gm_state()
        snap.update({"mode": "game", "pending": self.pending,
                     "history": [{k: v for k, v in h.items() if k != "sizes"} for h in self.history],
                     "chronicle": self.chronicle[-150:], "players": self.players(), "timer_minutes": self.timer_minutes,
                     "deadline": self.deadline.isoformat() if self.deadline else None})
        return snap

    def gm_region(self, rid: int) -> dict:
        s = self.state
        if rid not in s.regions:
            raise KeyError(rid)
        r, info = s.regions[rid], self.world.regions[rid]
        raw = self.raw_world["regions"][rid - 1]
        return {"id": rid, "name": raw["fullName"], "kind": raw["kind"], "biome": info.biome,
                "elevation": info.elevation, "coastal": info.coastal, "owner": r.owner, "pop": round(r.pop, 1),
                "order": r.order, "fort": r.fort, "building": r.building, "level": r.level, "plague": r.plague,
                "garrison": r.garrison, "armies": [{"owner": a.owner, "men": a.men, "vet": a.vet} for a in s.armies_in(rid)],
                "agents": [{"owner": g.owner, "kind": g.kind} for g in s.agents.values() if g.region == rid],
                "suggested_focus": rid in s.foci, "neighbors": list(info.neighbors)}

    def player_state(self, fid: int) -> dict:
        """Tudo o que o jogador fid sabe (nevoeiro, §8) + as suas ordens deste turno + o relógio."""
        s = self.state
        v = player_view(s, self.world, self.rules, fid)
        known = {f["id"] for f in v["factions"]} | {fid}
        v["regions"] = {str(k): e for k, e in v["regions"].items()}
        viewer = self.viewer_player(fid, v)
        own = s.regions_of(fid)
        v.update({"viewer": viewer,
                  "map_factions": [{"id": f.id, "name": f.name, "color": self.colors.get(f.id, "#8a8070")}
                                   for f in s.factions.values() if f.id in known] + [PRAGA_FACTION],
                  # factos fixos das regiões que conhece: terreno e recurso (o resto vem das fotografias)
                  "region_info": {k: {"terrain": self.world.regions[int(k)].terrain,
                                      "resource": self.world.regions[int(k)].resource,
                                      "amount": self.world.regions[int(k)].amount,
                                      "rough": self.world.regions[int(k)].rough} for k in v["regions"]},
                  "orders": self.orders_of(fid), "order_cost": self.rules.order_cost,
                  "costs": {"scout": self.rules.scout_cost, "spy": self.rules.spy_cost,
                            "recruit_per_100": self.rules.recruit_cost_per_100, "fort": self.rules.fort_cost,
                            "fort_by_region": {str(rid): fort_cost(rid, self.rules, self.world) for rid in own},
                            "building": {str(k): v for k, v in self.rules.building_cost.items()}},
                  "clock": {"turn": s.turn, "timer_minutes": self.timer_minutes,
                            "deadline": self.deadline.isoformat() if self.deadline else None},
                  "allowed_buildings": {str(rid): list(self.world.regions[rid].allowed_buildings) for rid in own}})
        return v

    def known_regions(self, fid: int) -> set[int]:
        return set(self.state.known.get(fid, {}))

    # ------------------------------------------------------------------ GM
    def add_gm_order(self, order: dict) -> list[dict]:
        with self.lock:
            acc, errs = validate_gm(self.state, self.world, self.rules, [order])
            if errs:
                raise GameError(errs[0].split(": ", 1)[-1])
            if order["type"] in ("plague_state", "plague_intensity"):
                self.pending = [o for o in self.pending if o["type"] != order["type"]]
            self.pending.append(acc[0])
            with db.engine.begin() as conn:
                self._save(conn)
            return self.pending

    def remove_gm_order(self, i: int) -> list[dict]:
        with self.lock:
            if not 0 <= i < len(self.pending):
                raise GameError("ordem inexistente")
            self.pending.pop(i)
            with db.engine.begin() as conn:
                self._save(conn)
            return self.pending

    def set_timer(self, minutes: int):
        with self.lock:
            self.timer_minutes = max(0, int(minutes))
            self.deadline = (datetime.now(timezone.utc) + timedelta(minutes=self.timer_minutes)
                             if self.timer_minutes else None)
            with db.engine.begin() as conn:
                self._save(conn)

    def _player_orders(self) -> dict[int, list[dict]]:
        with db.engine.begin() as conn:
            rows = conn.execute(select(db.orders).where(db.orders.c.turn == self.state.turn)).mappings().all()
        return {r["faction_id"]: list(r["orders"]) for r in rows}

    def resolve(self) -> dict:
        """Fecha o turno: ordens dos jogadores (quem não enviou fica com ordens permanentes), guardiões, GM."""
        with self.lock:
            before = self.state
            turn = before.turn
            orders = self._player_orders()
            gm = list(self.pending)
            self.state, events = resolve_turn(before, self.world, self.rules, orders, gm)
            self.pending = []
            self.history.append(self._metrics(self.state))
            self.chronicle += self._chronicle(turn, events, before)
            if self.timer_minutes:
                self.deadline = datetime.now(timezone.utc) + timedelta(minutes=self.timer_minutes)
            with db.engine.begin() as conn:
                conn.execute(insert(db.turn_log).values(turn=turn, state=before.to_dict(),
                                                        orders={str(k): v for k, v in orders.items()},
                                                        gm_orders=gm, events=[list(e) for e in events]))
                self._save(conn)
            return self.gm_full()

    def preview(self, turns: int = 10) -> dict:
        """Estimativa: no primeiro turno usa as ordens já enviadas; depois os jogadores são simulados por bots."""
        turns = max(1, min(int(turns), 30))
        with self.lock:
            s = copy.deepcopy(self.state)
            pending = list(self.pending)
            first = self._player_orders()
        start = {rid: r.owner for rid, r in s.regions.items()}
        series = []
        for i in range(turns):
            orders = first if i == 0 else {fid: bot_orders(s, self.world, self.rules, fid, "builder")
                                           for fid, f in s.factions.items() if f.active and f.controller == "player"}
            s, _ = resolve_turn(s, self.world, self.rules, orders, pending if i == 0 else [])
            series.append(self._metrics(s))
        newly = sorted(rid for rid, r in s.regions.items() if r.owner == PRAGA and start[rid] != PRAGA)
        hit = Counter(start[rid] for rid in newly if start[rid] > 0)
        snap = self.gm_state(s)
        snap.update({"from_turn": self.state.turn, "turns": turns,
                     "series": [{k: v for k, v in m.items() if k != "sizes"} for m in series], "newly_lost": newly,
                     "factions_hit": [{"id": f, "name": s.factions[f].name, "lost": c} for f, c in hit.most_common(8)]})
        return snap

    def _chronicle(self, turn: int, events: list, before: GameState) -> list[dict]:
        name = lambda f: ("terras livres" if f == FREE else "a Praga" if f == PRAGA
                          else before.factions[f].name if f in before.factions else f"fação {f}")
        out, lost, conq, outb = [], [], [], []
        for e in events:
            k = e[0]
            if k == "gm":
                out.append({"turn": turn, "kind": "gm", "text": e[2]})
            elif k == "gm_rejected":
                out.append({"turn": turn, "kind": "warn", "text": f"Ordem do GM recusada: {e[2]}"})
            elif k == "lost":
                lost.append(e[2])
            elif k == "conquest":
                conq.append(e)
            elif k == "outbreak":
                outb.append(e[2])
            elif k in ("to_bot", "eliminated", "regency"):
                out.append({"turn": turn, "kind": "faction", "text": e[2] + "."})
            elif k == "spy_caught":
                out.append({"turn": turn, "kind": "faction", "regions": [e[2]],
                            "text": f"Um espião de {name(e[1])} é apanhado em {self.region_name[e[2]]}."})
        if lost:
            names = ", ".join(self.region_name[r] for r in lost[:4]) + (f" e mais {len(lost) - 4}" if len(lost) > 4 else "")
            out.append({"turn": turn, "kind": "plague", "text": f"Caem para a Praga: {names}.", "regions": lost})
        if outb:
            out.append({"turn": turn, "kind": "plague", "regions": outb,
                        "text": f"Surtos em {len(outb)} região(ões) negligenciada(s)."})
        for _, a, rid, prev in conq[:6]:
            out.append({"turn": turn, "kind": "war", "regions": [rid],
                        "text": f"{name(a).capitalize()} toma {self.region_name[rid]} a {name(prev)}."})
        if len(conq) > 6:
            out.append({"turn": turn, "kind": "war", "text": f"Mais {len(conq) - 6} conquistas noutras frentes."})
        return out
