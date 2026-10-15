"""Simulação: 24 fações-bot + entradas tardias + abandonos, N turnos, várias seeds, métricas agregadas.

Uso (a partir de modules/turn-engine):
    python -m sim.run --world ../world-map/web/data/world.json --turns 200 --seeds 5 --out build/sim
Opções:
    --start small|azgaar   arranque pequeno e justo (padrão) ou território do Azgaar
    --set CAMPO=JSON       altera uma regra, ex.: --set 'plague_recede=0'
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import time
from collections import Counter
from pathlib import Path

from praga import DEFAULT, FREE, PRAGA, WorldMap, add_faction, new_game, plague_strength, resolve_turn
from praga.bots import STYLES, bot_orders
from praga.state import land_distances

ABANDON_AT = (25, 40, 60)          # três fações deixam de jogar nestes turnos
ENTRIES = (20, 50, 75)             # turnos em que entra um jogador novo, se houver lugar
MAX_ACTIVE = 25
NEAR = 10                          # "perto da Praga" = capital a ≤10 regiões de um foco


# --------------------------------------------------------------------------- políticas de GM simuladas
# O GM real é uma pessoa. Estas políticas existem só para medir o que acontece com cada estilo de condução.
def gm_never(state, world, rules, total):
    return []


def gm_always(state, world, rules, total):
    """Desperta a Praga no turno 10, com todos os focos sugeridos, e nunca a desliga."""
    if state.turn == 10:
        return [{"type": "plague_state", "value": "active"}] + [{"type": "plague_focus", "region": r} for r in state.foci]
    return []


def gm_pulse(state, world, rules, total, on=30, off=30):
    """Ciclos: ativa 30 turnos, adormece 30. Abre um foco novo em cada despertar."""
    t = state.turn - 10
    if t < 0:
        return []
    phase = t % (on + off)
    if phase == 0:
        cycle = t // (on + off)
        foci = [r for r in state.foci if state.regions[r].owner != PRAGA]
        out = [{"type": "plague_state", "value": "active"}]
        if foci:
            out.append({"type": "plague_focus", "region": foci[cycle % len(foci)]})
        return out
    if phase == on:
        return [{"type": "plague_state", "value": "dormant"}]
    return []


def gm_leader(state, world, rules, total):
    """Anti-domínio: desperta quando uma fação passa 8% do mapa, com um foco junto à periferia dela;
    adormece quando a Praga passa 20% do mapa ou o líder desce abaixo de 6%."""
    sizes = Counter(r.owner for r in state.regions.values() if r.owner > 0)
    leader, size = sizes.most_common(1)[0] if sizes else (None, 0)
    lost = sum(1 for r in state.regions.values() if r.owner == PRAGA) / total
    if not state.plague_active and leader and size / total > 0.08:
        mine = set(state.regions_of(leader))
        dist = land_distances(world, list(mine))
        border = [r for r, d in dist.items() if 2 <= d <= 4 and state.regions[r].owner in (FREE,) and r not in mine]
        out = [{"type": "plague_state", "value": "active"}]
        if border:
            out.append({"type": "plague_focus", "region": sorted(border)[len(border) // 2]})
        return out
    if state.plague_active and (lost > 0.20 or size / total < 0.06):
        return [{"type": "plague_state", "value": "dormant"}]
    return []


GM_POLICIES = {"never": gm_never, "always": gm_always, "pulse": gm_pulse, "leader": gm_leader}


def gini(xs: list[int]) -> float:
    xs = sorted(xs)
    n, total = len(xs), sum(xs)
    if not n or not total:
        return 0.0
    return sum((2 * i - n + 1) * x for i, x in enumerate(xs)) / (n * total)


def simulate(world: WorldMap, rules, start: str, turns: int, rng_seed: str, gm=gm_always) -> dict:
    state = new_game(world, rules, start, rng_seed)
    fids = sorted(state.factions)
    style = {fid: STYLES[i % len(STYLES)] for i, fid in enumerate(fids)}
    abandon = {fids[2]: ABANDON_AT[0], fids[7]: ABANDON_AT[1], fids[12]: ABANDON_AT[2]}
    to_focus = land_distances(world, state.foci)
    start_dist = {fid: to_focus.get(state.armies_of(fid)[0].region, 99) for fid in fids}
    no_iron = [fid for fid in fids if not any(world.regions[r].base["iron"] + state.regions[r].iron_bonus
                                               for r in state.regions_of(fid))]
    next_new, total = 100, len(state.regions)
    history, event_log = [], []

    for _ in range(turns):
        turn = state.turn
        if turn in ENTRIES and sum(f.active for f in state.factions.values()) < MAX_ACTIVE:
            rid = add_faction(state, world, rules, next_new, f"Recém-chegados {next_new - 99}")
            if rid:
                style[next_new] = "builder"
                event_log.append((turn, "entry", next_new, rid))
                next_new += 1
        orders = {fid: bot_orders(state, world, rules, fid, style[fid])
                  for fid, f in sorted(state.factions.items())
                  if f.active and not (fid in abandon and turn >= abandon[fid])}
        state, events = resolve_turn(state, world, rules, orders, gm(state, world, rules, total))
        kinds = Counter(e[0] for e in events)
        event_log += [(turn, *e) for e in events if e[0] in ("dissolve", "regency", "eliminated", "gm")]
        owners = Counter(r.owner for r in state.regions.values())
        sizes = [owners.get(f.id, 0) for f in state.factions.values() if f.active]
        history.append({
            "turn": turn,
            "lost": owners.get(PRAGA, 0) / total,
            "contaminated": sum(1 for r in state.regions.values() if r.owner != PRAGA and r.plague > 0) / total,
            "free": owners.get(FREE, 0) / total,
            "active": len(sizes), "largest": max(sizes, default=0), "gini": round(gini(sizes), 3),
            "men": sum(a.men for a in state.armies.values() if a.owner > 0),
            "strength": plague_strength(state, rules), "active_plague": state.plague_active,
            "conquests": kinds["conquest"], "lost_regions": kinds["lost"], "outbreaks": kinds["outbreak"],
            "rejected": sum(e[2] for e in events if e[0] == "rejected"),
        })

    played = [f for f in fids if f not in abandon]
    survived = {f: len(state.regions_of(f)) > 0 for f in played}
    return {
        "rng_seed": rng_seed, "digest": state.digest(), "foci": state.foci, "no_iron_at_start": no_iron,
        "history": history, "events": event_log,
        "near": [survived[f] for f in played if start_dist[f] <= NEAR],
        "far": [survived[f] for f in played if start_dist[f] > NEAR],
        "final": {fid: {"name": f.name, "style": style.get(fid), "active": f.active,
                        "regions": len(state.regions_of(fid)), "start_dist": start_dist.get(fid)}
                  for fid, f in sorted(state.factions.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", required=True)
    ap.add_argument("--turns", type=int, default=200)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--start", choices=("small", "azgaar"), default="small")
    ap.add_argument("--out", default="build/sim")
    ap.add_argument("--set", action="append", default=[], metavar="CAMPO=JSON")
    ap.add_argument("--gm", choices=sorted(GM_POLICIES), default="always", help="política de GM simulada")
    args = ap.parse_args()

    rules = DEFAULT
    for kv in args.set:
        key, val = kv.split("=", 1)
        if not hasattr(rules, key):
            ap.error(f"regra desconhecida: {key}")
        if key in {f.name for f in dataclasses.fields(rules)}:
            rules = dataclasses.replace(rules, **{key: json.loads(val)})
        else:  # atributos de classe (dicts) não são campos do dataclass
            object.__setattr__(rules, key, json.loads(val))
    world = WorldMap.load(args.world, rules)

    t0 = time.perf_counter()
    runs = [simulate(world, rules, args.start, args.turns, f"s{i}", GM_POLICIES[args.gm]) for i in range(args.seeds)]
    elapsed = time.perf_counter() - t0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "runs.json").write_text(json.dumps({"args": vars(args), "runs": runs}, ensure_ascii=False))

    print(f"{args.seeds} seeds × {args.turns} turnos em {elapsed:.1f}s · focos {runs[0]['foci']}")
    print(f"fações sem ferro no arranque: {runs[0]['no_iron_at_start'] or 'nenhuma'}")
    print("turno   perdido (média, mín–máx)   contaminado   maior fação   gini   ativas")
    for t in (10, 25, 50, 100, 150, 200):
        if t > args.turns:
            continue
        hs = [r["history"][t - 1] for r in runs]
        lost = [h["lost"] for h in hs]
        print(f"{t:5d}   {statistics.mean(lost):6.1%} ({min(lost):.0%}–{max(lost):.0%})"
              f"        {statistics.mean(h['contaminated'] for h in hs):6.1%}"
              f"       {statistics.mean(h['largest'] for h in hs):5.1f}"
              f"     {statistics.mean(h['gini'] for h in hs):.2f}   {statistics.mean(h['active'] for h in hs):5.1f}")
    near = [x for r in runs for x in r["near"]]
    far = [x for r in runs for x in r["far"]]
    print(f"sobreviventes ao turno {args.turns}: perto da Praga (≤{NEAR}) {sum(near)}/{len(near)}"
          f" = {sum(near) / max(1, len(near)):.0%} · longe {sum(far)}/{len(far)} = {sum(far) / max(1, len(far)):.0%}")
    minlost = min(min(h["lost"] for h in r["history"][50:]) for r in runs) if args.turns > 50 else None
    print(f"mínimo da Praga depois do turno 50: {minlost:.1%}" if minlost is not None else "")
    on = [statistics.mean(h["active_plague"] for h in r["history"]) for r in runs]
    print(f"Praga ativa em {statistics.mean(on):.0%} dos turnos · crónica do GM (seed 0):",
          [(e[0], e[3]) for e in runs[0]["events"] if e[1] == "gm"][:8])


if __name__ == "__main__":
    main()
