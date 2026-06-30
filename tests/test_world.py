"""Sanity tests — not exhaustive, just catch the dumb breakages."""
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from foodchain.sim import DEFAULT_SPECIES, PLAYER_SPECIES, SimConfig, World


def _predator_only_config(seed: int, count: int, start_energy: int) -> SimConfig:
    """A world with predators but zero herbivores and no grass regrowth."""
    herb = next(s for s in DEFAULT_SPECIES if s.name == "herbivore")
    pred = next(s for s in DEFAULT_SPECIES if s.name == "predator")
    herb = replace(herb, initial_count=0)
    pred = replace(pred, initial_count=count, start_energy=start_energy)
    return SimConfig(
        seed=seed, grass_regrow_prob=0.0, species=[herb, pred, PLAYER_SPECIES]
    )


def test_deterministic():
    a = World(SimConfig(seed=7))
    b = World(SimConfig(seed=7))
    for _ in range(200):
        a.step()
        b.step()
    assert a.counts() == b.counts()


def test_occupied_invariant():
    w = World(SimConfig(seed=1))
    for _ in range(100):
        w.step()
        for animal in w.animals:
            assert w.occupied.get(animal.pos) is animal
        assert len(w.occupied) == len(w.animals)


def test_predator_starves_without_prey():
    w = World(_predator_only_config(seed=3, count=10, start_energy=5))
    for _ in range(50):
        w.step()
    counts = w.counts()
    assert counts["predator"] == 0


def test_predator_cannot_breed_without_food():
    # Plenty of starting energy and long runway — but no prey means they should
    # eventually die out, not self-replace forever.
    w = World(_predator_only_config(seed=4, count=40, start_energy=30))
    for _ in range(500):
        w.step()
    assert w.counts()["predator"] == 0


def test_no_phantom_herbivores_after_kill():
    w = World(SimConfig(seed=2))
    for _ in range(50):
        w.step()
        for a in w.animals:
            assert w.occupied.get(a.pos) is a


def test_counts_keys():
    w = World(SimConfig(seed=0))
    c = w.counts()
    assert set(c) == {"grass", "herbivore", "predator"}


# ------------- Phase 3 behaviour mechanics --------------------------------

def _minimal_species(**overrides):
    from foodchain.sim import SpeciesDef
    base = dict(
        name="x", initial_count=0, start_energy=10, max_energy=20,
        move_cost=1, breed_age=999, breed_cost=999, eat_gain=5,
    )
    base.update(overrides)
    return SpeciesDef(**base)


def test_hidden_invisible_at_distance_greater_than_one():
    from foodchain.sim import SpeciesDef, Animal
    from foodchain.sim.config import SpeciesDef as SD
    hider = _minimal_species(name="h", eats_grass=True, hidden=True)
    seeker = _minimal_species(name="s", eats=frozenset({"h"}), vision=3, pursues_prey=True)
    cfg = SimConfig(seed=0, grass_initial_density=0.0, grass_regrow_prob=0.0,
                    species=[hider, seeker])
    w = World(cfg)
    # Place hider at (5,5) and seeker at (5,8) — Chebyshev distance 3.
    w.animals = []
    w.occupied = {}
    h = Animal("h", 5, 5, energy=10)
    s = Animal("s", 5, 8, energy=10)
    w.animals = [h, s]
    w.occupied = {(5, 5): h, (5, 8): s}
    # With hidden=True, seeker should not detect hider at distance 3.
    assert w._nearest_in_vision(s, frozenset({"h"}), 3) is None
    # But right next to it, it should.
    assert w._nearest_in_vision(s, frozenset({"h"}), 1) is None   # still not adjacent
    s.x, s.y = 5, 6
    w.occupied = {(5, 5): h, (5, 6): s}
    assert w._nearest_in_vision(s, frozenset({"h"}), 3) == (5, 5)


def test_pursuer_steps_toward_prey():
    from foodchain.sim import Animal
    prey = _minimal_species(name="p", eats_grass=True)
    hunter = _minimal_species(
        name="h", eats=frozenset({"p"}), vision=3, pursues_prey=True, move_cost=0,
    )
    cfg = SimConfig(seed=0, grass_initial_density=0.0, grass_regrow_prob=0.0,
                    species=[prey, hunter])
    w = World(cfg)
    p = Animal("p", 10, 10, energy=99)
    h = Animal("h", 10, 13, energy=99)
    w.animals = [p, h]
    w.occupied = {(10, 10): p, (10, 13): h}
    w._step_animal(h)
    # Hunter should have moved one step toward prey (y decreased).
    assert h.y == 12 and h.x == 10


def test_breed_in_place_does_not_require_movement():
    from foodchain.sim import Animal
    sdef = _minimal_species(
        name="r", eats_grass=True, breed_age=1, breed_cost=2, breed_in_place=True,
    )
    cfg = SimConfig(seed=0, grass_initial_density=0.0, grass_regrow_prob=0.0,
                    species=[sdef])
    w = World(cfg)
    parent = Animal("r", 5, 5, energy=10, age=1)
    w.animals = [parent]
    w.occupied = {(5, 5): parent}
    before = len(w.animals)
    w._maybe_breed(parent, parent.pos, sdef)   # vacated == pos — would block non-in-place
    assert len(w.animals) == before + 1


def test_flee_bypasses_sessile():
    from foodchain.sim import Animal
    threat = _minimal_species(name="t")
    sitter = _minimal_species(
        name="s", sessile=True, vision=1, flees_from=frozenset({"t"}), move_cost=0,
    )
    cfg = SimConfig(seed=0, grass_initial_density=0.0, grass_regrow_prob=0.0,
                    species=[threat, sitter])
    w = World(cfg)
    t = Animal("t", 5, 5, energy=99)
    s = Animal("s", 5, 6, energy=99)
    w.animals = [t, s]
    w.occupied = {(5, 5): t, (5, 6): s}
    w._step_animal(s)
    # Sessile animal should have moved away from adjacent threat.
    assert s.pos != (5, 6)


# -------------- Phase 3 player -------------------------------------------

def test_player_blocked_move_does_not_tick():
    from foodchain.sim import Animal
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=0, species=list(PHASE2_SPECIES))
    w = World(cfg)
    w.animals = []
    w.occupied = {}
    w.place_player(5, 5)
    # Put a hider (not in player's tier-0 eats) right next to the player.
    hider = Animal("hider", 6, 5, energy=10)
    w.animals = [hider]
    w.occupied[(6, 5)] = hider
    before_tick = w.tick
    info = w.step_with_player("move", (1, 0))
    assert info["ticked"] is False
    assert w.tick == before_tick
    assert w.player.pos == (5, 5)   # stayed put


def test_player_eats_prey_and_counts_kill():
    from foodchain.sim import Animal
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=0, grass_initial_density=0.0, grass_regrow_prob=0.0,
                    species=list(PHASE2_SPECIES))
    w = World(cfg)
    w.animals = []
    w.occupied = {}
    w.place_player(5, 5)
    mult = Animal("multiplier", 6, 5, energy=10)
    w.animals = [mult]
    w.occupied[(6, 5)] = mult
    info = w.step_with_player("move", (1, 0))
    assert info["ticked"] is True
    assert info["ate"] == "multiplier"
    assert w.player is not None
    assert w.player.kills == 1
    assert w.player.pos == (6, 5)


# -------------- Stage 3B player abilities --------------------------------

def _lonely_player_world(seed=0):
    """PHASE2 roster, grass off, no terrain — good bench for ability tests."""
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=seed, species=list(PHASE2_SPECIES),
                    grass_initial_density=0.0, grass_regrow_prob=0.0)
    w = World(cfg)
    w.animals = []
    w.occupied = {}
    return w


def test_dash_locked_at_level_zero():
    w = _lonely_player_world()
    w.place_player(10, 10)
    before = w.tick
    info = w.step_with_player("dash", (1, 0))
    assert info["ticked"] is False
    assert w.tick == before
    assert "locked" in (info.get("message") or "")


def test_dash_moves_two_cells_when_unblocked():
    from foodchain.sim.config import PLAYER_DASH_ENERGY
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 1
    start_energy = w.player.energy
    info = w.step_with_player("dash", (1, 0))
    assert info["ticked"] is True
    assert w.player.pos == (12, 10)
    # Dash pays dash-energy, not move_cost.
    assert start_energy - w.player.energy == PLAYER_DASH_ENERGY


def test_dash_stops_after_eating_first_cell_prey():
    from foodchain.sim import Animal
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 1
    prey = Animal("multiplier", 11, 10, energy=10)
    w.animals = [prey]
    w.occupied[(11, 10)] = prey
    info = w.step_with_player("dash", (1, 0))
    assert info["ticked"] is True
    assert info["ate"] == "multiplier"
    assert w.player.pos == (11, 10)     # stopped at the kill


def test_hide_makes_player_invisible_at_distance_two():
    """Test the vision rule directly. We set hidden_until_tick manually so
    the world.step() inside step_with_player can't move the sprinter around."""
    from foodchain.sim import Animal
    w = _lonely_player_world()
    w.place_player(10, 10)
    spr = Animal("sprinter", 12, 10, energy=20)
    w.animals = [spr]
    w.occupied[(12, 10)] = spr

    # Not hidden: sprinter sees player at distance 2.
    assert w._nearest_in_vision(spr, frozenset({"player"}), 2) == (10, 10)

    # Flip on the hide flag as the ability would.
    w.player.hidden_until_tick = w.tick + 5
    assert w._nearest_in_vision(spr, frozenset({"player"}), 2) is None

    # Adjacency still reveals the player — hide matches the species-level rule.
    del w.occupied[(12, 10)]
    spr.x = 11
    w.occupied[(11, 10)] = spr
    assert w._nearest_in_vision(spr, frozenset({"player"}), 1) == (10, 10)


def test_hide_ability_sets_flag_via_step():
    """End-to-end: invoking the hide action actually flips the flag."""
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 2
    info = w.step_with_player("hide")
    assert info["ticked"] is True
    assert w.player is not None and w.player.hidden_until_tick > w.tick


def test_hide_locked_at_level_one():
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 1
    info = w.step_with_player("hide")
    assert info["ticked"] is False
    assert "locked" in (info.get("message") or "")


def test_dominated_stalker_cannot_eat_player():
    """At level 3, stalkers stop being a threat — they no longer eat the
    player even when adjacent."""
    from foodchain.sim import Animal
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 3
    stalker = Animal("stalker", 11, 10, energy=20)
    w.animals = [stalker]
    w.occupied[(11, 10)] = stalker
    # Wait a few turns — stalker is adjacent, would normally attack.
    for _ in range(5):
        if w.player is None:
            break
        w.step_with_player("wait")
    assert w.player is not None      # survived dominated stalker


def test_non_dominated_stalker_still_attacks():
    """At level 2, stalkers are still predators."""
    from foodchain.sim import Animal
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 2
    stalker = Animal("stalker", 11, 10, energy=20)
    w.animals = [stalker]
    w.occupied[(11, 10)] = stalker
    died = False
    for _ in range(10):
        if w.player is None:
            died = True
            break
        w.step_with_player("wait")
    assert died, "level-2 player should be vulnerable to an adjacent stalker"


def test_dominated_sprinter_does_not_pursue_player():
    """At level 4, sprinter's pursue-prey logic ignores the player."""
    from foodchain.sim import Animal
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 4
    spr = Animal("sprinter", 12, 10, energy=30)
    w.animals = [spr]
    w.occupied[(12, 10)] = spr
    # Sprinter's vision scan should not see the player as prey.
    assert w._nearest_in_vision(spr, frozenset({"player"}), 3) is None


def test_apex_dominance_at_level_5():
    """The payoff: at max level, apex can't eat the player."""
    from foodchain.sim import Animal
    w = _lonely_player_world()
    w.place_player(10, 10)
    w.player.level = 5
    ap = Animal("apex", 11, 10, energy=30)
    w.animals = [ap]
    w.occupied[(11, 10)] = ap
    for _ in range(10):
        if w.player is None:
            break
        w.step_with_player("wait")
    assert w.player is not None      # invincible to apex at L5


# -------------- Phase 4 biomes -------------------------------------------

def test_default_config_has_no_terrain():
    """Terrain is off by default — critical for preserving existing test
    determinism and the tuned ecology numbers."""
    w = World(SimConfig(seed=0))
    assert w.terrain == {}


def test_terrain_generation_is_deterministic():
    cfg_kwargs = dict(seed=42, terrain_forest_frac=0.2, terrain_water_frac=0.05)
    a = World(SimConfig(**cfg_kwargs))
    b = World(SimConfig(**cfg_kwargs))
    assert a.terrain == b.terrain
    # And non-empty — with these fractions we expect both biomes present.
    kinds = set(a.terrain.values())
    assert "forest" in kinds and "water" in kinds


def test_animals_never_spawn_on_water():
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=1, species=list(PHASE2_SPECIES),
                    terrain_forest_frac=0.2, terrain_water_frac=0.1)
    w = World(cfg)
    for a in w.animals:
        assert w.is_passable(a.pos), f"{a.species} spawned on water at {a.pos}"


def test_grass_never_grows_on_water():
    cfg = SimConfig(seed=2, terrain_forest_frac=0.2, terrain_water_frac=0.1,
                    grass_regrow_prob=0.5)  # turbo-regrow to stress-test
    w = World(cfg)
    for _ in range(50):
        w.step()
    for cell in w.grass:
        assert w.is_passable(cell), f"grass appeared on water at {cell}"


def test_animals_never_move_onto_water():
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=3, species=list(PHASE2_SPECIES),
                    terrain_forest_frac=0.2, terrain_water_frac=0.1)
    w = World(cfg)
    for _ in range(200):
        w.step()
        for a in w.animals:
            assert w.is_passable(a.pos), (
                f"{a.species} ended up on water at {a.pos} at tick {w.tick}"
            )


def test_player_blocked_by_water():
    from foodchain.sim import Animal
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=0, species=list(PHASE2_SPECIES))   # no terrain
    w = World(cfg)
    w.animals = []
    w.occupied = {}
    # Manually place water next to the player.
    w.terrain[(6, 5)] = "water"
    w.place_player(5, 5)
    before = w.tick
    info = w.step_with_player("move", (1, 0))
    assert info["ticked"] is False
    assert w.tick == before
    assert w.player.pos == (5, 5)


def test_forest_blocks_line_of_sight():
    from foodchain.sim import Animal
    from foodchain.sim.config import PHASE2_SPECIES
    cfg = SimConfig(seed=0, species=list(PHASE2_SPECIES))
    w = World(cfg)
    w.animals = []
    w.occupied = {}
    # Place a sprinter (vision 2, pursues_prey) three cells east of a multiplier
    # with a forest cell directly between them.
    mult = Animal("multiplier", 5, 5, energy=10)
    spr = Animal("sprinter", 7, 5, energy=10)
    w.animals = [mult, spr]
    w.occupied = {(5, 5): mult, (7, 5): spr}
    # Distance 2 — would normally be visible to sprinter.
    assert w._nearest_in_vision(spr, frozenset({"multiplier"}), 2) == (5, 5)
    # Drop a forest cell between them — sight should be blocked.
    w.terrain[(6, 5)] = "forest"
    assert w._nearest_in_vision(spr, frozenset({"multiplier"}), 2) is None
    # But at distance 1 forest is irrelevant (adjacency always sees).
    spr.x = 6  # move sprinter onto... wait, forest doesn't block entry; but
    # for this test we want a close-range check. Put sprinter directly adjacent.
    # (Actually forest doesn't block movement, only sight.)
    w.terrain.pop((6, 5))  # clean up for the assertion below
    spr.x = 6
    del w.occupied[(7, 5)]
    w.occupied[(6, 5)] = spr
    assert w._nearest_in_vision(spr, frozenset({"multiplier"}), 1) == (5, 5)


def test_player_levels_up_at_threshold():
    from foodchain.sim import Animal
    from foodchain.sim.config import PHASE2_SPECIES, PLAYER_KILLS_TO_LEVEL
    cfg = SimConfig(seed=0, grass_initial_density=0.0, grass_regrow_prob=0.0,
                    species=list(PHASE2_SPECIES))
    w = World(cfg)
    w.animals = []
    w.occupied = {}
    w.place_player(10, 10)
    # Stand the player one kill short of levelling up, then feed them one multiplier.
    w.player.kills = PLAYER_KILLS_TO_LEVEL[0] - 1
    mult = Animal("multiplier", 11, 10, energy=10)
    w.animals = [mult]
    w.occupied[(11, 10)] = mult
    info = w.step_with_player("move", (1, 0))
    assert info["ate"] == "multiplier"
    assert info["leveled_up"] is True
    assert w.player.level == 1
    assert "hider" in w.player.eats


if __name__ == "__main__":
    test_deterministic()
    test_occupied_invariant()
    test_predator_starves_without_prey()
    test_predator_cannot_breed_without_food()
    test_no_phantom_herbivores_after_kill()
    test_counts_keys()
    test_hidden_invisible_at_distance_greater_than_one()
    test_pursuer_steps_toward_prey()
    test_breed_in_place_does_not_require_movement()
    test_flee_bypasses_sessile()
    test_player_blocked_move_does_not_tick()
    test_player_eats_prey_and_counts_kill()
    test_player_levels_up_at_threshold()
    test_default_config_has_no_terrain()
    test_terrain_generation_is_deterministic()
    test_animals_never_spawn_on_water()
    test_grass_never_grows_on_water()
    test_animals_never_move_onto_water()
    test_player_blocked_by_water()
    test_forest_blocks_line_of_sight()
    test_dash_locked_at_level_zero()
    test_dash_moves_two_cells_when_unblocked()
    test_dash_stops_after_eating_first_cell_prey()
    test_hide_makes_player_invisible_at_distance_two()
    test_hide_ability_sets_flag_via_step()
    test_hide_locked_at_level_one()
    test_dominated_stalker_cannot_eat_player()
    test_non_dominated_stalker_still_attacks()
    test_dominated_sprinter_does_not_pursue_player()
    test_apex_dominance_at_level_5()
    print("ok")
