"""Estado do jogo: mapa estático (do world.json do módulo world-map) + estado dinâmico serializável."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .rules import (BIOME_YIELD, DESERTS, FREE, HILL_ELEVATION, MOUNTAIN_ELEVATION, PRAGA, RESOURCES, ROUGH_BIOMES,
                    FOREST_BIOMES, Rules)


def stable_hash(*parts) -> float:
    """Número em [0,1) determinístico a partir de qualquer conjunto de valores."""
    h = hashlib.sha256(":".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


# --------------------------------------------------------------------------- mapa (não muda durante o jogo)
@dataclass(frozen=True)
class RegionInfo:
    id: int
    name: str
    kind: str
    biome: str
    elevation: int
    coastal: bool
    neighbors: tuple[int, ...]
    sea_links: tuple[int, ...]
    center: tuple[float, float]
    base: dict            # produção base por recurso (sem edifícios)
    rough: bool           # custa 2 passos a entrar
    gold_vein: bool
    allowed_buildings: tuple[str, ...]


class WorldMap:
    def __init__(self, world: dict, rules: Rules):
        self.name = world["name"]
        self.seed = world["seed"]
        self.factions = {f["id"]: f for f in world["factions"]}
        raw = {r["id"]: r for r in world["regions"]}
        self.start_owner = {rid: r["owner"] for rid, r in raw.items()}
        self.start_pop = {rid: float(r["population"]) for rid, r in raw.items()}
        self.capitals = {}
        for b in world["burgs"]:
            if b["capital"] and b["region"]:
                owner = raw[b["region"]]["owner"]
                if owner:
                    self.capitals.setdefault(owner, b["region"])

        # ligações por mar: regiões costeiras próximas que não são vizinhas por terra
        coastal = [r for r in raw.values() if r["coastal"]]
        sea = {r["id"]: [] for r in coastal}
        for i, a in enumerate(coastal):
            for b in coastal[i + 1:]:
                if b["id"] in a["neighbors"]:
                    continue
                d = math.dist(a["center"], b["center"])
                if d < 70:
                    sea[a["id"]].append(b["id"])
                    sea[b["id"]].append(a["id"])

        self.regions: dict[int, RegionInfo] = {}
        for rid, r in raw.items():
            food, wood = BIOME_YIELD.get(r["biome"], (1, 0))
            if r["coastal"]:
                food += 1
            elev = r["elevation"]
            iron = 4 if elev >= MOUNTAIN_ELEVATION else 2 if elev >= HILL_ELEVATION else 0
            if r["biome"] in DESERTS:
                iron = max(iron, 2)
            vein = elev >= HILL_ELEVATION and stable_hash(self.seed, "vein", rid) < rules.gold_vein_share
            allowed = []
            if food >= 2:
                allowed.append("farm")
            if r["biome"] in FOREST_BIOMES:
                allowed.append("sawmill")
            if iron > 0:
                allowed.append("iron_mine")
            if vein:
                allowed.append("gold_mine")
            self.regions[rid] = RegionInfo(
                id=rid, name=r["name"], kind=r["kind"], biome=r["biome"], elevation=elev, coastal=r["coastal"],
                neighbors=tuple(sorted(r["neighbors"])), sea_links=tuple(sorted(sea.get(rid, []))),
                center=tuple(r["center"]), base={"food": food, "wood": wood, "iron": iron, "gold": 3 if vein else 0},
                rough=r["biome"] in ROUGH_BIOMES or elev >= MOUNTAIN_ELEVATION, gold_vein=vein,
                allowed_buildings=tuple(allowed))

    @classmethod
    def load(cls, path: str | Path, rules: Rules) -> "WorldMap":
        return cls(json.loads(Path(path).read_text()), rules)


# --------------------------------------------------------------------------- estado dinâmico
@dataclass
class Region:
    owner: int
    pop: float                      # milhares de habitantes
    order: int = 2                  # ordem pública 0..3
    fort: int = 0
    building: str | None = None
    level: int = 0
    project: dict | None = None     # obra em curso {"kind","target","left"}
    plague: int = 0
    garrison: int = 0               # guarnição neutra (só Terras Livres)
    neglect: int = 0                # turnos seguidos com ordem 0 ou fome


@dataclass
class Army:
    id: int
    owner: int
    region: int
    men: int
    vet: int = 0


@dataclass
class Faction:
    id: int
    name: str
    stock: dict
    postures: dict = field(default_factory=dict)   # outra fação -> "ally" | "neutral" | "hostile"
    active: bool = True
    joined: int = 1
    protected_until: int = 0
    last_orders: int = 0
    famine: bool = False

    def posture(self, other: int) -> str:
        return self.postures.get(str(other), "neutral")


@dataclass
class GameState:
    turn: int
    regions: dict[int, Region]
    armies: dict[int, Army]
    factions: dict[int, Faction]
    next_army: int = 1

    # ---------------------------------------------------------------- serialização determinística
    def to_dict(self) -> dict:
        return {
            "turn": self.turn, "next_army": self.next_army,
            "regions": {str(k): asdict(v) for k, v in sorted(self.regions.items())},
            "armies": {str(k): asdict(v) for k, v in sorted(self.armies.items())},
            "factions": {str(k): asdict(v) for k, v in sorted(self.factions.items())},
        }

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:16]

    # ---------------------------------------------------------------- consultas
    def regions_of(self, fid: int) -> list[int]:
        return [rid for rid, r in sorted(self.regions.items()) if r.owner == fid]

    def armies_in(self, rid: int) -> list[Army]:
        return [a for a in self.armies.values() if a.region == rid]

    def armies_of(self, fid: int) -> list[Army]:
        return [a for _, a in sorted(self.armies.items()) if a.owner == fid]

    def command_points(self, fid: int, rules: Rules) -> int:
        n = len(self.regions_of(fid))
        return int(rules.pc_base + rules.pc_per_sqrt_region * math.sqrt(n)) if n else 0


def new_game(world: WorldMap, rules: Rules, start: str = "small") -> GameState:
    """start='azgaar': cada fação começa com o território do Azgaar (tamanhos muito desiguais).
    start='small': cada fação começa com a capital e as regiões vizinhas; o resto são Terras Livres guarnecidas."""
    regions: dict[int, Region] = {}
    for rid, info in world.regions.items():
        pop = world.start_pop[rid]
        owner = world.start_owner[rid]
        if info.kind == "wild":
            regions[rid] = Region(owner=PRAGA, pop=pop * 0.3, order=0, plague=100)
            continue
        if start == "small":
            owner = FREE
        regions[rid] = Region(owner=owner, pop=pop,
                              garrison=int(rules.neutral_garrison_base + rules.neutral_garrison_per_kpop * pop)
                              if owner == FREE else 0)

    factions: dict[int, Faction] = {}
    armies: dict[int, Army] = {}
    next_army = 1
    for fid, f in sorted(world.factions.items()):
        if fid == FREE:
            continue
        cap = world.capitals.get(fid)
        if cap is None:
            continue
        if start == "small":
            for rid in (cap, *world.regions[cap].neighbors[:2]):
                if regions[rid].owner == FREE:
                    regions[rid].owner = fid
                    regions[rid].garrison = 0
        factions[fid] = Faction(id=fid, name=f["name"], stock=dict(rules.start_treasury))
        armies[next_army] = Army(id=next_army, owner=fid, region=cap, men=rules.start_army)
        next_army += 1

    # Praga inicial: os Ermos contaminam os vizinhos
    for rid, r in regions.items():
        if r.owner == PRAGA:
            for n in world.regions[rid].neighbors:
                if regions[n].owner != PRAGA:
                    regions[n].plague = max(regions[n].plague, 45)
    return GameState(turn=1, regions=regions, armies=armies, factions=factions, next_army=next_army)
