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
        # mundos com reinos próprios (tools/partition.py) trazem a capital de cada fação; os antigos usam os burgos
        for f in world["factions"]:
            if f.get("capital"):
                self.capitals[f["id"]] = f["capital"]
        self.has_kingdoms = bool(self.capitals)
        for b in world["burgs"]:
            if b["capital"] and b["region"]:
                owner = raw[b["region"]]["owner"]
                if owner and not self.has_kingdoms:
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
    iron_bonus: int = 0             # "veio menor" dado no arranque a capitais sem ferro por perto (§3.1)


@dataclass
class Army:
    id: int
    owner: int
    region: int
    men: int
    vet: int = 0


@dataclass
class Agent:
    """Batedor ("scout") ou espião ("spy"): não combate; serve para ver (§8)."""
    id: int
    owner: int
    kind: str
    region: int


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
    controller: str = "player"      # "player" ou "bot" (reino-guardião sem jogador, §7, v0.6)

    def posture(self, other: int) -> str:
        return self.postures.get(str(other), "neutral")


@dataclass
class GameState:
    turn: int
    regions: dict[int, Region]
    armies: dict[int, Army]
    factions: dict[int, Faction]
    next_army: int = 1
    rng_seed: str = ""              # varia o acaso entre corridas sem mudar o mapa
    foci: list = field(default_factory=list)   # sugestões de focos para o GM (não ativos no arranque)
    plague_active: bool = False     # a Praga começa adormecida; só o GM a desperta (§6.1)
    plague_intensity: str = "normal"
    # §8 visão: o que cada fação vê agora, o que já viu (fotografias com o turno) e a sua caixa de mensagens
    agents: dict[int, Agent] = field(default_factory=dict)
    next_agent: int = 1
    vision: dict[int, dict[int, int]] = field(default_factory=dict)     # fação -> região -> nível (2..4)
    known: dict[int, dict[int, dict]] = field(default_factory=dict)     # fação -> região -> fotografia
    inbox: dict[int, list[dict]] = field(default_factory=dict)          # fação -> [{turn, kind, text}]

    # ---------------------------------------------------------------- serialização determinística
    def to_dict(self) -> dict:
        return {
            "turn": self.turn, "next_army": self.next_army, "rng_seed": self.rng_seed, "foci": self.foci,
            "plague_active": self.plague_active, "plague_intensity": self.plague_intensity,
            "regions": {str(k): asdict(v) for k, v in sorted(self.regions.items())},
            "armies": {str(k): asdict(v) for k, v in sorted(self.armies.items())},
            "factions": {str(k): asdict(v) for k, v in sorted(self.factions.items())},
            "agents": {str(k): asdict(v) for k, v in sorted(self.agents.items())},
            "next_agent": self.next_agent,
            "vision": {str(f): {str(r): lvl for r, lvl in sorted(v.items())} for f, v in sorted(self.vision.items())},
            "known": {str(f): {str(r): snap for r, snap in sorted(v.items())} for f, v in sorted(self.known.items())},
            "inbox": {str(f): v for f, v in sorted(self.inbox.items())},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        return cls(
            turn=d["turn"], next_army=d["next_army"], rng_seed=d.get("rng_seed", ""), foci=list(d.get("foci", [])),
            plague_active=d.get("plague_active", False), plague_intensity=d.get("plague_intensity", "normal"),
            regions={int(k): Region(**v) for k, v in d["regions"].items()},
            armies={int(k): Army(**v) for k, v in d["armies"].items()},
            factions={int(k): Faction(**v) for k, v in d["factions"].items()},
            agents={int(k): Agent(**v) for k, v in d.get("agents", {}).items()},
            next_agent=d.get("next_agent", 1),
            vision={int(f): {int(r): lvl for r, lvl in v.items()} for f, v in d.get("vision", {}).items()},
            known={int(f): {int(r): snap for r, snap in v.items()} for f, v in d.get("known", {}).items()},
            inbox={int(f): list(v) for f, v in d.get("inbox", {}).items()},
        )

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:16]

    # ---------------------------------------------------------------- consultas
    def regions_of(self, fid: int) -> list[int]:
        return [rid for rid, r in sorted(self.regions.items()) if r.owner == fid]

    def armies_in(self, rid: int) -> list[Army]:
        return [a for a in self.armies.values() if a.region == rid]

    def armies_of(self, fid: int) -> list[Army]:
        return [a for _, a in sorted(self.armies.items()) if a.owner == fid]

    def agents_of(self, fid: int) -> list[Agent]:
        return [a for _, a in sorted(self.agents.items()) if a.owner == fid]

    def command_points(self, fid: int, rules: Rules) -> int:
        n = len(self.regions_of(fid))
        return int(rules.pc_base + rules.pc_per_sqrt_region * math.sqrt(n)) if n else 0


def land_distances(world: WorldMap, sources) -> dict[int, int]:
    """Distância em regiões (por terra) desde o conjunto de origens. Regiões inalcançáveis ficam de fora."""
    from collections import deque
    dist = {r: 0 for r in sources}
    q = deque(sources)
    while q:
        u = q.popleft()
        for n in world.regions[u].neighbors:
            if n not in dist:
                dist[n] = dist[u] + 1
                q.append(n)
    return dist


def place_foci(world: WorldMap, capitals: list[int], rules: Rules) -> list[int]:
    """Sugestões de focos da Praga para o GM (§6): entre foci_min_dist e foci_max_dist da capital mais próxima
    (longe o suficiente para não matar ninguém à nascença, perto o suficiente para haver rumores), espalhados uns dos
    outros, e sempre no mesmo continente que uma capital (um foco numa ilha vazia nunca faria nada)."""
    if not capitals:
        return []
    reach = land_distances(world, capitals)
    cap_xy = [world.regions[c].center for c in capitals]
    dcap = {r: min(math.dist(world.regions[r].center, c) for c in cap_xy) for r in reach}
    band = [r for r in sorted(reach) if rules.foci_min_dist <= dcap[r] <= rules.foci_max_dist]
    if len(band) < rules.plague_foci:                       # mapa pequeno ou muito cheio: alarga para fora
        band = [r for r in sorted(reach) if dcap[r] >= rules.foci_min_dist] or sorted(reach, key=lambda r: -dcap[r])
    chosen: list[int] = []
    while len(chosen) < rules.plague_foci and len(chosen) < len(band):
        def score(r):
            apart = min((math.dist(world.regions[r].center, world.regions[c].center) for c in chosen), default=1e9)
            return (apart, dcap[r], -r)
        chosen.append(max((r for r in band if r not in chosen), key=score))
    return chosen


def new_game(world: WorldMap, rules: Rules, start: str | None = None, rng_seed: str = "",
             players: set[int] | None = None) -> GameState:
    """start='world': cada reino começa com o território do world.json — num mundo com reinos próprios, todos têm o
    mesmo número de províncias (ferro garantido como em 'small'); o resto são Terras Livres guarnecidas.
    start='azgaar': o mesmo, num mundo antigo com o território do Azgaar (tamanhos muito desiguais).
    start='small': capital + 2 regiões (com ferro garantido, §3.1); o resto são Terras Livres guarnecidas.
    start=None: 'world' se o mundo tiver reinos próprios, senão 'small'.
    players: fações com jogador; as outras começam como reinos-guardiões (bots, §7). None = todas com jogador.
    A Praga começa adormecida; os focos calculados são só sugestões para o GM (§6.1)."""
    if start is None:
        start = "world" if world.has_kingdoms else "small"
    if start not in ("small", "world", "azgaar"):
        raise ValueError(f"início desconhecido: {start}")
    regions: dict[int, Region] = {}
    for rid, info in world.regions.items():
        pop = world.start_pop[rid]
        owner = FREE if start == "small" else world.start_owner[rid]
        regions[rid] = Region(owner=owner, pop=pop,
                              garrison=int(rules.neutral_garrison_base + rules.neutral_garrison_per_kpop * pop)
                              if owner == FREE else 0)

    capitals = {fid: world.capitals[fid] for fid in sorted(world.factions) if fid != FREE and fid in world.capitals}
    factions: dict[int, Faction] = {}
    armies: dict[int, Army] = {}
    next_army = 1
    for fid, cap in capitals.items():
        if start == "small":
            if regions[cap].owner != FREE:      # capital já apanhada por um vizinho: usa a vizinha livre mais rica
                cap = max((n for n in world.regions[cap].neighbors if regions[n].owner == FREE),
                          key=lambda n: (regions[n].pop, -n), default=cap)
                capitals[fid] = cap
            mine = _start_regions(world, regions, cap)
            for rid in mine:
                regions[rid].owner, regions[rid].garrison = fid, 0
            if not any(world.regions[r].base["iron"] for r in mine):
                regions[cap].iron_bonus = 2
        elif start == "world":
            mine = [r for r in regions if regions[r].owner == fid]
            if not any(world.regions[r].base["iron"] for r in mine):
                regions[cap].iron_bonus = 2
        factions[fid] = Faction(id=fid, name=world.factions[fid]["name"], stock=dict(rules.start_treasury),
                                controller="player" if players is None or fid in players else "bot")
        armies[next_army] = Army(id=next_army, owner=fid, region=cap, men=rules.start_army)
        next_army += 1

    # A Praga começa adormecida e sem focos: o GM decide quando e onde ela desperta (§6.1).
    foci = place_foci(world, list(capitals.values()), rules)
    state = GameState(turn=1, regions=regions, armies=armies, factions=factions, next_army=next_army,
                      rng_seed=rng_seed, foci=foci)
    from .vision import update_vision
    update_vision(state, world, rules)
    return state


def _start_regions(world: WorldMap, regions: dict[int, Region], cap: int) -> list[int]:
    """Capital + 2 regiões livres. Prefere vizinhas com ferro; se não houver, um caminho de 2 passos até ferro."""
    free = lambda r: regions[r].owner == FREE
    nbs = [n for n in world.regions[cap].neighbors if free(n)]
    if not free(cap):
        return [cap] if regions[cap].owner == FREE else []
    iron = [n for n in nbs if world.regions[n].base["iron"]]
    if world.regions[cap].base["iron"] or iron:
        pick = (iron[:1] + [n for n in nbs if n not in iron[:1]])[:2]
        return [cap, *pick]
    for n in nbs:
        far = [m for m in world.regions[n].neighbors if free(m) and m != cap and world.regions[m].base["iron"]]
        if far:
            return [cap, n, far[0]]
    return [cap, *nbs[:2]]
