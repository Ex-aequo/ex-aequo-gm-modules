"""Validação de ordens no momento da submissão (§2: o jogador sabe logo porque é que uma ordem é impossível).

Formato das ordens (dicts JSON):
  {"type": "move",     "army": 3, "path": [12, 13]}
  {"type": "attack",   "army": 3, "target": 14}
  {"type": "garrison", "army": 3}
  {"type": "purge",    "army": 3}
  {"type": "build",    "region": 12, "what": "fort" | "farm" | "sawmill" | "iron_mine" | "gold_mine" | "upgrade"}
  {"type": "recruit",  "region": 12, "men": 200}
  {"type": "posture",  "faction": 7, "value": "ally" | "neutral" | "hostile"}
  {"type": "recruit_agent", "region": 12, "kind": "scout" | "spy"}         (§8)
  {"type": "agent_move",    "agent": 4, "path": [13, 14]}                  (§8: batedor 2 passos, espião 1)
"""
from __future__ import annotations

from .rules import BUILDINGS, FREE, PRAGA, STONE_FORT_DISCOUNT, Rules
from .state import GameState, WorldMap


def fort_cost(rid: int, rules: Rules, world: WorldMap | None = None) -> dict:
    """Custo de um nível de fortificação; numa província com pedra custa metade (decisão de 2026-10-16)."""
    if world and world.regions[rid].resource == "stone":
        return {k: round(v * STONE_FORT_DISCOUNT) for k, v in rules.fort_cost.items()}
    return dict(rules.fort_cost)


def build_cost(state: GameState, rid: int, what: str, rules: Rules,
               world: WorldMap | None = None) -> tuple[dict | None, str | None]:
    r = state.regions[rid]
    if r.project:
        return None, "já há uma obra em curso nesta região"
    if what == "fort":
        if r.fort >= 3:
            return None, "fortificação já está no máximo"
        return fort_cost(rid, rules, world), None
    if what == "upgrade":
        if not r.building:
            return None, "não há edifício para subir de nível"
        if r.level >= 3:
            return None, "edifício já está no nível 3"
        return dict(rules.building_cost[r.level + 1]), None
    if what in BUILDINGS:
        if r.building:
            return None, "a região já tem um edifício de produção (só um por região)"
        return dict(rules.building_cost[1]), None
    return None, f"edifício desconhecido: {what}"


def move_cost(world: WorldMap, src: int, dst: int) -> int | None:
    info = world.regions[src]
    if dst in info.neighbors:
        return 2 if world.regions[dst].rough else 1
    if dst in info.sea_links:
        return 2                                    # travessia por mar gasta o movimento todo
    return None


def agent_step_cost(world: WorldMap, src: int, dst: int) -> int | None:
    """Batedores e espiões só andam por terra; terreno difícil custa 2."""
    if dst not in world.regions[src].neighbors:
        return None
    return 2 if world.regions[dst].rough else 1


def agent_cost(kind: str, rules: Rules) -> dict | None:
    return {"scout": rules.scout_cost, "spy": rules.spy_cost}.get(kind)


def validate(state: GameState, world: WorldMap, rules: Rules, fid: int, orders: list[dict]) -> tuple[list[dict], list[str]]:
    """Devolve (ordens aceites, erros). Aceita ordens pela ordem dada até esgotar pontos de comando."""
    accepted, errors = [], []
    faction = state.factions.get(fid)
    if not faction or not faction.active:
        return [], ["fação inexistente ou inativa"]
    pc = state.command_points(fid, rules)
    used_armies, used_regions, used_agents = set(), set(), set()
    reserve = {k: 0.0 for k in faction.stock}
    hostile_now = {k for k, v in faction.postures.items() if v == "hostile"}
    for o in orders:
        if o.get("type") == "posture" and o.get("value") == "hostile":
            hostile_now.add(str(o.get("faction")))

    for i, o in enumerate(orders):
        t = o.get("type")
        err = None
        cost = rules.order_cost.get(t)
        if cost is None:
            errors.append(f"ordem {i}: tipo desconhecido '{t}'")
            continue
        if cost > pc:
            errors.append(f"ordem {i} ({t}): sem pontos de comando")
            continue

        if t in ("move", "attack", "garrison", "purge"):
            a = state.armies.get(o.get("army"))
            if not a or a.owner != fid:
                err = "exército inexistente ou de outra fação"
            elif a.id in used_armies:
                err = "este exército já tem uma ordem"
            elif t == "move":
                path, here, steps = o.get("path") or [], a.region, 0
                for dst in path:
                    c = move_cost(world, here, dst)
                    if c is None:
                        err = f"região {dst} não é vizinha de {here}"
                        break
                    owner = state.regions[dst].owner
                    if owner != fid and faction.posture(owner) != "ally":
                        err = f"região {dst} não é tua nem de um aliado (para entrar à força usa Atacar)"
                        break
                    steps += c
                    here = dst
                if not err and (not path or steps > rules.move_steps):
                    err = "caminho vazio ou longo demais"
            elif t == "attack":
                tgt = o.get("target")
                if tgt not in state.regions or move_cost(world, a.region, tgt) is None:
                    err = "alvo não é vizinho do exército"
                else:
                    owner = state.regions[tgt].owner
                    if owner == fid:
                        err = "não podes atacar a tua própria região"
                    elif owner == PRAGA and state.regions[tgt].plague >= rules.plague_lost:
                        err = "região perdida: purga-a primeiro até abaixo de 80"
                    elif owner not in (FREE, PRAGA):
                        other = state.factions.get(owner)
                        if str(owner) not in hostile_now:
                            err = "só podes atacar fações declaradas Hostis"
                        elif other and other.protected_until >= state.turn:
                            err = "essa fação está protegida (entrada recente)"
                    if not err and faction.protected_until >= state.turn:
                        err = "estás protegido e não podes atacar"
            elif t == "purge":
                if state.regions[a.region].plague <= 0:
                    err = "não há Praga nesta região"
            if not err:
                used_armies.add(a.id)

        elif t in ("build", "recruit"):
            rid = o.get("region")
            r = state.regions.get(rid)
            if not r or r.owner != fid:
                err = "região não é tua"
            elif (rid, t) in used_regions:
                err = f"já há uma ordem {t} nesta região"
            elif t == "build":
                what = o.get("what")
                need, err = build_cost(state, rid, what, rules, world)
                if not err and what in BUILDINGS and what not in world.regions[rid].allowed_buildings:
                    err = f"{what} não é possível neste terreno"
                if not err:
                    for k, v in need.items():
                        if faction.stock[k] - reserve[k] < v:
                            err = f"recursos insuficientes ({k})"
                            break
                    else:
                        for k, v in need.items():
                            reserve[k] += v
            else:
                men = int(o.get("men", 0))
                if not 0 < men <= rules.recruit_max:
                    err = f"recrutar entre 1 e {rules.recruit_max} homens"
                elif r.plague >= rules.plague_infested:
                    err = "não se recruta numa região infestada"
                elif r.pop < men / 1000 * 2:
                    err = "população insuficiente"
                else:
                    for k, v in rules.recruit_cost_per_100.items():
                        if faction.stock[k] - reserve[k] < v * men / 100:
                            err = f"recursos insuficientes ({k})"
                            break
                    else:
                        for k, v in rules.recruit_cost_per_100.items():
                            reserve[k] += v * men / 100
            if not err:
                used_regions.add((rid, t))

        elif t == "recruit_agent":
            rid, kind = o.get("region"), o.get("kind")
            r = state.regions.get(rid)
            need = agent_cost(kind, rules)
            if not r or r.owner != fid:
                err = "região não é tua"
            elif need is None:
                err = "tipo de agente tem de ser 'scout' ou 'spy'"
            elif (rid, t) in used_regions:
                err = "já há um recrutamento de agente nesta região"
            else:
                for k, v in need.items():
                    if faction.stock[k] - reserve[k] < v:
                        err = f"recursos insuficientes ({k})"
                        break
                else:
                    for k, v in need.items():
                        reserve[k] += v
                    used_regions.add((rid, t))

        elif t == "agent_move":
            ag = state.agents.get(o.get("agent"))
            if not ag or ag.owner != fid:
                err = "agente inexistente ou de outra fação"
            elif ag.id in used_agents:
                err = "este agente já tem uma ordem"
            else:
                limit = rules.scout_steps if ag.kind == "scout" else rules.spy_steps
                path, here, steps = o.get("path") or [], ag.region, 0
                for dst in path:
                    c = agent_step_cost(world, here, dst) if dst in state.regions else None
                    if c is None:
                        err = f"região {dst} não é vizinha por terra de {here}"
                        break
                    steps += c
                    here = dst
                if not err and (not path or steps > limit):
                    err = "caminho vazio ou longo demais"
                if not err:
                    used_agents.add(ag.id)

        elif t == "posture":
            other = o.get("faction")
            if other not in state.factions or other == fid:
                err = "fação inválida"
            elif o.get("value") not in ("ally", "neutral", "hostile"):
                err = "postura inválida"

        if err:
            errors.append(f"ordem {i} ({t}): {err}")
        else:
            accepted.append(o)
            pc -= cost
    return accepted, errors
