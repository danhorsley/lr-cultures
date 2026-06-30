"""Pygame entrypoint.

Culture Sort (L/R) — default mode:
    python main.py
    python main.py --seed 42

Legacy foodchain sim (observer / play):
    python main.py --foodchain
    python main.py --foodchain --species phase2 --play

Browser (via pygbag):
    When sys.platform is "emscripten" (Pyodide), we skip argparse and run
    Culture Sort in portrait mode.
"""
import asyncio
import os
import sys

# NB: pygbag's dependency scanner only looks for `import pygame` in THIS file
# to decide whether to pull the pygame-ce wheel into the browser bundle.
# Transitive imports (ours live inside foodchain.render) aren't detected and
# the browser runtime silently refuses to start the script. Keeping this
# import at module level is load-bearing for the web build.
import pygame  # noqa: F401  — load-bearing for pygbag dep detection

print("[lr] boot: importing app", flush=True)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
    print(f"[lr] sys.path += {_THIS_DIR}", flush=True)

from foodchain.lr.config import LRConfig
from foodchain.render.lr_view import LRApp
from foodchain.render.pygame_view import App as FoodchainApp
from foodchain.sim import SimConfig
from foodchain.sim.config import CLASSIC_SPECIES, PHASE2_SPECIES

ROSTERS = {"classic": CLASSIC_SPECIES, "phase2": PHASE2_SPECIES}

DEFAULT_FOREST_FRAC = 0.22
DEFAULT_WATER_FRAC = 0.06

IS_BROWSER = sys.platform in ("emscripten", "wasi")


def _browser_config():
    return LRConfig(seed=12)


def _native_config():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--foodchain",
        action="store_true",
        help="run legacy foodchain sim instead of Culture Sort",
    )
    p.add_argument("--seed", type=int, default=12)
    p.add_argument("--agents", type=int, default=30, help="agents per run (LR mode)")
    p.add_argument("--species", choices=ROSTERS, default="phase2")
    p.add_argument("--play", action="store_true", help="foodchain player mode")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--biomes", dest="biomes", action="store_true")
    group.add_argument("--no-biomes", dest="biomes", action="store_false")
    p.set_defaults(biomes=None)
    args = p.parse_args()

    if args.foodchain:
        if args.biomes is None:
            args.biomes = args.play
        cfg = SimConfig(seed=args.seed, species=list(ROSTERS[args.species]))
        if args.biomes:
            cfg.terrain_forest_frac = DEFAULT_FOREST_FRAC
            cfg.terrain_water_frac = DEFAULT_WATER_FRAC
        return "foodchain", cfg, args.play

    return "lr", LRConfig(seed=args.seed, total_agents=args.agents), False


async def main() -> None:
    print(f"[lr] platform={sys.platform} browser={IS_BROWSER}", flush=True)
    if IS_BROWSER:
        mode, cfg, play = "lr", _browser_config(), False
    else:
        mode, cfg, play = _native_config()
    print(f"[lr] starting mode={mode}", flush=True)
    if mode == "lr":
        await LRApp(cfg).run()
    else:
        await FoodchainApp(cfg, play=play).run()


if __name__ == "__main__":
    asyncio.run(main())