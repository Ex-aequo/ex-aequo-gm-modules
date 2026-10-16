"""Constantes das regras núcleo (docs/regras-nucleo.md, v0.5).

Todos os números são valores iniciais, a calibrar na simulação. Cada um aponta para a secção do documento.
"""
from dataclasses import dataclass, field

PRAGA = -1          # dono das regiões perdidas para a Praga
FREE = 0            # Terras Livres (sem dono)
RESOURCES = ("gold", "food", "wood", "iron")


@dataclass(frozen=True)
class Rules:
    # §4 pontos de comando
    pc_base: int = 4
    pc_per_sqrt_region: float = 2.0
    move_steps: int = 2                  # regiões por Mover; terreno difícil custa 2
    order_cost = {"move": 1, "attack": 1, "garrison": 0, "purge": 1, "build": 1, "recruit": 1, "posture": 0,
                  "recruit_agent": 1, "agent_move": 1}

    # §3.1 economia
    gold_base: float = 1.0
    gold_per_kpop: float = 0.12          # ouro por mil habitantes
    army_food_per_100: float = 1.0
    army_gold_per_100: float = 1.0
    famine_army_loss: float = 0.10
    bankrupt_army_loss: float = 0.05
    pop_growth: float = 0.01
    order_production = (0.0, 0.5, 0.85, 1.0)   # multiplicador por ordem pública 0..3

    # §3.2 edifícios de produção
    building_mult = (1.0, 1.5, 2.0, 2.5)
    building_cost = {1: {"wood": 20}, 2: {"wood": 40, "iron": 20}, 3: {"wood": 80, "iron": 40, "gold": 40}}
    building_turns = {1: 1, 2: 2, 3: 3}
    building_upkeep = (0, 2, 5, 10)
    fort_cost = {"wood": 15, "iron": 10}
    fort_turns: int = 2
    gold_vein_share: float = 0.10        # fração das regiões de montanha com veio de ouro

    # recrutamento
    recruit_max: int = 200
    recruit_cost_per_100 = {"gold": 10, "iron": 10}
    recruit_order_loss: int = 1

    # combate
    vet_bonus: float = 0.25
    fort_bonus: float = 0.25
    mountain_bonus: float = 0.30
    forest_bonus: float = 0.15
    garrison_bonus: float = 0.10
    combat_noise: float = 0.15
    neutral_garrison_base: int = 60
    neutral_garrison_per_kpop: float = 0.8   # mediana ~140 homens; calibrado na simulação
    conquest_order: int = 0

    # §6 Praga
    plague_contaminated: int = 1
    plague_infested: int = 40
    plague_lost: int = 80
    plague_growth: int = 8
    plague_growth_resisted: int = 4
    plague_spread_chance: float = 0.25   # × intensidade/100 × força
    plague_spread_amount: int = 15
    plague_outbreak_chance: float = 0.15
    plague_outbreak_amount: int = 20
    plague_neglect_turns: int = 2
    purge_base: int = 10
    purge_per_100_men: float = 1.0
    purge_loss: float = 0.05
    contaminated_food_mult: float = 0.75
    infested_pop_loss: float = 0.05
    spawn_chance: float = 0.05
    spawn_men: int = 150
    spawn_plague_hit: int = 30
    # recuo em regiões bem governadas (decisão 2B, v0.3) — funciona mesmo com a Praga adormecida
    plague_recede: int = 3               # por turno, com ordem pública 3 e sem fome
    # sugestões de focos para o GM (decisão 1B): longe das capitais e uns dos outros
    plague_foci: int = 6
    # v0.6: distâncias em unidades do mundo (o mundo tem sempre 1920 × 1080), não em regiões — assim não dependem
    # do tamanho das províncias
    foci_min_dist: float = 200.0         # distância mínima à capital mais próxima
    foci_max_dist: float = 420.0         # e máxima: dentro do alcance dos rumores, para alguém ouvir falar do foco
    foci_neighbor_plague: int = 30
    # v0.4: a Praga é um evento do GM (§6.1). Intensidade multiplica crescimento, alastramento, surtos e crias.
    plague_intensities = {"weak": 0.5, "normal": 1.0, "strong": 1.5}

    # §8 visão, batedores e espiões (v0.5)
    scout_cost = {"gold": 5, "iron": 1}
    spy_cost = {"gold": 40}
    scout_upkeep: float = 1.0            # ouro por turno
    spy_upkeep: float = 3.0
    scout_steps: int = 2                 # regiões por turno; terreno difícil custa 2; só por terra
    spy_steps: int = 1
    spy_catch_base: float = 0.10         # por turno, numa região que não é tua
    spy_catch_per_fort: float = 0.10     # por nível de fortificação
    rumour_distance: float = 450.0       # até onde chegam rumores da Praga (da região tua mais próxima)
    rumour_near: float = 150.0           # "perto das tuas fronteiras"
    rumour_mid: float = 300.0            # "a alguns dias de marcha"; mais longe: "em terras distantes"
    inbox_keep: int = 40                 # mensagens guardadas por fação (rumores e relatórios)

    # §7 entrada e abandono
    protection_turns: int = 5
    regency_after: int = 3               # turnos sem ordens até à Regência
    # dissolve_after: turnos sem ordens até o reino passar a reino-guardião (bot), disponível para quem chegar (v0.6)
    dissolve_after: int = 10
    new_player_treasury = {"gold": 120, "food": 60, "wood": 60, "iron": 40}

    # arranque
    start_treasury = {"gold": 80, "food": 50, "wood": 40, "iron": 30}
    start_army: int = 300


DEFAULT = Rules()

# Produção base por bioma (Azgaar) -> (comida, madeira)
BIOME_YIELD = {
    "Marine": (0, 0), "Hot desert": (0, 0), "Cold desert": (1, 0), "Savanna": (5, 1), "Grassland": (6, 0),
    "Tropical seasonal forest": (4, 3), "Temperate deciduous forest": (3, 4), "Tropical rainforest": (2, 5),
    "Temperate rainforest": (2, 5), "Taiga": (1, 4), "Tundra": (1, 0), "Glacier": (0, 0), "Wetland": (3, 2),
}
FOREST_BIOMES = {"Tropical seasonal forest", "Temperate deciduous forest", "Tropical rainforest",
                 "Temperate rainforest", "Taiga"}
ROUGH_BIOMES = FOREST_BIOMES | {"Wetland"}
DESERTS = {"Hot desert", "Cold desert"}
MOUNTAIN_ELEVATION = 45
HILL_ELEVATION = 35

BUILDINGS = {"farm": "food", "sawmill": "wood", "iron_mine": "iron", "gold_mine": "gold"}

# Mundos do Province-Forge (decisão de 2026-10-16): terreno de jogo em vez de bioma do Azgaar.
# (comida, madeira, ferro) base por terreno
TERRAIN_YIELD = {
    "plains": (6, 0, 0), "forest": (3, 4, 0), "hills": (3, 1, 2), "mountains": (1, 1, 4),
    "desert": (0, 0, 2), "marsh": (3, 2, 0), "jungle": (2, 5, 0), "tundra": (1, 1, 0),
}
ROUGH_TERRAINS = {"forest", "jungle", "marsh", "mountains"}
FOREST_TERRAINS = {"forest", "jungle"}
# recurso principal da província (quantidade 1–3): bónus na produção correspondente.
# pedra: fortificações mais baratas. cavalos, sal e especiarias: no mapa, ainda sem efeito.
RESOURCE_BONUS = {"grain": "food", "wood": "wood", "iron": "iron", "gold": "gold"}
STONE_FORT_DISCOUNT = 0.5
