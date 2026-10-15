"""GM sandbox: um mundo local onde as 24 fações são bots e o utilizador é o mestre de jogo.

Cada turno resolvido fica guardado em <data>/turns/state_NNNN.json (histórico completo e reconstituível).
A API (app.py) é fina: toda a lógica está aqui, para poder ser reutilizada pelo servidor real mais tarde.
"""
from __future__ import annotations

import copy
import json
import sys
import threading
from collections import Counter
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "turn-engine"
sys.path.insert(0, str(ENGINE))

from praga import DEFAULT, FREE, PRAGA, GameState, WorldMap, new_game, resolve_turn  # noqa: E402
from praga.bots import STYLES, bot_orders  # noqa: E402
from praga.engine import INTENSITY_PT, validate_gm  # noqa: E402

PRAGA_FACTION = {"id": PRAGA, "name": "A Praga", "color": "#3a1d40"}
STYLE_PT = {"expansionist": "expansionista", "builder": "construtor", "defender": "defensor"}


class GMError(ValueError):
    """Ordem do GM recusada; a mensagem é mostrada ao utilizador."""


class Sandbox:
    def __init__(self, world_path: str | Path, data_dir: str | Path, rng_seed: str = "s0"):
        self.world_path = Path(world_path)
        self.raw_world = json.loads(self.world_path.read_text())
        self.world = WorldMap(self.raw_world, DEFAULT)
        self.rules = DEFAULT
        self.dir = Path(data_dir)
        self.lock = threading.Lock()
        self.region_name = {r["id"]: r["name"] for r in self.raw_world["regions"]}
        if (self.dir / "turns").exists() and any((self.dir / "turns").glob("state_*.json")):
            self._load()
        else:
            self.reset(rng_seed)

    # ------------------------------------------------------------------ persistência
    def _save(self):
        (self.dir / "turns").mkdir(parents=True, exist_ok=True)
        (self.dir / "turns" / f"state_{self.state.turn:04d}.json").write_text(json.dumps(self.state.to_dict()))
        meta = {"pending": self.pending, "history": self.history, "chronicle": self.chronicle, "colors": self.colors}
        (self.dir / "sandbox.json").write_text(json.dumps(meta, ensure_ascii=False))

    def _load(self):
        last = sorted((self.dir / "turns").glob("state_*.json"))[-1]
        self.state = GameState.from_dict(json.loads(last.read_text()))
        meta = json.loads((self.dir / "sandbox.json").read_text())
        self.pending, self.history, self.chronicle = meta["pending"], meta["history"], meta["chronicle"]
        self.colors = {int(k): v for k, v in meta.get("colors", {}).items()}

    def reset(self, rng_seed: str = "s0"):
        with self.lock:
            for f in (self.dir / "turns").glob("state_*.json") if (self.dir / "turns").exists() else []:
                f.unlink()
            self.state = new_game(self.world, self.rules, "small", rng_seed)
            self.pending: list[dict] = []
            self.history: list[dict] = [self._metrics(self.state)]
            self.chronicle: list[dict] = [{"turn": 1, "kind": "info",
                                           "text": "O mundo começa. A Praga dorme; só o mestre de jogo a pode despertar."}]
            self.colors = {f["id"]: f["color"] for f in self.raw_world["factions"]}
            self._save()

    # ------------------------------------------------------------------ leitura
    @property
    def styles(self) -> dict[int, str]:
        fids = sorted(f for f in self.state.factions if f < 100)
        out = {fid: STYLES[i % len(STYLES)] for i, fid in enumerate(fids)}
        out.update({fid: "builder" for fid in self.state.factions if fid >= 100})
        return out

    def _metrics(self, s: GameState) -> dict:
        total = len(s.regions)
        owners = Counter(r.owner for r in s.regions.values())
        sizes = {f.id: owners.get(f.id, 0) for f in s.factions.values() if f.active}
        leader = max(sizes, key=sizes.get) if sizes else None
        return {
            "turn": s.turn,
            "lost": round(owners.get(PRAGA, 0) / total, 4),
            "contaminated": round(sum(1 for r in s.regions.values() if r.owner != PRAGA and r.plague > 0) / total, 4),
            "free": round(owners.get(FREE, 0) / total, 4),
            "plague_active": s.plague_active,
            "leader": leader, "leader_regions": sizes.get(leader, 0),
            "sizes": {str(k): v for k, v in sizes.items()},
        }

    def snapshot(self, s: GameState | None = None) -> dict:
        s = s or self.state
        n = len(s.regions)
        owner, plague = [0] * (n + 1), [0.0] * (n + 1)
        for rid, r in s.regions.items():
            owner[rid], plague[rid] = r.owner, round(r.plague / 100, 3)
        men = Counter()
        for a in s.armies.values():
            men[a.owner] += a.men
        regs = Counter(r.owner for r in s.regions.values())
        past = self.history[-11]["sizes"] if len(self.history) > 10 else self.history[0]["sizes"]
        styles = self.styles
        factions = sorted(({
            "id": f.id, "name": f.name, "color": self.colors.get(f.id, "#8a8070"), "active": f.active,
            "style": STYLE_PT.get(styles.get(f.id, ""), ""), "regions": regs.get(f.id, 0), "men": men.get(f.id, 0),
            "growth10": regs.get(f.id, 0) - past.get(str(f.id), 0),
            "stock": {k: round(v) for k, v in f.stock.items()},
            "protected": f.protected_until >= s.turn,
        } for f in s.factions.values()), key=lambda f: (-f["active"], -f["regions"], f["name"]))
        return {
            "turn": s.turn, "owner": owner, "plague": plague,
            "plague_active": s.plague_active, "plague_intensity": s.plague_intensity,
            "suggested_foci": [rid for rid in s.foci if s.regions[rid].owner != PRAGA],
            "factions": factions, "praga": PRAGA_FACTION,
            "metrics": self._metrics(s),
        }

    def full_state(self) -> dict:
        snap = self.snapshot()
        snap.update({"pending": self.pending, "history": [{k: v for k, v in h.items() if k != "sizes"} for h in self.history],
                     "chronicle": self.chronicle[-150:]})
        return snap

    def region(self, rid: int) -> dict:
        s = self.state
        if rid not in s.regions:
            raise KeyError(rid)
        r, info = s.regions[rid], self.world.regions[rid]
        raw = self.raw_world["regions"][rid - 1]
        armies = [{"owner": a.owner, "men": a.men, "vet": a.vet} for a in s.armies_in(rid)]
        return {
            "id": rid, "name": raw["fullName"], "kind": raw["kind"], "biome": info.biome, "elevation": info.elevation,
            "coastal": info.coastal, "owner": r.owner, "pop": round(r.pop, 1), "order": r.order, "fort": r.fort,
            "building": r.building, "level": r.level, "plague": r.plague, "garrison": r.garrison, "armies": armies,
            "suggested_focus": rid in s.foci, "neighbors": list(info.neighbors),
        }

    # ------------------------------------------------------------------ ordens do GM
    def add_order(self, order: dict) -> list[dict]:
        with self.lock:
            acc, errs = validate_gm(self.state, self.world, self.rules, [order])
            if errs:
                raise GMError(errs[0].split(": ", 1)[-1])
            if order["type"] == "plague_focus" and any(o["type"] == "plague_focus" and o["region"] == order["region"]
                                                        for o in self.pending):
                raise GMError("já há um foco pendente nesta região")
            if order["type"] in ("plague_state", "plague_intensity"):   # a última decisão substitui a anterior
                self.pending = [o for o in self.pending if o["type"] != order["type"]]
            self.pending.append(acc[0])
            self._save()
            return self.pending

    def remove_order(self, index: int) -> list[dict]:
        with self.lock:
            if not 0 <= index < len(self.pending):
                raise GMError("ordem inexistente")
            self.pending.pop(index)
            self._save()
            return self.pending

    # ------------------------------------------------------------------ turnos
    def _step(self, s: GameState, gm_orders: list[dict]):
        styles = self.styles
        orders = {fid: bot_orders(s, self.world, self.rules, fid, styles.get(fid, "builder"))
                  for fid, f in sorted(s.factions.items()) if f.active}
        return resolve_turn(s, self.world, self.rules, orders, gm_orders)

    def _chronicle(self, turn: int, events: list[tuple], before: GameState) -> list[dict]:
        name = lambda fid: ("terras livres" if fid == FREE else "a Praga" if fid == PRAGA
                            else before.factions[fid].name if fid in before.factions else f"fação {fid}")
        out, lost, conquests, outbreaks = [], [], [], []
        for e in events:
            k = e[0]
            if k == "gm":
                out.append({"turn": turn, "kind": "gm", "text": e[2]})
            elif k == "gm_rejected":
                out.append({"turn": turn, "kind": "warn", "text": f"Ordem do GM recusada: {e[2]}"})
            elif k == "lost":
                lost.append(e[2])
            elif k == "conquest":
                conquests.append(e)
            elif k == "outbreak":
                outbreaks.append(e[2])
            elif k in ("dissolve", "eliminated", "regency"):
                out.append({"turn": turn, "kind": "faction", "text": e[2] + "."})
        if lost:
            names = ", ".join(self.region_name[r] for r in lost[:4]) + (f" e mais {len(lost) - 4}" if len(lost) > 4 else "")
            out.append({"turn": turn, "kind": "plague", "text": f"Caem para a Praga: {names}.", "regions": lost})
        if outbreaks:
            out.append({"turn": turn, "kind": "plague", "text": f"Surtos em {len(outbreaks)} região(ões) negligenciada(s).",
                        "regions": outbreaks})
        for _, a, rid, prev in conquests[:4]:
            out.append({"turn": turn, "kind": "war", "text": f"{name(a).capitalize()} toma {self.region_name[rid]} a {name(prev)}.",
                        "regions": [rid]})
        if len(conquests) > 4:
            out.append({"turn": turn, "kind": "war", "text": f"Mais {len(conquests) - 4} conquistas noutras frentes."})
        return out

    def resolve(self) -> dict:
        with self.lock:
            before = self.state
            turn = before.turn
            self.state, events = self._step(before, self.pending)
            self.pending = []
            self.history.append(self._metrics(self.state))
            self.chronicle += self._chronicle(turn, events, before)
            self._save()
        return self.full_state()

    def preview(self, turns: int = 10) -> dict:
        """Simula os próximos turnos numa cópia, com as ordens pendentes no primeiro.
        Com bots, o resultado é exatamente o que vai acontecer; com jogadores humanos será uma estimativa."""
        turns = max(1, min(int(turns), 30))
        with self.lock:
            s = copy.deepcopy(self.state)
            pending = list(self.pending)
        start = {rid: r.owner for rid, r in s.regions.items()}
        series = []
        for i in range(turns):
            s, _ = self._step(s, pending if i == 0 else [])
            series.append(self._metrics(s))
        newly_lost = sorted(rid for rid, r in s.regions.items() if r.owner == PRAGA and start[rid] != PRAGA)
        hit = Counter(start[rid] for rid in newly_lost if start[rid] > 0)
        snap = self.snapshot(s)
        snap.update({
            "from_turn": self.state.turn, "turns": turns,
            "series": [{k: v for k, v in m.items() if k != "sizes"} for m in series],
            "newly_lost": newly_lost,
            "factions_hit": [{"id": fid, "name": s.factions[fid].name, "lost": n} for fid, n in hit.most_common(8)],
        })
        return snap
