"""Resolução de um turno, pela ordem de fases de docs/regras-nucleo.md §5.

resolve_turn(state, world, rules, orders, gm_orders) -> (novo estado, eventos)
Determinístico: o mesmo estado + as mesmas ordens (de jogadores e do GM) dão sempre o mesmo resultado.
"""
from __future__ import annotations

import copy
import random

from .bots import guardian_orders
from .orders import agent_cost, build_cost, validate
from .rules import BUILDINGS, FREE, PRAGA, RESOURCES, Rules
from .state import Agent, Army, Faction, GameState, WorldMap
from .vision import factions_near, make_rumours, post, update_vision


def _rng(world: WorldMap, state: GameState, phase: str) -> random.Random:
    return random.Random(f"{world.seed}:{state.rng_seed}:{state.turn}:{phase}")


def regency_orders(state: GameState, world: WorldMap, rules: Rules, fid: int) -> list[dict]:
    """IA mínima para fações em Regência (§7): guarnecer e purgar onde há Praga."""
    out = []
    for a in state.armies_of(fid):
        if state.regions[a.region].plague > 0:
            out.append({"type": "purge", "army": a.id})
        else:
            out.append({"type": "garrison", "army": a.id})
    return out


def to_guardian(state: GameState, fid: int, events: list):
    """Reino abandonado (§7, v0.6): passa a reino-guardião (bot) e fica disponível para o próximo jogador.
    Os agentes do jogador são dispensados; posturas hostis voltam a neutras (um guardião não faz guerra)."""
    f = state.factions[fid]
    f.controller = "bot"
    f.postures = {k: v for k, v in f.postures.items() if v != "hostile"}
    for gid in [g.id for g in state.agents_of(fid)]:
        del state.agents[gid]
    events.append(("to_bot", fid, f"{f.name} fica sem senhor e passa a reino-guardião"))


def claim_kingdom(state: GameState, world: WorldMap, rules: Rules, name: str | None = None) -> int | None:
    """Um jogador novo recebe o reino-guardião mais intacto (§7, v0.6): mais regiões, menos Praga, mais homens.
    Fica protegido durante protection_turns. Devolve o id da fação, ou None se não houver reinos-guardiões."""
    best, best_key = None, None
    for fid, f in sorted(state.factions.items()):
        if not f.active or f.controller != "bot":
            continue
        regs = state.regions_of(fid)
        if not regs:
            continue
        sick = sum(1 for r in regs if state.regions[r].plague >= rules.plague_contaminated)
        key = (len(regs) - 2 * sick, sum(a.men for a in state.armies_of(fid)), -fid)
        if best_key is None or key > best_key:
            best, best_key = fid, key
    if best is None:
        return None
    f = state.factions[best]
    f.controller, f.last_orders = "player", state.turn
    f.protected_until = state.turn + rules.protection_turns - 1
    if name:
        f.name = name
    return best


def add_faction(state: GameState, world: WorldMap, rules: Rules, fid: int, name: str) -> int | None:
    """Entrada tardia (§7): região livre, limpa e afastada de jogadores ativos; tesouro protegido; proteção."""
    active_land = {rid for f in state.factions.values() if f.active for rid in state.regions_of(f.id)}
    best, best_pop = None, -1.0
    for rid, r in sorted(state.regions.items()):
        if r.owner != FREE or r.plague > 0:
            continue
        if any(n in active_land for n in world.regions[rid].neighbors):
            continue
        if r.pop > best_pop:
            best, best_pop = rid, r.pop
    if best is None:
        return None
    r = state.regions[best]
    r.owner, r.garrison, r.order = fid, 0, 2
    state.factions[fid] = Faction(id=fid, name=name, stock=dict(rules.new_player_treasury), joined=state.turn,
                                  protected_until=state.turn + rules.protection_turns - 1, last_orders=state.turn)
    state.armies[state.next_army] = Army(id=state.next_army, owner=fid, region=best, men=rules.start_army)
    state.next_army += 1
    update_vision(state, world, rules)
    return best


# --------------------------------------------------------------------------- combate
def _power(men: int, vet: int, mod: float, rules: Rules) -> float:
    return men * (1 + rules.vet_bonus * vet) * mod


def _defense_mod(state: GameState, world: WorldMap, rid: int, rules: Rules, garrisoned: bool) -> float:
    info, r = world.regions[rid], state.regions[rid]
    mod = 1 + rules.fort_bonus * r.fort
    if info.elevation >= 45:
        mod += rules.mountain_bonus
    elif info.rough:
        mod += rules.forest_bonus
    if garrisoned:
        mod += rules.garrison_bonus
    return mod


def _fight(attack: float, defend: float, rng: random.Random, rules: Rules) -> tuple[bool, float, float]:
    """Devolve (atacante vence?, fração de baixas do atacante, fração de baixas do defensor)."""
    a = attack * (1 + rng.uniform(-rules.combat_noise, rules.combat_noise))
    d = defend * (1 + rng.uniform(-rules.combat_noise, rules.combat_noise))
    if a > d:
        return True, min(0.9, 0.5 * d / a), 1.0
    return False, 1.0 if d > 2 * a else 0.6, min(0.9, 0.5 * a / max(d, 1))


# --------------------------------------------------------------------------- turno
def resolve_turn(state: GameState, world: WorldMap, rules: Rules, orders: dict[int, list[dict]],
                 gm_orders: list[dict] | None = None):
    s = copy.deepcopy(state)
    events: list[tuple] = []
    turn = s.turn

    # 0. decisões do mestre de jogo (§6.1)
    _apply_gm(s, world, rules, gm_orders or [], events)

    # reinos-guardiões e inatividade (§7): as ordens dos bots são do motor, não de quem submete
    orders = dict(orders)
    for fid, f in sorted(s.factions.items()):
        if not f.active:
            continue
        if f.controller == "bot":
            orders[fid] = guardian_orders(s, world, rules, fid)
            continue
        if fid in orders:
            f.last_orders = turn
        idle = turn - f.last_orders
        if idle >= rules.dissolve_after:
            to_guardian(s, fid, events)
            orders[fid] = guardian_orders(s, world, rules, fid)
        elif idle >= rules.regency_after:
            orders[fid] = regency_orders(s, world, rules, fid)
            if idle == rules.regency_after:
                events.append(("regency", fid, f"{f.name} entra em Regência"))

    # validação no servidor (as mesmas regras da submissão)
    valid: dict[int, list[dict]] = {}
    for fid, f in sorted(s.factions.items()):
        if f.active:
            acc, errs = validate(s, world, rules, fid, orders.get(fid, []))
            valid[fid] = acc
            if errs:
                events.append(("rejected", fid, len(errs)))

    # 1. diplomacia
    for fid, os_ in valid.items():
        for o in os_:
            if o["type"] == "posture":
                s.factions[fid].postures[str(o["faction"])] = o["value"]

    # 2. economia
    for fid, f in sorted(s.factions.items()):
        if not f.active:
            continue
        income = {k: 0.0 for k in RESOURCES}
        for rid in s.regions_of(fid):
            r, info = s.regions[rid], world.regions[rid]
            m = rules.order_production[r.order]
            prod = dict(info.base)
            prod["iron"] += r.iron_bonus
            prod["gold"] = prod.get("gold", 0) + rules.gold_base + rules.gold_per_kpop * r.pop
            if r.building and r.plague < rules.plague_infested:
                res = BUILDINGS[r.building]
                prod[res] = prod.get(res, 0) * rules.building_mult[r.level]
            if r.plague >= rules.plague_contaminated:
                prod["food"] *= rules.contaminated_food_mult
            for k in RESOURCES:
                income[k] += prod.get(k, 0) * m
            income["gold"] -= rules.building_upkeep[r.level] if r.building else 0
        men = sum(a.men for a in s.armies_of(fid))
        income["food"] -= men / 100 * rules.army_food_per_100
        income["gold"] -= men / 100 * rules.army_gold_per_100
        for g in s.agents_of(fid):
            income["gold"] -= rules.scout_upkeep if g.kind == "scout" else rules.spy_upkeep
        for k in RESOURCES:
            f.stock[k] = round(f.stock[k] + income[k], 2)
        f.famine = f.stock["food"] < 0
        if f.famine:
            f.stock["food"] = 0
            for a in s.armies_of(fid):
                a.men = int(a.men * (1 - rules.famine_army_loss))
        if f.stock["gold"] < 0:
            f.stock["gold"] = 0
            for a in s.armies_of(fid):
                a.men = int(a.men * (1 - rules.bankrupt_army_loss))
    for rid, r in s.regions.items():
        if r.owner in (FREE, PRAGA):
            continue
        f = s.factions[r.owner]
        if r.plague >= rules.plague_infested:
            r.pop *= 1 - rules.infested_pop_loss
        elif not f.famine:
            r.pop *= 1 + rules.pop_growth
        r.neglect = r.neglect + 1 if (r.order == 0 or f.famine) else 0
        if not f.famine and r.order < 3:
            r.order += 1
    for rid, r in s.regions.items():
        if r.owner == FREE and r.order == 0:
            r.neglect += 1

    # 3. movimento
    attacks: dict[int, list[tuple[Army, int]]] = {}
    purging, garrisoned = [], set()
    for fid, os_ in sorted(valid.items()):
        for o in os_:
            a = s.armies.get(o.get("army")) if "army" in o else None
            if o["type"] == "move" and a:
                a.region = o["path"][-1]
            elif o["type"] == "attack" and a:
                attacks.setdefault(o["target"], []).append((a, a.region))
            elif o["type"] == "purge" and a:
                purging.append(a)
            elif o["type"] == "garrison" and a:
                garrisoned.add(a.id)
    # batedores e espiões (§8): os batedores veem as regiões por onde passam; atacar também dá vista do alvo
    seen_now: dict[int, set] = {}
    for fid, os_ in sorted(valid.items()):
        for o in os_:
            if o["type"] == "agent_move" and o["agent"] in s.agents:
                g = s.agents[o["agent"]]
                g.region = o["path"][-1]
                if g.kind == "scout":
                    seen_now.setdefault(fid, set()).update(o["path"])
            elif o["type"] == "attack":
                seen_now.setdefault(fid, set()).add(o["target"])
    # exércitos sem ordem guarnecem (ordens permanentes)
    ordered = {o["army"] for os_ in valid.values() for o in os_ if "army" in o}
    garrisoned |= {aid for aid in s.armies if aid not in ordered}

    # 4–5. combate e conquista
    rng = _rng(world, s, "combat")
    for rid in sorted(attacks):
        for a, origin in sorted(attacks[rid], key=lambda x: x[0].id):
            if a.id not in s.armies:
                continue
            r = s.regions[rid]
            # outro reino tomou o alvo neste mesmo turno (ataques simultâneos a Terras Livres): sem hostilidade
            # declarada, o ataque não se faz — ninguém entra em guerra por acidente
            if r.owner not in (FREE, PRAGA, a.owner) and s.factions[a.owner].posture(r.owner) != "hostile":
                continue
            defenders = [d for d in s.armies_in(rid) if d.owner != a.owner and
                         (d.owner == r.owner or s.factions[a.owner].posture(d.owner) == "hostile")]
            g = any(d.id in garrisoned for d in defenders)
            mod = _defense_mod(s, world, rid, rules, g)
            dpow = sum(_power(d.men, d.vet, mod, rules) for d in defenders) + r.garrison * mod
            apow = _power(a.men, a.vet, 1.0, rules)
            if dpow <= 0:
                win, la, ld = True, 0.0, 1.0
            else:
                win, la, ld = _fight(apow, dpow, rng, rules)
            a.men = int(a.men * (1 - la))
            for d in defenders:
                d.men = int(d.men * (1 - ld))
                if d.men < 20:
                    del s.armies[d.id]
            r.garrison = int(r.garrison * (1 - ld))
            if a.men < 20:
                del s.armies[a.id]
                continue
            if win:
                a.vet = min(3, a.vet + 1)
                a.region = rid
                if not [d for d in s.armies_in(rid) if d.owner == r.owner and d.owner != a.owner]:
                    prev = r.owner
                    r.owner, r.order, r.garrison, r.project = a.owner, rules.conquest_order, 0, None
                    events.append(("conquest", a.owner, rid, prev))
            else:
                a.region = origin

    # 5b. batedores apanhados por exércitos não aliados; espiões descobertos (§8)
    rng_ag = _rng(world, s, "agents")
    for gid, g in sorted(s.agents.items()):
        f = s.factions[g.owner]
        r = s.regions[g.region]
        name = world.regions[g.region].name
        if g.kind == "scout":
            if any(a.owner != g.owner and f.posture(a.owner) != "ally" for a in s.armies_in(g.region)):
                del s.agents[gid]
                post(s, rules, g.owner, turn, "report", f"O nosso batedor foi apanhado em {name}.")
                events.append(("scout_lost", g.owner, g.region))
        elif r.owner != g.owner:
            chance = rules.spy_catch_base + rules.spy_catch_per_fort * r.fort
            if rng_ag.random() < chance:
                del s.agents[gid]
                post(s, rules, g.owner, turn, "report", f"O nosso espião em {name} foi descoberto e executado.")
                if r.owner > 0 and r.owner in s.factions:
                    post(s, rules, r.owner, turn, "report", f"Apanhámos um espião de {f.name} em {name}.")
                events.append(("spy_caught", g.owner, g.region, r.owner))

    # 6. construção e recrutamento
    for fid, os_ in sorted(valid.items()):
        f = s.factions[fid]
        for o in os_:
            if o["type"] == "build":
                rid = o["region"]
                if s.regions[rid].owner != fid:
                    continue
                need, err = build_cost(s, rid, o["what"], rules, world)
                if err or any(f.stock[k] < v for k, v in need.items()):
                    continue
                for k, v in need.items():
                    f.stock[k] -= v
                r = s.regions[rid]
                if o["what"] == "fort":
                    r.project = {"kind": "fort", "left": rules.fort_turns}
                elif o["what"] == "upgrade":
                    r.project = {"kind": "upgrade", "left": rules.building_turns[r.level + 1]}
                else:
                    r.project = {"kind": "new", "what": o["what"], "left": rules.building_turns[1]}
            elif o["type"] == "recruit_agent":
                rid, need = o["region"], agent_cost(o["kind"], rules)
                if s.regions[rid].owner != fid or any(f.stock[k] < v for k, v in need.items()):
                    continue
                for k, v in need.items():
                    f.stock[k] -= v
                s.agents[s.next_agent] = Agent(id=s.next_agent, owner=fid, kind=o["kind"], region=rid)
                s.next_agent += 1
            elif o["type"] == "recruit":
                rid, men = o["region"], int(o["men"])
                r = s.regions[rid]
                cost = {k: v * men / 100 for k, v in rules.recruit_cost_per_100.items()}
                if r.owner != fid or any(f.stock[k] < v for k, v in cost.items()):
                    continue
                for k, v in cost.items():
                    f.stock[k] -= v
                r.pop -= men / 1000
                r.order = max(0, r.order - rules.recruit_order_loss)
                own = [a for a in s.armies_in(rid) if a.owner == fid]
                if own:
                    own[0].vet = int(round((own[0].vet * own[0].men) / (own[0].men + men)))
                    own[0].men += men
                else:
                    s.armies[s.next_army] = Army(id=s.next_army, owner=fid, region=rid, men=men)
                    s.next_army += 1
    for rid, r in sorted(s.regions.items()):
        if not r.project or r.plague >= rules.plague_infested:
            continue
        r.project["left"] -= 1
        if r.project["left"] <= 0:
            k = r.project["kind"]
            if k == "fort":
                r.fort += 1
            elif k == "upgrade":
                r.level += 1
            else:
                r.building, r.level = r.project["what"], 1
            r.project = None

    # 7. Praga
    _plague_phase(s, world, rules, purging, events)

    # eliminação: fação sem regiões nem exércitos sai do jogo (pode voltar a entrar, como no Atlantis)
    for fid, f in sorted(s.factions.items()):
        if f.active and not s.regions_of(fid) and not s.armies_of(fid):
            f.active = False
            for gid in [g.id for g in s.agents_of(fid)]:
                del s.agents[gid]
            events.append(("eliminated", fid, f"{f.name} foi eliminada"))

    # 8. visão e rumores (§8): fotografias do que cada fação vê agora; rumores sobre o que não vê
    s.turn += 1
    update_vision(s, world, rules, seen_now)
    make_rumours(s, world, rules, events, turn)
    return s, events


def plague_strength(state: GameState, rules: Rules) -> float:
    """Multiplicador da Praga: 0 quando adormecida; senão a intensidade escolhida pelo GM (§6)."""
    if not state.plague_active:
        return 0.0
    return rules.plague_intensities[state.plague_intensity]


def _plague_phase(s: GameState, world: WorldMap, rules: Rules, purging: list[Army], events: list):
    rng = _rng(world, s, "plague")
    strength = plague_strength(s, rules)
    active = strength > 0

    # purga: funciona sempre, mesmo com a Praga adormecida (é a janela dos jogadores)
    for a in purging:
        if a.id not in s.armies:
            continue
        r = s.regions[a.region]
        r.plague = max(0, r.plague - int(rules.purge_base + rules.purge_per_100_men * a.men / 100))
        a.men = int(a.men * (1 - rules.purge_loss))
        if r.owner == PRAGA and r.plague < rules.plague_lost:
            r.owner, r.order, r.garrison = FREE, 0, 0
            events.append(("purged", a.owner, a.region))

    # recuo em regiões bem governadas (sempre) e crescimento + surtos (só com a Praga ativa)
    for rid, r in sorted(s.regions.items()):
        if r.owner == PRAGA:
            continue
        if r.plague >= rules.plague_contaminated:
            owner = s.factions.get(r.owner)
            if owner is not None and r.order == 3 and not owner.famine and rules.plague_recede:
                r.plague = max(0, r.plague - rules.plague_recede)
                continue
            if active:
                resisted = r.fort >= 1 or r.order == 3
                grow = rules.plague_growth_resisted if resisted else rules.plague_growth
                r.plague = min(100, r.plague + max(1, round(grow * strength)))
        elif active and r.neglect >= rules.plague_neglect_turns and rng.random() < rules.plague_outbreak_chance * strength:
            r.plague = rules.plague_outbreak_amount
            events.append(("outbreak", r.owner, rid))

    if not active:
        return

    # alastramento (a partir de uma fotografia, para não depender da ordem de iteração)
    snap = {rid: (r.owner, r.plague) for rid, r in s.regions.items()}
    for rid in sorted(snap):
        owner, p = snap[rid]
        src = 100 if owner == PRAGA else p
        if src < rules.plague_infested:
            continue
        for n in world.regions[rid].neighbors:
            nr = s.regions[n]
            if nr.owner == PRAGA:
                continue
            if rng.random() < src / 100 * rules.plague_spread_chance * strength:
                nr.plague = min(100, max(nr.plague, 1) + rules.plague_spread_amount)

    # colapso
    for rid, r in sorted(s.regions.items()):
        if r.owner != PRAGA and r.plague >= rules.plague_lost:
            _collapse(s, rid, events)

    # crias da Praga atacam vizinhos
    for rid, r in sorted(s.regions.items()):
        if r.owner != PRAGA or rng.random() >= rules.spawn_chance * strength:
            continue
        targets = [n for n in world.regions[rid].neighbors if s.regions[n].owner != PRAGA]
        if not targets:
            continue
        tgt = targets[int(rng.random() * len(targets))]
        tr = s.regions[tgt]
        defenders = [a for a in s.armies_in(tgt) if a.owner == tr.owner]
        mod = _defense_mod(s, world, tgt, rules, True)
        dpow = sum(_power(a.men, a.vet, mod, rules) for a in defenders) + tr.garrison * mod
        win, _, ld = _fight(rules.spawn_men, dpow, rng, rules) if dpow > 0 else (True, 0, 1)
        for a in defenders:
            a.men = int(a.men * (1 - ld))
            if a.men < 20:
                del s.armies[a.id]
        tr.garrison = int(tr.garrison * (1 - ld))
        if win:
            tr.plague = min(100, tr.plague + rules.spawn_plague_hit)
            events.append(("spawn", tr.owner, tgt))


def _collapse(s: GameState, rid: int, events: list):
    r = s.regions[rid]
    prev = r.owner
    r.owner, r.garrison, r.project, r.plague = PRAGA, 0, None, max(r.plague, 80)
    if r.building:
        r.level -= 1
        if r.level <= 0:
            r.building, r.level = None, 0
    for a in s.armies_in(rid):
        a.men = int(a.men * 0.8)
    events.append(("lost", prev, rid))


# --------------------------------------------------------------------------- ordens do GM
INTENSITY_PT = {"weak": "fraca", "normal": "normal", "strong": "forte"}


def validate_gm(state: GameState, world: WorldMap, rules: Rules, gm_orders: list[dict]) -> tuple[list[dict], list[str]]:
    """Ordens do mestre de jogo (§6.1). Formatos:
      {"type": "plague_state", "value": "active" | "dormant"}
      {"type": "plague_focus", "region": 115}
      {"type": "plague_intensity", "value": "weak" | "normal" | "strong"}
      {"type": "rumor", "text": "...", "factions": [3, 7]}            rumor a fações escolhidas
      {"type": "rumor", "text": "...", "region": 115, "radius": 6}    rumor a quem tem terras perto de uma região
    O GM pode escrever rumores verdadeiros ou falsos; o motor não os verifica.
    """
    accepted, errors = [], []
    for i, o in enumerate(gm_orders or []):
        t, err = o.get("type"), None
        if t == "plague_state":
            if o.get("value") not in ("active", "dormant"):
                err = "estado tem de ser 'active' ou 'dormant'"
        elif t == "plague_focus":
            rid = o.get("region")
            if rid not in state.regions:
                err = "região inexistente"
            elif state.regions[rid].owner == PRAGA:
                err = "a região já está perdida para a Praga"
        elif t == "plague_intensity":
            if o.get("value") not in rules.plague_intensities:
                err = f"intensidade tem de ser uma de {sorted(rules.plague_intensities)}"
        elif t == "rumor":
            text = o.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
                err = "o rumor precisa de texto (até 500 caracteres)"
            elif "factions" in o:
                fs = o["factions"]
                if not isinstance(fs, list) or not fs or any(f not in state.factions or not state.factions[f].active
                                                             for f in fs):
                    err = "lista de fações inválida"
            elif "region" in o:
                if o["region"] not in state.regions:
                    err = "região inexistente"
                elif not isinstance(o.get("radius", 5), int) or not 0 <= o.get("radius", 5) <= 30:
                    err = "raio tem de estar entre 0 e 30"
            else:
                err = "indica 'factions' ou 'region'"
        else:
            err = f"ordem de GM desconhecida '{t}'"
        if err:
            errors.append(f"GM ordem {i} ({t}): {err}")
        else:
            accepted.append(o)
    return accepted, errors


def _apply_gm(s: GameState, world: WorldMap, rules: Rules, gm_orders: list[dict], events: list):
    """Fase 0: as decisões do GM aplicam-se antes de tudo e ficam na crónica do turno."""
    accepted, errors = validate_gm(s, world, rules, gm_orders)
    for e in errors:
        events.append(("gm_rejected", 0, e))
    for o in accepted:
        t = o["type"]
        if t == "plague_state":
            was = s.plague_active
            s.plague_active = o["value"] == "active"
            if s.plague_active != was:
                events.append(("gm", 0, "A Praga desperta." if s.plague_active else "A Praga adormece."))
        elif t == "plague_intensity":
            if o["value"] != s.plague_intensity:
                s.plague_intensity = o["value"]
                events.append(("gm", 0, f"A Praga torna-se {INTENSITY_PT[o['value']]}."))
        elif t == "plague_focus":
            rid = o["region"]
            _collapse(s, rid, events)
            s.regions[rid].plague = 100
            for n in world.regions[rid].neighbors:
                nr = s.regions[n]
                if nr.owner != PRAGA:
                    nr.plague = max(nr.plague, rules.foci_neighbor_plague)
            events.append(("gm", 0, f"Um foco da Praga abre-se em {world.regions[rid].name}."))
            events.append(("focus", 0, rid))
        elif t == "rumor":
            targets = o["factions"] if "factions" in o else factions_near(s, world, o["region"], o.get("radius", 5))
            for fid in targets:
                post(s, rules, fid, s.turn, "gm", o["text"].strip())
            events.append(("gm", 0, f"Rumor enviado a {len(targets)} fação(ões)."))
