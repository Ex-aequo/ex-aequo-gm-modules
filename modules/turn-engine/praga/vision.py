"""Visão, memória e rumores (regras §8, v0.5).

Níveis de cada região, por fação:
  1 conhecida  — já foi vista; fica a geografia e a última fotografia, com o turno em que foi tirada
  2 visível    — vizinha por terra de uma região tua, ou com um exército teu, um batedor teu, ou atacada por ti
  3 espiada    — tem um espião teu: números exatos, obras, ordem pública
  4 tua
Regiões nunca vistas não aparecem de todo na vista do jogador. Vizinhos por mar não dão visão.

As fotografias guardam só o que o nível permitia ver. A vista do jogador (player_view) é construída apenas a partir
delas e dos dados da própria fação — nunca do estado completo —, por isso não pode deixar escapar nada.
"""
from __future__ import annotations

import math
import random
from collections import deque

from .rules import FREE, PRAGA, Rules
from .state import GameState, WorldMap

KNOWN, VISIBLE, SPIED, OWN = 1, 2, 3, 4
SIZE_BANDS = (150, 400, 1000)          # pequena / média / grande / enorme
SIZE_PT = ("pequena", "média", "grande", "enorme")


def size_band(men: int) -> int:
    return sum(men >= b for b in SIZE_BANDS)


def plague_band(p: int, rules: Rules) -> int:
    """0 limpa, 1 contaminada, 2 infestada, 3 perdida."""
    return 0 if p < rules.plague_contaminated else 1 if p < rules.plague_infested else 2 if p < rules.plague_lost else 3


# --------------------------------------------------------------------------- visão
def compute_vision(state: GameState, world: WorldMap, fid: int, extra=()) -> dict[int, int]:
    vis: dict[int, int] = {}
    own = state.regions_of(fid)
    for rid in own:
        vis[rid] = OWN
    for rid in own:
        for n in world.regions[rid].neighbors:
            vis.setdefault(n, VISIBLE)
    for a in state.armies_of(fid):
        vis.setdefault(a.region, VISIBLE)
    for ag in state.agents_of(fid):
        if ag.kind == "spy":
            if vis.get(ag.region, 0) < SPIED:
                vis[ag.region] = SPIED
        else:
            vis.setdefault(ag.region, VISIBLE)
    for rid in extra:
        vis.setdefault(rid, VISIBLE)
    return vis


def snapshot(state: GameState, rid: int, level: int, rules: Rules) -> dict:
    """O que se vê de uma região a um dado nível. Chaves curtas: isto é guardado por fação e por região."""
    r = state.regions[rid]
    snap = {"t": state.turn, "o": r.owner, "p": plague_band(r.plague, rules), "f": r.fort,
            "b": r.building, "l": r.level,
            "a": sorted([a.owner, size_band(a.men)] for a in state.armies_in(rid))}
    if r.owner == FREE:
        snap["g"] = size_band(r.garrison)
    if level >= SPIED:
        snap["x"] = {"armies": sorted([a.owner, a.men, a.vet] for a in state.armies_in(rid)),
                     "garrison": r.garrison, "pop": round(r.pop, 1), "order": r.order, "plague": r.plague,
                     "project": dict(r.project) if r.project else None}
    return snap


def update_vision(state: GameState, world: WorldMap, rules: Rules, extra: dict[int, set] | None = None):
    """Recalcula a visão de cada fação ativa e atualiza as fotografias das regiões que ela vê agora."""
    extra = extra or {}
    for fid, f in sorted(state.factions.items()):
        if not f.active:
            state.vision.pop(fid, None)
            continue
        vis = compute_vision(state, world, fid, extra.get(fid, ()))
        state.vision[fid] = vis
        known = state.known.setdefault(fid, {})
        for rid, lvl in vis.items():
            known[rid] = snapshot(state, rid, SPIED if lvl == SPIED else VISIBLE, rules)


def first_contact(state: GameState, fid: int) -> bool:
    """A fação já conhece outra fação (viu uma região ou um exército dela)?"""
    for snap in state.known.get(fid, {}).values():
        if snap["o"] not in (FREE, PRAGA, fid) or any(o not in (fid,) for o, _ in snap["a"]):
            return True
    return False


# --------------------------------------------------------------------------- vista do jogador
def player_view(state: GameState, world: WorldMap, rules: Rules, fid: int) -> dict:
    """Tudo o que a fação fid sabe, e nada mais. É isto que o servidor envia ao jogador."""
    f = state.factions[fid]
    vis = state.vision.get(fid, {})
    regions = {}
    seen_factions = set()
    for rid, snap in sorted(state.known.get(fid, {}).items()):
        lvl = vis.get(rid, KNOWN)
        if lvl == OWN:
            r = state.regions[rid]
            entry = {"level": OWN, "t": state.turn, "o": fid, "pop": round(r.pop, 1), "order": r.order,
                     "fort": r.fort, "building": r.building, "lvl": r.level, "project": r.project,
                     "plague": r.plague, "iron_bonus": r.iron_bonus,
                     "a": sorted([a.owner, size_band(a.men)] for a in state.armies_in(rid) if a.owner != fid)}
        else:
            entry = dict(snap)
            entry["level"] = lvl
        regions[rid] = entry
        seen_factions.add(entry["o"])
        seen_factions.update(o for o, _ in entry.get("a", []))
    seen_factions -= {FREE, PRAGA, fid}
    return {
        "turn": state.turn,
        "faction": {"id": fid, "name": f.name, "stock": {k: round(v, 1) for k, v in f.stock.items()},
                    "postures": dict(f.postures), "active": f.active, "famine": f.famine,
                    "protected_until": f.protected_until, "command_points": state.command_points(fid, rules)},
        "regions": regions,
        "armies": [{"id": a.id, "region": a.region, "men": a.men, "vet": a.vet} for a in state.armies_of(fid)],
        "agents": [{"id": a.id, "kind": a.kind, "region": a.region} for a in state.agents_of(fid)],
        "factions": [{"id": o, "name": state.factions[o].name} for o in sorted(seen_factions) if o in state.factions],
        "inbox": list(state.inbox.get(fid, [])),
    }


# --------------------------------------------------------------------------- caixa de mensagens e rumores
def post(state: GameState, rules: Rules, fid: int, turn: int, kind: str, text: str, key: str | None = None):
    box = state.inbox.setdefault(fid, [])
    msg = {"turn": turn, "kind": kind, "text": text}
    if key:
        msg["key"] = key
    box.append(msg)
    del box[:-rules.inbox_keep]


RUMOUR_QUIET = 4
DIRECTIONS = ("a leste", "a sudeste", "a sul", "a sudoeste", "a oeste", "a noroeste", "a norte", "a nordeste")
RUMOURS = {
    "lost": ["Chegam rumores de terras engolidas pela Praga {dir}, {far}.",
             "Refugiados contam que aldeias inteiras desapareceram {dir}, {far}.",
             "Os mercadores já não vêm {dirfrom}: dizem que a Praga tomou as estradas, {far}."],
    "outbreak": ["Viajantes falam de uma doença estranha {dir}, {far}.",
                 "Diz-se que há febres e campos abandonados {dir}, {far}."],
    "spawn": ["Fala-se de coisas que saem da Praga e atacam povoações {dir}, {far}.",
              "Pastores juram ter visto vultos a sair da névoa {dir}, {far}."],
    "focus": ["Corre que algo despertou {dir}, {far}. Os animais fogem dessa direção.",
              "O céu escureceu {dir}, {far}, e ninguém sabe dizer porquê."],
}
FROM_DIR = {"a leste": "de leste", "a sudeste": "de sudeste", "a sul": "do sul", "a sudoeste": "de sudoeste",
            "a oeste": "de oeste", "a noroeste": "de noroeste", "a norte": "do norte", "a nordeste": "de nordeste"}


def _distance_band(hops: int) -> str:
    return "perto das tuas fronteiras" if hops <= 3 else "a alguns dias de marcha" if hops <= 6 else "em terras distantes"


def _direction(src, dst) -> str:
    ang = math.atan2(dst[1] - src[1], dst[0] - src[0])        # y cresce para sul
    return DIRECTIONS[int(round(ang / (math.pi / 4))) % 8]


def make_rumours(state: GameState, world: WorldMap, rules: Rules, events: list, turn: int):
    """Rumores vagos sobre a Praga para quem não vê o que aconteceu: direção, distância aproximada, nunca a região."""
    kinds = {"lost": "lost", "outbreak": "outbreak", "spawn": "spawn", "focus": "focus"}
    focus = {e[2] for e in events if e[0] == "focus"}
    # um foco também aparece como "perdida": conta só como foco
    happened = [(kinds[e[0]], e[2]) for e in events if e[0] in kinds and not (e[0] == "lost" and e[2] in focus)]
    if not happened:
        return
    rng = random.Random(f"{world.seed}:{state.rng_seed}:{turn}:rumours")
    for fid, f in sorted(state.factions.items()):
        if not f.active:
            continue
        own = state.regions_of(fid)
        if not own:
            continue
        vis = state.vision.get(fid, {})
        dist = _hops(world, own, rules.rumour_radius)
        cx = sum(world.regions[r].center[0] for r in own) / len(own)
        cy = sum(world.regions[r].center[1] for r in own) / len(own)
        # o mesmo rumor (tipo + direção) não se repete durante RUMOUR_QUIET turnos; no máximo 2 rumores por turno
        recent = {m.get("key") for m in state.inbox.get(fid, []) if m["turn"] > turn - RUMOUR_QUIET}
        heard = 0
        for kind, rid in sorted(happened, key=lambda kr: (kr[0] != "focus", dist.get(kr[1], 99), kr[1])):
            if heard >= 2 or rid in vis or rid not in dist:
                continue
            d = _direction((cx, cy), world.regions[rid].center)
            key = f"{kind}:{d}"
            if key in recent:
                continue
            recent.add(key)
            heard += 1
            text = rng.choice(RUMOURS[kind]).format(dir=d, dirfrom=FROM_DIR[d], far=_distance_band(dist[rid]))
            post(state, rules, fid, turn, "rumour", text, key)


def _hops(world: WorldMap, sources, limit: int) -> dict[int, int]:
    dist = {r: 0 for r in sources}
    q = deque(sources)
    while q:
        u = q.popleft()
        if dist[u] >= limit:
            continue
        for n in world.regions[u].neighbors:
            if n not in dist:
                dist[n] = dist[u] + 1
                q.append(n)
    return dist


def factions_near(state: GameState, world: WorldMap, rid: int, radius: int) -> list[int]:
    """Fações ativas com pelo menos uma região a ≤ radius passos (por terra) de rid. Para rumores do GM."""
    near = _hops(world, [rid], radius)
    return sorted({state.regions[r].owner for r in near if state.regions[r].owner > 0
                   and state.factions[state.regions[r].owner].active})
