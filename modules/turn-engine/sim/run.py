"""Simulação: 24 fações-bot + entradas tardias + abandonos, N turnos, métricas por turno.

Uso (a partir de modules/turn-engine):
    python -m sim.run --world ../world-map/web/data/world.json --turns 100 --out build/sim
Opções:
    --start small|azgaar   arranque pequeno e igual (padrão) ou território do Azgaar
    --no-cap               Praga sem equilíbrio dinâmico (decisão em aberto §6)
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

ABANDON_AT = (25, 40, 60)          # três fações deixam de jogar nestes turnos
ENTRIES = (20, 50, 75)             # turnos em que entra um jogador novo, se houver lugar
MAX_ACTIVE = 25


def gini(xs: list[int]) -> float:
    xs = sorted(xs)
    n, total = len(xs), sum(xs)
    if not n or not total:
        return 0.0
    return sum((2 * i - n + 1) * x for i, x in enumerate(xs)) / (n * total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", required=True)
    ap.add_argument("--turns", type=int, default=100)
    ap.add_argument("--start", choices=("small", "azgaar"), default="small")
    ap.add_argument("--no-cap", action="store_true")
    ap.add_argument("--out", default="build/sim")
    ap.add_argument("--set", action="append", default=[], metavar="CAMPO=JSON",
                    help='altera uma regra, ex.: --set \'recruit_cost_per_100={"gold": 15}\'')
    args = ap.parse_args()

    rules = dataclasses.replace(DEFAULT, plague_target=None) if args.no_cap else DEFAULT
    for kv in args.set:
        key, val = kv.split("=", 1)
        if not hasattr(rules, key):
            ap.error(f"regra desconhecida: {key}")
        if key in {f.name for f in dataclasses.fields(rules)}:
            rules = dataclasses.replace(rules, **{key: json.loads(val)})
        else:  # atributos de classe (dicts) não são campos do dataclass
            object.__setattr__(rules, key, json.loads(val))
    world = WorldMap.load(args.world, rules)
    state = new_game(world, rules, args.start)

    fids = sorted(state.factions)
    style = {fid: STYLES[i % len(STYLES)] for i, fid in enumerate(fids)}
    # quem abandona: uma fação de cada estilo, escolhidas de forma fixa
    abandon = {fids[2]: ABANDON_AT[0], fids[7]: ABANDON_AT[1], fids[12]: ABANDON_AT[2]}
    next_new = 100
    total = len(state.regions)
    history, event_log = [], []
    t0 = time.perf_counter()

    for _ in range(args.turns):
        turn = state.turn
        active = [f for f in state.factions.values() if f.active]
        if turn in ENTRIES and len(active) < MAX_ACTIVE:
            rid = add_faction(state, world, rules, next_new, f"Recém-chegados {next_new - 99}")
            if rid:
                style[next_new] = "builder"
                event_log.append((turn, "entry", next_new, rid))
                next_new += 1

        orders = {}
        for fid, f in sorted(state.factions.items()):
            if not f.active or (fid in abandon and turn >= abandon[fid]):
                continue
            orders[fid] = bot_orders(state, world, rules, fid, style[fid])

        state, events = resolve_turn(state, world, rules, orders)
        kinds = Counter(e[0] for e in events)
        for e in events:
            if e[0] in ("dissolve", "regency", "eliminated"):
                event_log.append((turn, *e))

        owners = Counter(r.owner for r in state.regions.values())
        active = [f for f in state.factions.values() if f.active]
        sizes = [owners.get(f.id, 0) for f in active]
        history.append({
            "turn": turn,
            "lost": owners.get(PRAGA, 0) / total,
            "contaminated": sum(1 for r in state.regions.values() if r.owner != PRAGA and r.plague > 0) / total,
            "free": owners.get(FREE, 0) / total,
            "active": len(active),
            "largest": max(sizes, default=0),
            "smallest": min(sizes, default=0),
            "median": statistics.median(sizes) if sizes else 0,
            "gini": round(gini(sizes), 3),
            "men": sum(a.men for a in state.armies.values() if a.owner > 0),
            "strength": plague_strength(state, rules),
            "conquests": kinds["conquest"], "lost_regions": kinds["lost"], "outbreaks": kinds["outbreak"],
            "recede": kinds["recede"], "spawns": kinds["spawn"], "rejected": sum(e[2] for e in events if e[0] == "rejected"),
        })

    elapsed = time.perf_counter() - t0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    final = {fid: {"name": f.name, "style": style.get(fid), "active": f.active, "regions": len(state.regions_of(fid)),
                   "men": sum(a.men for a in state.armies_of(fid)), "stock": {k: round(v) for k, v in f.stock.items()},
                   "buildings": Counter(f"{state.regions[r].building}:{state.regions[r].level}"
                                        for r in state.regions_of(fid) if state.regions[r].building)}
             for fid, f in sorted(state.factions.items())}
    (out / "metrics.json").write_text(json.dumps({"args": vars(args), "history": history, "events": event_log,
                                                  "final": final, "digest": state.digest(),
                                                  "seconds": round(elapsed, 2)}, ensure_ascii=False, indent=1))

    print(f"{args.turns} turnos em {elapsed:.1f}s ({elapsed / args.turns * 1000:.0f} ms/turno) · digest {state.digest()}")
    print("turno  perdido  contamin.  livre  ativas  maior  menor  mediana  gini  homens")
    for h in history:
        if h["turn"] % 10 == 0 or h["turn"] == 1:
            print(f"{h['turn']:5d}  {h['lost']:7.1%}  {h['contaminated']:9.1%}  {h['free']:5.1%}  {h['active']:6d}"
                  f"  {h['largest']:5d}  {h['smallest']:5d}  {h['median']:7.1f}  {h['gini']:.2f}  {h['men']:6d}")
    for e in event_log:
        print("  ", e)
    print("Rejeitadas:", sum(h["rejected"] for h in history))
    top = sorted(final.items(), key=lambda kv: -kv[1]["regions"])[:5]
    for fid, f in top:
        print(f"  {f['name']:<22} {f['style']:<13} {f['regions']:4d} regiões  {f['men']:5d} homens  {dict(f['buildings'])}")


if __name__ == "__main__":
    main()
