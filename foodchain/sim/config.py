"""All simulation tunables live here. One place to sweep when tuning equilibria.

Species are now data-driven: a SimConfig carries a list[SpeciesDef], and the
World's step loop is generic over what each species eats. Adding a new species
is a matter of appending an entry — no new branches in world.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Tuple


@dataclass(frozen=True)
class SpeciesDef:
    name: str
    initial_count: int
    start_energy: int
    max_energy: int
    move_cost: int          # energy deducted each tick (metabolism)
    breed_age: int          # ticks alive before reproducing
    breed_cost: int         # parent needs >= this to breed; transferred to child
    eat_gain: int           # energy gained on a successful eat (grass or prey)
    eats_grass: bool = False
    eats: FrozenSet[str] = frozenset()          # names of species this one preys on
    color: Tuple[int, int, int] = (200, 200, 200)

    # -- Behavior fields. All default off — classic species use none. ------------
    vision: int = 1                             # Chebyshev radius for flee/pursue
    flees_from: FrozenSet[str] = frozenset()    # species seen within vision → flee
    pursues_prey: bool = False                  # if prey visible (not adjacent), step toward it
    sessile: bool = False                       # no wandering; only moves to eat or flee
    breed_in_place: bool = False                # can spawn offspring into an empty neighbour without vacating
    hidden: bool = False                        # detectable only at Chebyshev distance <= 1


# --------------------------------------------------------------------------
# Player. A stub SpeciesDef so predators can have "player" in their `eats`
# set without breaking the validator. The Player class (see world.py) handles
# level/tier/eats dynamically — the fields below are only used for metabolism
# (move_cost), satiety cap (max_energy), and grass eating.
PLAYER_SPECIES: SpeciesDef = SpeciesDef(
    name="player",
    initial_count=0,                # placed manually via World.place_player
    start_energy=20,
    max_energy=40,
    move_cost=1,
    breed_age=10**9,                # never
    breed_cost=10**9,
    eat_gain=10,
    eats_grass=True,
    color=(255, 255, 255),
)

# Per-level `eats` sets — what the player can kill at each level.
# Length is max_level + 1.
PLAYER_TIERS = (
    frozenset({"multiplier"}),
    frozenset({"multiplier", "hider"}),
    frozenset({"multiplier", "hider", "runner"}),
    frozenset({"multiplier", "hider", "runner", "stalker"}),
    frozenset({"multiplier", "hider", "runner", "stalker", "sprinter"}),
    frozenset({"multiplier", "hider", "runner", "stalker", "sprinter", "apex"}),
)
# Kills required to advance from level i to i+1. Length = len(PLAYER_TIERS) - 1.
PLAYER_KILLS_TO_LEVEL = (5, 10, 15, 20, 30)

# Abilities unlocked per level (inclusive minimum level).
PLAYER_DASH_LEVEL = 1
PLAYER_HIDE_LEVEL = 2

# Ability costs (energy) and tuning.
PLAYER_DASH_ENERGY = 3
PLAYER_DASH_RANGE = 2          # up to this many cells per dash
PLAYER_HIDE_ENERGY = 5
PLAYER_HIDE_DURATION = 3       # ticks of invisibility

# Passive progression: at each level below, the named predator becomes
# dominated by the player. Dominated predators cannot eat the player and
# do not see the player as prey (no chasing, no lock-on). Eating stays
# controlled by PLAYER_TIERS (at each level the player can eat one more
# species); dominance mirrors the food unlock on the threat side.
PLAYER_DOMINANCE_LEVELS: dict = {
    "stalker": 3,
    "sprinter": 4,
    "apex": 5,
}


# Two-species ecology — the tuned Phase 1 baseline. Known-good coexistence.
CLASSIC_SPECIES: List[SpeciesDef] = [
    SpeciesDef(
        name="herbivore",
        initial_count=120,
        start_energy=8,
        max_energy=20,
        move_cost=1,
        breed_age=8,
        breed_cost=6,
        eat_gain=12,
        eats_grass=True,
        color=(220, 200, 90),
    ),
    SpeciesDef(
        name="predator",
        initial_count=20,
        start_energy=15,
        max_energy=30,
        move_cost=1,
        breed_age=14,
        breed_cost=6,
        eat_gain=15,
        eats=frozenset({"herbivore", "player"}),
        color=(210, 70, 70),
    ),
    PLAYER_SPECIES,
]


# Six-species ecology — Phase 2. Stat-only differentiation.
# Three herbivore life-history strategies (r-selected / efficient / K-selected),
# three predator strategies (ambush / pursuit / omnipredator). Behaviors
# are all identical; distinctiveness comes from stats and food-web position
# (apex eats other predators).
PHASE2_SPECIES: List[SpeciesDef] = [
    # ------- Herbivores — all eat grass, compete for the same resource -------
    SpeciesDef(
        # r-selected: cheap, fast, many individuals. Reproduces without vacating.
        name="multiplier",
        initial_count=60,
        start_energy=5,
        max_energy=12,
        move_cost=1,
        breed_age=4,
        breed_cost=4,
        eat_gain=8,
        eats_grass=True,
        color=(240, 230, 110),
        breed_in_place=True,
    ),
    SpeciesDef(
        # Forages normally — but predators can't see it from further than 1 cell.
        # Sprinters and other vision>1 hunters ignore it at distance.
        name="hider",
        initial_count=35,
        start_energy=10,
        max_energy=22,
        move_cost=1,
        breed_age=10,
        breed_cost=6,
        eat_gain=12,
        eats_grass=True,
        color=(140, 170, 90),
        hidden=True,
    ),
    SpeciesDef(
        # Long eyesight; flees predators early. Pays for that edge with
        # higher movement cost and expensive breeding.
        name="runner",
        initial_count=20,
        start_energy=15,
        max_energy=30,
        move_cost=2,
        breed_age=18,
        breed_cost=10,
        eat_gain=18,
        eats_grass=True,
        color=(210, 170, 50),
        vision=3,
        flees_from=frozenset({"stalker", "sprinter", "apex"}),
    ),
    # -------- Predators ------------------------------------------------------
    SpeciesDef(
        # Ambush: never wanders. Only moves to kill adjacent prey or flinch
        # from an adjacent apex.
        name="stalker",
        initial_count=10,
        start_energy=12,
        max_energy=24,
        move_cost=1,
        breed_age=14,
        breed_cost=6,
        eat_gain=12,
        eats=frozenset({"multiplier", "hider", "runner", "player"}),
        color=(150, 50, 50),
        sessile=True,
        flees_from=frozenset({"apex"}),
    ),
    SpeciesDef(
        # Pursuit: chases visible herbivores.
        name="sprinter",
        initial_count=8,
        start_energy=15,
        max_energy=30,
        move_cost=2,
        breed_age=16,
        breed_cost=7,
        eat_gain=18,
        eats=frozenset({"multiplier", "hider", "runner", "player"}),
        color=(240, 90, 70),
        vision=2,
        pursues_prey=True,
    ),
    SpeciesDef(
        # Omnipredator. Already distinct via food web — no behavior change.
        # Expensive to reproduce and modest per-kill payoff so it doesn't
        # snowball through the rest of the food web.
        name="apex",
        initial_count=3,
        start_energy=25,
        max_energy=50,
        move_cost=2,
        breed_age=28,
        breed_cost=18,
        eat_gain=18,
        eats=frozenset({"multiplier", "hider", "runner", "stalker", "sprinter", "player"}),
        color=(180, 70, 200),
    ),
    PLAYER_SPECIES,
]


# Default for main.py / tune.py is still the validated Phase 1 baseline.
DEFAULT_SPECIES: List[SpeciesDef] = CLASSIC_SPECIES


@dataclass
class SimConfig:
    # World
    width: int = 60
    height: int = 40
    seed: int = 0

    # Grass (the base food source)
    grass_initial_density: float = 0.5
    grass_regrow_prob: float = 0.02

    # Terrain / biomes. All zero -> no terrain generated, sim behaves
    # identically to pre-biome versions (tests rely on this).
    #
    # Fractions are the approximate share of the grid covered by each biome.
    # Blob size is the walk length per seed — bigger = fewer, larger clusters.
    terrain_forest_frac: float = 0.0
    terrain_water_frac: float = 0.0
    terrain_forest_blob_size: int = 40
    terrain_water_blob_size: int = 12

    # Species roster
    species: List[SpeciesDef] = field(
        default_factory=lambda: list(DEFAULT_SPECIES)
    )
