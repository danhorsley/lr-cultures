"""Headless simulation core. No pygame, no I/O — just rules.

Design notes:
  * One tick = one call to World.step(). This is the atom we'll hook the
    Pixel-Dungeon-style turn system into later (player action -> step()).
  * Species are data-driven via SpeciesDef (see config.py). The step loop is
    generic over `eats_grass` and `eats` — adding a species means appending
    to SimConfig.species, not adding a new branch here.
  * Grass is a bitgrid (set of cells). Animals are objects on a dict grid for
    O(1) neighbour/occupancy checks.
  * Toroidal wrap — no edge effects while we're tuning basic equilibria.
  * Deterministic given config.seed; tuning scripts rely on this.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from foodchain.sim.config import (
    PLAYER_DASH_ENERGY,
    PLAYER_DASH_LEVEL,
    PLAYER_DASH_RANGE,
    PLAYER_DOMINANCE_LEVELS,
    PLAYER_HIDE_DURATION,
    PLAYER_HIDE_ENERGY,
    PLAYER_HIDE_LEVEL,
    PLAYER_KILLS_TO_LEVEL,
    PLAYER_TIERS,
    SimConfig,
    SpeciesDef,
)

Cell = Tuple[int, int]


@dataclass
class Animal:
    species: str        # matches a SpeciesDef.name
    x: int
    y: int
    energy: int
    age: int = 0

    @property
    def pos(self) -> Cell:
        return (self.x, self.y)


@dataclass
class Player:
    """Player-controlled actor. Duck-types as Animal where it matters (species,
    x/y/pos, energy) so it can sit in `World.occupied` and be eaten by predators.
    But behavior is driven manually via `World.step_with_player`, so it is NOT
    added to `self.animals` — it never auto-steps, breeds, or ages."""
    x: int
    y: int
    energy: int
    level: int = 0
    kills: int = 0                                         # resets per tier
    meals: Dict[str, int] = field(default_factory=dict)    # lifetime counts (incl. grass)
    hidden_until_tick: int = 0                             # active-ability stealth
    species: str = "player"

    def has_ability(self, min_level: int) -> bool:
        return self.level >= min_level

    @property
    def total_kills(self) -> int:
        return sum(v for k, v in self.meals.items() if k != "grass")

    @property
    def pos(self) -> Cell:
        return (self.x, self.y)

    @property
    def eats(self) -> frozenset:
        return PLAYER_TIERS[self.level]

    @property
    def kills_to_next(self) -> Optional[int]:
        if self.level >= len(PLAYER_KILLS_TO_LEVEL):
            return None
        return PLAYER_KILLS_TO_LEVEL[self.level]

    @property
    def max_level(self) -> bool:
        return self.level >= len(PLAYER_KILLS_TO_LEVEL)


class World:
    def __init__(self, config: SimConfig):
        self.cfg = config
        self.rng = random.Random(config.seed)
        self.tick: int = 0

        self.species_defs: Dict[str, SpeciesDef] = {s.name: s for s in config.species}
        if len(self.species_defs) != len(config.species):
            raise ValueError("duplicate species names in SimConfig.species")
        for sdef in config.species:
            missing = sdef.eats - set(self.species_defs)
            if missing:
                raise ValueError(
                    f"species {sdef.name!r} eats unknown species: {sorted(missing)}"
                )

        self.grass: Set[Cell] = set()
        self.animals: List[Animal] = []
        self.occupied: Dict[Cell, object] = {}  # Animal | Player
        self.player: Optional[Player] = None
        self._player_killer: Optional[str] = None   # set by the predator step that eats the player
        self.terrain: Dict[Cell, str] = {}          # cell -> "forest" | "water"; absent = plains

        self._generate_terrain()
        self._populate()

    # ------------------------------------------------------------------ setup

    def _populate(self) -> None:
        cfg = self.cfg
        all_cells = [(x, y) for x in range(cfg.width) for y in range(cfg.height)]
        passable_cells = [c for c in all_cells if self.is_passable(c)]
        self.rng.shuffle(passable_cells)

        # Grass seeds onto passable cells only; density is relative to the
        # whole grid so the absolute count stays comparable with non-terrain runs.
        n_grass = min(
            int(cfg.grass_initial_density * len(all_cells)),
            len(passable_cells),
        )
        self.grass = set(passable_cells[:n_grass])

        free = list(passable_cells)
        self.rng.shuffle(free)
        idx = 0

        for sdef in cfg.species:
            placed = 0
            while placed < sdef.initial_count and idx < len(free):
                cell = free[idx]
                idx += 1
                if cell in self.occupied:
                    continue
                a = Animal(sdef.name, cell[0], cell[1], energy=sdef.start_energy)
                self.animals.append(a)
                self.occupied[cell] = a
                placed += 1

    # ----------------------------------------------------------------- terrain

    def _generate_terrain(self) -> None:
        """Random-walk blob biome generation. No-op (and no rng consumed)
        if both biome fractions are zero — preserves pre-terrain determinism.

        Algorithm: for each biome, pick N seed cells and grow each by a
        random walk of `blob_size` steps, marking every cell it touches.
        Water is placed first and locks its cells; forest then fills around
        water without overwriting it."""
        ff = self.cfg.terrain_forest_frac
        wf = self.cfg.terrain_water_frac
        if ff <= 0 and wf <= 0:
            return
        total_cells = self.cfg.width * self.cfg.height

        def grow(biome: str, fraction: float, blob_size: int) -> None:
            # blob_size = unique cells per blob. Random walks revisit heavily,
            # so we step until we've painted `blob_size` new cells (or hit a
            # hard step ceiling to prevent pathological loops).
            target = int(fraction * total_cells)
            if target <= 0 or blob_size <= 0:
                return
            n_seeds = max(1, target // blob_size)
            step_ceiling = blob_size * 6
            painted = 0
            for _ in range(n_seeds):
                x = self.rng.randrange(self.cfg.width)
                y = self.rng.randrange(self.cfg.height)
                this_blob = 0
                steps = 0
                while this_blob < blob_size and steps < step_ceiling:
                    steps += 1
                    cell = (x, y)
                    if cell not in self.terrain:
                        self.terrain[cell] = biome
                        this_blob += 1
                        painted += 1
                        if painted >= target:
                            return
                    step = self.rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
                    x = (x + step[0]) % self.cfg.width
                    y = (y + step[1]) % self.cfg.height

        grow("water", wf, self.cfg.terrain_water_blob_size)
        grow("forest", ff, self.cfg.terrain_forest_blob_size)

    def is_passable(self, cell: Cell) -> bool:
        """Water is the only impassable terrain."""
        return self.terrain.get(cell) != "water"

    def _line_of_sight_clear(self, a: Cell, b: Cell) -> bool:
        """Return True iff no forest cell lies strictly between `a` and `b`.
        Uses linear interpolation along the torus-shortest path; at vision<=3
        this checks at most 2 intermediate cells."""
        dx = self._wrap_delta(a[0], b[0], self.cfg.width)
        dy = self._wrap_delta(a[1], b[1], self.cfg.height)
        steps = max(abs(dx), abs(dy))
        if steps <= 1:
            return True
        for i in range(1, steps):
            x = a[0] + round(dx * i / steps)
            y = a[1] + round(dy * i / steps)
            cell = self._wrap(x, y)
            if self.terrain.get(cell) == "forest":
                return False
        return True

    # ----------------------------------------------------------------- helpers

    def _wrap(self, x: int, y: int) -> Cell:
        return (x % self.cfg.width, y % self.cfg.height)

    def _neighbours(self, x: int, y: int) -> List[Cell]:
        # 4-connected (von Neumann). Swap to 8 later if movement feels too rigid.
        return [
            self._wrap(x + 1, y),
            self._wrap(x - 1, y),
            self._wrap(x, y + 1),
            self._wrap(x, y - 1),
        ]

    def _wrap_delta(self, a: int, b: int, size: int) -> int:
        """Signed shortest-path distance from a to b on a size-wide torus."""
        d = (b - a) % size
        if d > size // 2:
            d -= size
        return d

    def _nearest_in_vision(
        self, actor: Animal, targets: FrozenSet[str], vision: int
    ) -> Optional[Cell]:
        """Nearest cell containing a live animal whose species is in `targets`,
        within Chebyshev distance `vision`. Scans the (2v+1)^2 box around actor."""
        best_pos: Optional[Cell] = None
        best_dist = vision + 1
        ax, ay = actor.x, actor.y
        for dx in range(-vision, vision + 1):
            for dy in range(-vision, vision + 1):
                if dx == 0 and dy == 0:
                    continue
                d = max(abs(dx), abs(dy))
                if d >= best_dist:
                    continue
                cell = self._wrap(ax + dx, ay + dy)
                occ = self.occupied.get(cell)
                if occ is None or occ.energy <= 0:
                    continue
                if occ.species not in targets:
                    continue
                # Hidden species only reveal themselves at adjacent range.
                if d > 1 and self.species_defs[occ.species].hidden:
                    continue
                # Player's hide ability mirrors species-level hidden.
                if d > 1 and isinstance(occ, Player) and self.tick < occ.hidden_until_tick:
                    continue
                # Forest blocks sight past distance 1.
                if d > 1 and not self._line_of_sight_clear(actor.pos, cell):
                    continue
                # Dominated predators don't register the player as prey at all.
                if isinstance(occ, Player) and self._player_dominates_species(actor.species):
                    continue
                best_dist = d
                best_pos = cell
        return best_pos

    def _player_dominates_species(self, predator_species: str) -> bool:
        """True iff the current player has levelled past this predator's
        dominance threshold."""
        if self.player is None:
            return False
        req = PLAYER_DOMINANCE_LEVELS.get(predator_species)
        if req is None:
            return False
        return self.player.level >= req

    def _directional_step(
        self, from_pos: Cell, to_pos: Cell, away: bool
    ) -> Optional[Cell]:
        """Adjacent cell stepping toward `to_pos` (or away from it). Tries the
        dominant axis first, falls back to the perpendicular. None if both
        candidates are occupied."""
        w, h = self.cfg.width, self.cfg.height
        dx = self._wrap_delta(from_pos[0], to_pos[0], w)
        dy = self._wrap_delta(from_pos[1], to_pos[1], h)
        if away:
            dx, dy = -dx, -dy
        sx = (dx > 0) - (dx < 0)
        sy = (dy > 0) - (dy < 0)

        tries: List[Cell] = []
        if abs(dx) >= abs(dy):
            if sx:
                tries.append(self._wrap(from_pos[0] + sx, from_pos[1]))
            if sy:
                tries.append(self._wrap(from_pos[0], from_pos[1] + sy))
        else:
            if sy:
                tries.append(self._wrap(from_pos[0], from_pos[1] + sy))
            if sx:
                tries.append(self._wrap(from_pos[0] + sx, from_pos[1]))
        for c in tries:
            if c not in self.occupied and self.is_passable(c):
                return c
        return None

    # -------------------------------------------------------------------- tick

    def step(self) -> None:
        """Advance the world by one tick."""
        self._regrow_grass()
        order = list(self.animals)
        self.rng.shuffle(order)
        for animal in order:
            if animal.energy <= 0:
                continue  # killed this tick already
            self._step_animal(animal)
        self._reap()
        self.tick += 1

    def _regrow_grass(self) -> None:
        p = self.cfg.grass_regrow_prob
        if p <= 0:
            return
        for x in range(self.cfg.width):
            for y in range(self.cfg.height):
                cell = (x, y)
                if cell in self.grass:
                    continue
                if not self.is_passable(cell):
                    continue
                if self.rng.random() < p:
                    self.grass.add(cell)

    def _step_animal(self, a: Animal) -> None:
        sdef = self.species_defs[a.species]
        a.age += 1
        a.energy -= sdef.move_cost

        neigh = self._neighbours(a.x, a.y)
        self.rng.shuffle(neigh)

        old = a.pos
        moved = False

        # 1. Adjacent prey? Eat. (Skip the player if we're dominated by them —
        # player at required level is invisible-as-prey to this species.)
        if sdef.eats:
            for c in neigh:
                occ = self.occupied.get(c)
                if occ is None or occ.species not in sdef.eats or occ.energy <= 0:
                    continue
                if isinstance(occ, Player) and self._player_dominates_species(a.species):
                    continue
                occ.energy = 0
                del self.occupied[c]
                self._move(a, c)
                a.energy = min(sdef.max_energy, a.energy + sdef.eat_gain)
                moved = True
                if occ is self.player:
                    self._player_killer = a.species
                break

        # 2. Adjacent grass? Eat.
        if not moved and sdef.eats_grass:
            for c in neigh:
                if c in self.occupied:
                    continue
                if c in self.grass:
                    self._move(a, c)
                    self.grass.discard(c)
                    a.energy = min(sdef.max_energy, a.energy + sdef.eat_gain)
                    moved = True
                    break

        # 3. Threat visible? Flee.
        if not moved and sdef.flees_from:
            threat = self._nearest_in_vision(a, sdef.flees_from, sdef.vision)
            if threat is not None:
                step = self._directional_step(a.pos, threat, away=True)
                if step is not None:
                    self._move(a, step)
                    moved = True

        # 4. Prey visible (but not adjacent)? Pursue.
        if not moved and sdef.pursues_prey and sdef.eats:
            prey = self._nearest_in_vision(a, sdef.eats, sdef.vision)
            if prey is not None:
                step = self._directional_step(a.pos, prey, away=False)
                if step is not None:
                    self._move(a, step)
                    moved = True

        # 5. Wander — unless sessile.
        if not moved and not sdef.sessile:
            for c in neigh:
                if c not in self.occupied and self.is_passable(c):
                    self._move(a, c)
                    moved = True
                    break

        self._maybe_breed(a, old, sdef)

    def _move(self, a: Animal, target: Cell) -> None:
        # Caller must have already cleared `target` of any occupant.
        del self.occupied[a.pos]
        a.x, a.y = target
        self.occupied[target] = a

    def _maybe_breed(self, a: Animal, vacated: Cell, sdef: SpeciesDef) -> None:
        # Energy conservation: parent transfers `breed_cost` to the child.
        # Birth cell is either `vacated` (the parent moved off it) or, for
        # breed_in_place species, any empty neighbour.
        if a.age < sdef.breed_age:
            return
        if a.energy < sdef.breed_cost:
            return

        birth_cell: Optional[Cell]
        if sdef.breed_in_place:
            candidates = [
                c for c in self._neighbours(a.x, a.y)
                if c not in self.occupied and self.is_passable(c)
            ]
            if not candidates:
                return
            birth_cell = self.rng.choice(candidates)
        else:
            if vacated == a.pos or vacated in self.occupied:
                return
            if not self.is_passable(vacated):
                return
            birth_cell = vacated

        a.energy -= sdef.breed_cost
        child = Animal(sdef.name, birth_cell[0], birth_cell[1], energy=sdef.breed_cost)
        self.animals.append(child)
        self.occupied[birth_cell] = child
        a.age = 0

    def _reap(self) -> None:
        survivors: List[Animal] = []
        for a in self.animals:
            if a.energy <= 0:
                if self.occupied.get(a.pos) is a:
                    del self.occupied[a.pos]
            else:
                survivors.append(a)
        self.animals = survivors

    # --------------------------------------------------------------- readouts

    def counts(self) -> Dict[str, int]:
        """{'grass': N, species_name: N, ...} — one entry per species plus grass.
        Player is not included in counts (ecological view only)."""
        out: Dict[str, int] = {"grass": len(self.grass)}
        for name in self.species_defs:
            if name == "player":
                continue
            out[name] = 0
        for a in self.animals:
            if a.species == "player":
                continue
            out[a.species] += 1
        return out

    # ------------------------------------------------------------------ player

    def place_player(self, x: Optional[int] = None, y: Optional[int] = None) -> Player:
        """Drop the player onto an empty cell. If x/y omitted, pick a random
        empty cell near the centre."""
        if "player" not in self.species_defs:
            raise ValueError("roster has no 'player' SpeciesDef registered")
        player_sdef = self.species_defs["player"]

        if x is None or y is None:
            cx, cy = self.cfg.width // 2, self.cfg.height // 2
            # spiral outward from centre until we find something passable & free
            for radius in range(max(self.cfg.width, self.cfg.height)):
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        cell = self._wrap(cx + dx, cy + dy)
                        if cell not in self.occupied and self.is_passable(cell):
                            x, y = cell
                            break
                    if x is not None:
                        break
                if x is not None:
                    break

        if (x, y) in self.occupied:
            raise ValueError(f"cell {(x, y)} is occupied")
        if not self.is_passable((x, y)):
            raise ValueError(f"cell {(x, y)} is water")

        self.player = Player(x=x, y=y, energy=player_sdef.start_energy)
        self.occupied[(x, y)] = self.player
        return self.player

    def step_with_player(self, action: str, direction: Optional[Cell] = None) -> Dict:
        """Advance the world by one turn, with the player acting first.

        Actions:
            "move"   — requires direction; walk one cell (or attack edible prey).
            "wait"   — no movement; one tick passes.
            "dash"   — requires direction; up to 2 cells (unlock at L1).
            "hide"   — no direction; invisible at d>1 for N ticks (unlock at L2).

        Returns info dict:
            {"ticked", "ate", "leveled_up", "won", "died_by", "message"}
        Invalid / blocked / locked actions return ticked=False and no state
        changes — caller should re-prompt. `message` carries a short reason
        for locked / blocked ability uses.
        """
        info = {"ticked": False, "ate": None, "leveled_up": False,
                "won": False, "died_by": None, "message": None}
        self._player_killer = None

        if self.player is None:
            self.step()
            info["ticked"] = True
            return info

        player = self.player
        player_sdef = self.species_defs["player"]
        cost = player_sdef.move_cost   # default metabolism

        # ---- Player action --------------------------------------------------
        if action == "move":
            if direction is None:
                raise ValueError("move action requires direction")
            target = self._wrap(player.x + direction[0], player.y + direction[1])
            if not self._can_player_step_onto(target):
                return info
            self._execute_player_step(target, info)

        elif action == "dash":
            if not player.has_ability(PLAYER_DASH_LEVEL):
                info["message"] = f"dash locked — reach level {PLAYER_DASH_LEVEL}"
                return info
            if direction is None:
                raise ValueError("dash action requires direction")
            t1 = self._wrap(player.x + direction[0], player.y + direction[1])
            if not self._can_player_step_onto(t1):
                return info
            killed = self._execute_player_step(t1, info)
            # Continue up to the dash range, stopping on any kill.
            for _ in range(PLAYER_DASH_RANGE - 1):
                if killed:
                    break
                t = self._wrap(player.x + direction[0], player.y + direction[1])
                if not self._can_player_step_onto(t):
                    break
                killed = self._execute_player_step(t, info)
            cost = PLAYER_DASH_ENERGY

        elif action == "hide":
            if not player.has_ability(PLAYER_HIDE_LEVEL):
                info["message"] = f"hide locked — reach level {PLAYER_HIDE_LEVEL}"
                return info
            player.hidden_until_tick = self.tick + PLAYER_HIDE_DURATION
            info["message"] = f"hidden for {PLAYER_HIDE_DURATION} turns"
            cost = PLAYER_HIDE_ENERGY

        elif action in ("wait", "skip"):
            pass

        else:
            raise ValueError(f"unknown action: {action!r}")

        info["ticked"] = True
        player.energy -= cost

        # Starvation before the world acts.
        if player.energy <= 0:
            if self.occupied.get(player.pos) is player:
                del self.occupied[player.pos]
            self.player = None
            info["died_by"] = "starved"
            self.step()
            return info

        # ---- World turn -----------------------------------------------------
        self.step()

        # Did anything eat the player during the world turn?
        if self.player is not None and self.player.energy <= 0:
            info["died_by"] = self._player_killer or "predator"
            self.player = None

        return info

    def _can_player_step_onto(self, target: Cell) -> bool:
        """True iff the player could validly step onto `target` this turn —
        passable terrain, and either empty or containing live edible prey."""
        if self.player is None:
            return False
        if not self.is_passable(target):
            return False
        occ = self.occupied.get(target)
        if occ is None or occ is self.player:
            return True
        return occ.species in self.player.eats and occ.energy > 0

    def _execute_player_step(self, target: Cell, info: Dict) -> bool:
        """Commit a validated player step. Caller must have confirmed
        `_can_player_step_onto(target)` first. Returns True iff a kill
        occurred (used by dash to decide whether to stop after this step —
        grazing grass is not a kill)."""
        player = self.player
        player_sdef = self.species_defs["player"]
        occ = self.occupied.get(target)
        if occ is not None and occ is not player:
            occ.energy = 0
            del self.occupied[target]
            self._move(player, target)
            player.energy = min(
                player_sdef.max_energy, player.energy + player_sdef.eat_gain
            )
            player.kills += 1
            player.meals[occ.species] = player.meals.get(occ.species, 0) + 1
            info["ate"] = occ.species
            if occ.species == "apex":
                info["won"] = True
            if self._try_level_up():
                info["leveled_up"] = True
            return True
        if target in self.grass:
            self.grass.discard(target)
            player.energy = min(
                player_sdef.max_energy, player.energy + player_sdef.eat_gain
            )
            player.meals["grass"] = player.meals.get("grass", 0) + 1
            info["ate"] = "grass"
        self._move(player, target)
        return False

    def _try_level_up(self) -> bool:
        p = self.player
        if p is None or p.max_level:
            return False
        threshold = p.kills_to_next
        if threshold is None:
            return False
        if p.kills >= threshold:
            p.level += 1
            p.kills = 0      # reset toward next tier
            return True
        return False
