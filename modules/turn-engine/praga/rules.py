"""Constantes das regras núcleo (docs/regras-nucleo.md, v0.2).

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
    order_cost = {"move": 1, "attack": 1, "garrison": 0, "purge": 1, "build": 1, "recruit": 1, "posture": 0}

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
    # v0.3: recuo natural em regiões bem governadas (decisão 2B)
    plague_recede: int = 3               # por turno, com ordem pública 3 e sem fome
    # focos iniciais (decisão 1B)
    plague_foci: int = 6
    foci_min_distance: int = 6           # regiões até à capital mais próxima
    foci_neighbor_plague: int = 30
    # alternativas em estudo (desligadas por defeito; ver docs/simulacao-v0.3.md)
    free_lands_resist: bool = False      # Terras Livres com guarnição também fazem recuar a Praga
    plague_burnout: int = 0              # regiões perdidas perdem N/turno; abaixo de 80 viram ruínas livres
    plague_equilibrium: float | None = None  # alvo (fração do mapa); força = (alvo/perdido)^1.5 em crescimento e alastramento
    # equilíbrio por "teto" da v0.2: falhou na simulação; desligado por defeito
    plague_target: tuple | None = None

    # §7 entrada e abandono
    protection_turns: int = 5
    regency_after: int = 3
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
