"""Bots simples para a simulação. Não são IA a sério: existem para pôr as regras sob pressão.

Estilos:
  expansionist — recruta muito, ataca Terras Livres e vizinhos mais fracos
  builder      — constrói e sobe edifícios, só expande para Terras Livres
  defender     — fortifica, purga a Praga, raramente ataca
Cada bot submete ordens válidas pela ordem de prioridade até gastar os pontos de comando.
Nevoeiro (§8): os bots só escolhem alvos que a fação vê agora, e mantêm batedores a explorar o desconhecido.
Não usam espiões.
"""
from __future__ import annotations

import random

from .orders import agent_step_cost, move_cost, validate
from .rules import BUILDINGS, FREE, PRAGA, Rules
from .state import GameState, WorldMap

STYLES = ("expansionist", "builder", "defender")


def _strength_at(state: GameState, rid: int, fid: int) -> int:
    r = state.regions[rid]
    return sum(a.men for a in state.armies_in(rid) if a.owner == r.owner) + r.garrison


def _path_to_frontier(state: GameState, world: WorldMap, fid: int, start: int) -> list[int] | None:
    """Caminho mais curto, só por regiões próprias, até uma região que tenha um vizinho conquistável."""
    from collections import deque
    prev, q = {start: None}, deque([start])
    while q:
        u = q.popleft()
        if u != start and any(state.regions[n].owner != fid and
                              not (state.regions[n].owner == PRAGA and state.regions[n].plague >= rules_lost())
                              for n in world.regions[u].neighbors):
            path = []
            while u != start:
                path.append(u)
                u = prev[u]
            return path[::-1]
        for n in world.regions[u].neighbors:
            if n not in prev and state.regions[n].owner == fid:
                prev[n] = u
                q.append(n)
    return None


def rules_lost() -> int:
    from .rules import DEFAULT
    return DEFAULT.plague_lost


def bot_orders(state: GameState, world: WorldMap, rules: Rules, fid: int, style: str) -> list[dict]:
    rng = random.Random(f"bot:{state.rng_seed}:{fid}:{state.turn}")
    f = state.factions[fid]
    mine = state.regions_of(fid)
    if not mine:
        return []
    orders: list[dict] = []
    stock = dict(f.stock)
    men_total = sum(a.men for a in state.armies_of(fid))

    def afford(cost: dict) -> bool:
        if all(stock[k] >= v for k, v in cost.items()):
            for k, v in cost.items():
                stock[k] -= v
            return True
        return False

    vis = state.vision.get(fid, {})
    known = state.known.get(fid, {})

    # --- exércitos
    for a in state.armies_of(fid):
        r = state.regions[a.region]
        if r.plague >= 20 and style != "expansionist" or r.plague >= 50:
            orders.append({"type": "purge", "army": a.id})
            continue
        # alvos vizinhos: Terras Livres, regiões recuperáveis da Praga, rivais mais fracos
        targets = []
        for n in world.regions[a.region].neighbors + world.regions[a.region].sea_links:
            nr = state.regions[n]
            if nr.owner == fid or move_cost(world, a.region, n) is None or n not in vis:
                continue
            defense = _strength_at(state, n, fid)
            if nr.owner == FREE:
                score = nr.pop * 2 - defense / 50 - nr.plague
            elif nr.owner == PRAGA:
                if nr.plague >= rules.plague_lost:
                    continue
                score = nr.pop - nr.plague / 2
            else:
                other = state.factions.get(nr.owner)
                if style == "builder" or (other and other.protected_until >= state.turn):
                    continue
                if style == "defender" and rng.random() > 0.15:
                    continue
                score = nr.pop * 1.5 - defense / 40
            if a.men > defense * (1.6 if nr.owner not in (FREE, PRAGA) else 1.3):
                targets.append((score, n))
        attack_bias = {"expansionist": 0.9, "builder": 0.45, "defender": 0.3}[style]
        if targets and rng.random() < attack_bias and a.men >= 150:
            targets.sort(reverse=True)
            tgt = targets[0][1]
            owner = state.regions[tgt].owner
            if owner not in (FREE, PRAGA) and f.posture(owner) != "hostile":
                orders.append({"type": "posture", "faction": owner, "value": "hostile"})
            orders.append({"type": "attack", "army": a.id, "target": tgt})
            continue
        # sem alvo: ir para uma região própria com Praga, senão caminhar até à fronteira
        infected = [n for n in world.regions[a.region].neighbors
                    if state.regions[n].owner == fid and state.regions[n].plague > 0]
        if infected:
            orders.append({"type": "move", "army": a.id, "path": [infected[0]]})
            continue
        path = _path_to_frontier(state, world, fid, a.region) if style != "defender" or rng.random() < 0.3 else None
        if path:
            steps, here, take = 0, a.region, []
            for n in path:
                c = move_cost(world, here, n)
                if steps + c > rules.move_steps:
                    break
                take.append(n)
                steps += c
                here = n
            if take:
                orders.append({"type": "move", "army": a.id, "path": take})
                continue
        orders.append({"type": "garrison", "army": a.id})

    # --- batedores: andam para onde há mais vizinhos desconhecidos, evitando exércitos estrangeiros vistos
    for g in state.agents_of(fid):
        options = []
        for n in world.regions[g.region].neighbors:
            c = agent_step_cost(world, g.region, n)
            if c is None or c > rules.scout_steps:
                continue
            seen_armies = known.get(n, {}).get("a", [])
            if any(o != fid for o, _ in seen_armies):
                continue
            unknown = sum(1 for m in world.regions[n].neighbors if m not in known)
            options.append((unknown + rng.random(), n))
        if options:
            options.sort(reverse=True)
            orders.append({"type": "agent_move", "agent": g.id, "path": [options[0][1]]})
    want_scouts = {"expansionist": 2, "builder": 1, "defender": 1}[style]
    if len(state.agents_of(fid)) < want_scouts and stock["gold"] > 40 and afford(rules.scout_cost):
        orders.append({"type": "recruit_agent", "region": mine[0], "kind": "scout"})

    # --- economia: construir
    build_bias = {"expansionist": 0.4, "builder": 1.0, "defender": 0.7}[style]
    by_pop = sorted(mine, key=lambda rid: -state.regions[rid].pop)
    builds = 0
    for rid in by_pop:
        if builds >= (3 if style == "builder" else 1) or rng.random() > build_bias:
            break
        r, info = state.regions[rid], world.regions[rid]
        if r.project or r.plague >= rules.plague_infested:
            continue
        if style == "defender" and r.fort < 2 and r.plague > 0 and afford(rules.fort_cost):
            orders.append({"type": "build", "region": rid, "what": "fort"})
            builds += 1
        elif not r.building and info.allowed_buildings:
            # escolhe o edifício do recurso com mais produção base
            what = max(info.allowed_buildings, key=lambda b: info.base.get(BUILDINGS[b], 0))
            if afford(rules.building_cost[1]):
                orders.append({"type": "build", "region": rid, "what": what})
                builds += 1
        elif r.building and r.level < 3 and afford(rules.building_cost[r.level + 1]):
            orders.append({"type": "build", "region": rid, "what": "upgrade"})
            builds += 1

    # --- recrutar
    want = {"expansionist": 260 * len(mine) ** 0.5, "builder": 120 * len(mine) ** 0.5, "defender": 180 * len(mine) ** 0.5}[style]
    if men_total < want and stock["food"] > 10:
        for rid in by_pop[:2]:
            r = state.regions[rid]
            if r.plague < rules.plague_infested and r.order >= 1:
                men = 200 if style == "expansionist" else 100
                if afford({k: v * men / 100 for k, v in rules.recruit_cost_per_100.items()}):
                    orders.append({"type": "recruit", "region": rid, "men": men})

    accepted, _ = validate(state, world, rules, fid, orders)
    return accepted


# --------------------------------------------------------------------------- reinos-guardiões (§7, v0.6)
def guardian_orders(state: GameState, world: WorldMap, rules: Rules, fid: int) -> list[dict]:
    """Reino sem jogador. Defende, constrói, purga a Praga e expande só para Terras Livres (ou regiões recuperáveis
    da Praga). Nunca declara hostilidade nem ataca outro reino, jogador ou bot. Decide só com o que vê."""
    rng = random.Random(f"guardian:{state.rng_seed}:{fid}:{state.turn}")
    mine = state.regions_of(fid)
    if not mine:
        return []
    vis = state.vision.get(fid, {})
    stock = dict(state.factions[fid].stock)
    orders: list[dict] = []

    def afford(cost: dict) -> bool:
        if all(stock[k] >= v for k, v in cost.items()):
            for k, v in cost.items():
                stock[k] -= v
            return True
        return False

    for a in state.armies_of(fid):
        r = state.regions[a.region]
        if r.plague >= 20:
            orders.append({"type": "purge", "army": a.id})
            continue
        targets = []
        for n in world.regions[a.region].neighbors:            # só por terra: um guardião não desembarca
            nr = state.regions[n]
            if n not in vis or state.armies_in(n) and any(x.owner != fid for x in state.armies_in(n)):
                continue
            defense = _strength_at(state, n, fid)
            if nr.owner == FREE:
                score = nr.pop * 2 - defense / 50 - nr.plague
            elif nr.owner == PRAGA and nr.plague < rules.plague_lost:
                score = nr.pop - nr.plague / 2
            else:
                continue
            if a.men > defense * 1.5:
                targets.append((score, n))
        if targets and a.men >= 150 and rng.random() < 0.5:
            orders.append({"type": "attack", "army": a.id, "target": max(targets)[1]})
            continue
        infected = [n for n in world.regions[a.region].neighbors
                    if state.regions[n].owner == fid and state.regions[n].plague > 0]
        if infected:
            orders.append({"type": "move", "army": a.id, "path": [infected[0]]})
            continue
        orders.append({"type": "garrison", "army": a.id})

    built = 0
    for rid in sorted(mine, key=lambda r: -state.regions[r].pop):
        if built >= 2:
            break
        r, info = state.regions[rid], world.regions[rid]
        if r.project or r.plague >= rules.plague_infested:
            continue
        if not r.building and info.allowed_buildings:
            what = max(info.allowed_buildings, key=lambda b: info.base.get(BUILDINGS[b], 0))
            if afford(rules.building_cost[1]):
                orders.append({"type": "build", "region": rid, "what": what})
                built += 1
        elif r.building and r.level < 3 and afford(rules.building_cost[r.level + 1]):
            orders.append({"type": "build", "region": rid, "what": "upgrade"})
            built += 1

    men = sum(a.men for a in state.armies_of(fid))
    if men < 150 * len(mine) ** 0.5 and stock["food"] > 10:
        rid = max(mine, key=lambda r: (state.regions[r].pop, -r))
        r = state.regions[rid]
        if r.plague < rules.plague_infested and r.order >= 1:
            if afford({k: v for k, v in rules.recruit_cost_per_100.items()}):
                orders.append({"type": "recruit", "region": rid, "men": 100})

    accepted, _ = validate(state, world, rules, fid, orders)
    return accepted
