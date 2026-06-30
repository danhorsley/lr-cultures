"""Headless runner for parameter tuning.

Run a sim for N ticks and print/write population counts per tick. No pygame,
no matplotlib required — CSV out so you can plot with whatever you like.

World-level params are exposed as CLI flags. Species rosters are data-driven
(see SimConfig.species) — for species-level sweeps, write a short Python
script that constructs a SimConfig with a custom species list and calls
run_sim() below.

Usage:
    python -m scripts.tune                               # 2000 ticks, stdout
    python -m scripts.tune --ticks 5000 --out run.csv
    python -m scripts.tune --seed 42 --grass-regrow-prob 0.03
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import fields
from pathlib import Path
from typing import Iterable, TextIO

# Allow running as `python scripts/tune.py` from repo root too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from foodchain.sim import SimConfig, World
from foodchain.sim.config import CLASSIC_SPECIES, PHASE2_SPECIES

ROSTERS = {"classic": CLASSIC_SPECIES, "phase2": PHASE2_SPECIES}

# Only simple (scalar) SimConfig fields get auto-flags.
_SCALAR_TYPES = (int, float, str, bool)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Foodchain headless sim runner")
    p.add_argument("--ticks", type=int, default=2000)
    p.add_argument("--out", type=str, default=None, help="CSV path; stdout if omitted")
    p.add_argument("--every", type=int, default=1, help="sample every N ticks")
    p.add_argument("--species", choices=ROSTERS, default="classic")
    for f in fields(SimConfig):
        if not isinstance(f.default, _SCALAR_TYPES):
            continue
        flag = "--" + f.name.replace("_", "-")
        p.add_argument(flag, type=type(f.default), default=None)
    return p


def cfg_from_args(args: argparse.Namespace) -> SimConfig:
    cfg = SimConfig(species=list(ROSTERS[args.species]))
    for f in fields(SimConfig):
        if not isinstance(f.default, _SCALAR_TYPES):
            continue
        v = getattr(args, f.name)
        if v is not None:
            setattr(cfg, f.name, v)
    return cfg


def run_sim(cfg: SimConfig, ticks: int, every: int, out: TextIO) -> None:
    world = World(cfg)
    # Exclude player — it's not part of the ecological readout.
    species_names = [s.name for s in cfg.species if s.name != "player"]
    header = ["tick", "grass"] + species_names
    writer = csv.writer(out)
    writer.writerow(header)

    def row(t: int) -> Iterable[int]:
        c = world.counts()
        return [t, c["grass"]] + [c[n] for n in species_names]

    writer.writerow(row(0))
    for t in range(1, ticks + 1):
        world.step()
        if t % every == 0 or t == ticks:
            writer.writerow(row(t))
            if all(world.counts()[n] == 0 for n in species_names):
                print(f"# all species extinct at tick {t}", file=sys.stderr)
                break


def main() -> int:
    args = build_parser().parse_args()
    cfg = cfg_from_args(args)
    out_f = open(args.out, "w", newline="") if args.out else sys.stdout
    try:
        run_sim(cfg, args.ticks, args.every, out_f)
    finally:
        if out_f is not sys.stdout:
            out_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
