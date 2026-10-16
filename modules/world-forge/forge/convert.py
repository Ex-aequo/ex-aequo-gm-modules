"""Mapa do Province-Forge (static-map.json) → world.json que o motor de turnos lê.

O Province-Forge numera as regiões a partir de 0, com as províncias de terra primeiro (0..L-1) e depois o mar,
os lagos e o gelo. No Praga, cada província de terra tem o id `pf + 1` (1..L); o mar fica fora do jogo terrestre
mas dá as ligações por mar (`sea_links`: províncias costeiras que tocam a mesma zona de mar costeira).

Cada posição inicial do Province-Forge é um reino (fação slot + 1), com o nome e a cor que o gerador sugere.
O resto da terra são Terras Livres. A população vem do terreno, do rio, da costa e do tamanho da província.

Uso: python -m forge.convert <pasta do mundo>     (lê static-map.json, escreve world.json ao lado)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

FORMAT = "praga-world/province-forge"
# população de partida (milhares) por terreno, para uma província de área média
TERRAIN_POP = {"plains": 120, "forest": 75, "hills": 80, "mountains": 40, "desert": 25, "marsh": 55,
               "jungle": 60, "tundra": 30}
FREE_COLOR = "#9a9488"


def _jitter(seed: str, rid: int) -> float:
    h = hashlib.sha256(f"{seed}:pop:{rid}".encode()).digest()
    return 0.85 + 0.3 * int.from_bytes(h[:8], "big") / 2 ** 64


def praga_world(static: dict, name: str | None = None) -> dict:
    regions = static["regions"]
    land = [r for r in regions if r["kind"] == "land"]
    if [r["id"] for r in land] != list(range(len(land))):
        raise ValueError("o Province-Forge mudou a numeração: as províncias de terra já não são 0..L-1")
    seed = static["params"]["seed"]
    width = static["world"]["width"]
    mean_area = sum(r["area"] for r in land) / max(1, len(land))

    starts = [s for s in static.get("starts", []) if not s.get("reserved")]
    owner: dict[int, int] = {}
    factions = [{"id": 0, "name": "Terras Livres", "fullName": "Terras Livres", "color": FREE_COLOR}]
    for s in starts:
        fid = s["slot"] + 1
        c = s.get("country") or {}
        short = (c.get("name") or {}).get("pt") or f"Reino {fid}"
        full = (c.get("fullName") or {}).get("pt") or short
        factions.append({"id": fid, "name": short, "fullName": full, "color": c.get("color", "#8a8070"),
                         "capital": s["capital"] + 1})
        for p in s["provinces"]:
            owner[p] = fid

    # ligações por mar: costeiras que tocam a mesma zona de mar
    by_sea: dict[int, set[int]] = {}
    for r in land:
        for n in r["neighbors"]:
            if regions[n]["kind"] == "sea":
                by_sea.setdefault(n, set()).add(r["id"])
    sea_links: dict[int, set[int]] = {r["id"]: set() for r in land}
    for zone, members in by_sea.items():
        if regions[zone].get("seaKind") != "coastal":
            continue
        for a in members:
            sea_links[a] |= members - {a}

    out_regions = []
    for r in land:
        rid = r["id"] + 1
        nm = (r.get("name") or {}).get("pt") or f"Terra {rid}"
        pop = TERRAIN_POP.get(r["terrain"], 50) + (25 if r.get("hasRiver") else 0) + (15 if r["coastal"] else 0)
        pop *= math.sqrt(r["area"] / mean_area) * _jitter(seed, rid)
        land_nb = sorted(n + 1 for n in r["neighbors"] if regions[n]["kind"] == "land")
        out_regions.append({
            "id": rid, "pf": r["id"], "kind": "province", "name": nm, "fullName": nm,
            "owner": owner.get(r["id"], 0), "area": r["area"], "center": r["label"],
            "terrain": r["terrain"], "resource": r.get("resource"), "amount": r.get("amount") or 0,
            "river": bool(r.get("hasRiver")), "coastal": bool(r["coastal"]), "landmass": r["landmass"],
            "neighbors": land_nb, "river_neighbors": sorted(n + 1 for n in r.get("riverNeighbors", [])),
            "sea_links": sorted(n + 1 for n in sea_links[r["id"]] if n + 1 not in land_nb),
            "population": round(pop, 1),
            # compatibilidade com o motor antigo (mundos do Azgaar): não usados quando há "terrain"
            "biome": r["terrain"], "elevation": 0,
        })

    return {
        "format": FORMAT, "name": name or seed, "seed": seed,
        "width": width, "height": static["world"]["height"], "wrapX": bool(static["world"].get("wrapX")),
        "generator": static.get("generator"),
        "factions": factions, "regions": out_regions, "rivers": [], "roads": [], "burgs": [],
        "pragaSeeds": [p + 1 for p in static.get("pragaSeeds", []) if p < len(land)],
    }


def main():
    d = Path(sys.argv[1])
    static = json.loads((d / "static-map.json").read_text())
    name = sys.argv[2] if len(sys.argv) > 2 else None
    w = praga_world(static, name)
    (d / "world.json").write_text(json.dumps(w, ensure_ascii=False, separators=(",", ":")))
    kingdoms = len(w["factions"]) - 1
    owned = sum(1 for r in w["regions"] if r["owner"])
    print(f"world.json: {len(w['regions'])} províncias, {kingdoms} reinos, {owned} com dono "
          f"({owned / len(w['regions']):.0%})")


if __name__ == "__main__":
    main()
