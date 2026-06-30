"""Generate an itch.io cover image (630×500 recommended; we output 1260×1000
for retina) from a live game state. Runs the sim deterministically from a
fixed seed so the image is reproducible.

Output:
    cover.png            — 1260×1000, for itch cover
    banner.png           — 960×300,  for itch banner

Re-run whenever the look of the game changes:
    python scripts/make_cover.py
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")     # headless surface

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame
pygame.init()

from foodchain.sim import SimConfig, World
from foodchain.sim.config import PHASE2_SPECIES
from foodchain.render.pygame_view import (
    BG, GRASS, FOREST, WATER, PLAYER_COLOR, PLAYER_RING, TERRAIN_COLORS,
)

TITLE_COLOR = (255, 240, 120)
SUB_COLOR = (180, 180, 200)


def build_world(seed: int, warmup_ticks: int) -> World:
    cfg = SimConfig(
        seed=seed,
        species=list(PHASE2_SPECIES),
        terrain_forest_frac=0.22,
        terrain_water_frac=0.06,
    )
    w = World(cfg)
    w.place_player()
    for _ in range(warmup_ticks):
        w.step()   # let ecology develop; player idles (not moving) meanwhile
    return w


def draw_world(surface: pygame.Surface, w: World, cell: int,
               origin: tuple[int, int]) -> None:
    gx, gy = origin
    grid_w = w.cfg.width * cell
    grid_h = w.cfg.height * cell
    pygame.draw.rect(surface, (30, 30, 36), (gx, gy, grid_w, grid_h))
    for c, kind in w.terrain.items():
        color = TERRAIN_COLORS.get(kind)
        if color is None:
            continue
        x, y = c
        pygame.draw.rect(surface, color, (gx + x * cell, gy + y * cell, cell, cell))
    for (x, y) in w.grass:
        pygame.draw.rect(surface, GRASS, (gx + x * cell, gy + y * cell, cell, cell))
    for a in w.animals:
        color = w.species_defs[a.species].color
        inset = max(1, cell // 10)
        pygame.draw.rect(
            surface, color,
            (gx + a.x * cell + inset, gy + a.y * cell + inset,
             cell - 2 * inset, cell - 2 * inset),
        )
    if w.player is not None:
        p = w.player
        px, py = gx + p.x * cell, gy + p.y * cell
        inset = max(2, cell // 8)
        pygame.draw.rect(
            surface, PLAYER_COLOR,
            (px + inset, py + inset, cell - 2 * inset, cell - 2 * inset),
        )
        pygame.draw.rect(surface, PLAYER_RING, (px, py, cell, cell), max(2, cell // 12))


def load_font(size: int, bold: bool = False) -> pygame.font.Font:
    try:
        f = pygame.font.SysFont("menlo,monospace,courier", size, bold=bold)
        if f is not None:
            return f
    except Exception:
        pass
    return pygame.font.Font(None, size)


def render_cover(out_path: Path, size: tuple[int, int] = (1260, 1000)) -> None:
    """Zoomed-in crop around the player so thumbnails read clearly."""
    W, H = size
    w = build_world(seed=12, warmup_ticks=60)

    surface = pygame.Surface((W, H))
    surface.fill(BG)

    # Crop window (in world cells) and cell render size.
    CROP_W, CROP_H = 32, 22
    CELL = 36
    grid_w = CROP_W * CELL
    grid_h = CROP_H * CELL
    gx = (W - grid_w) // 2
    gy = 50

    # Centre the crop on the player with toroidal wrap.
    px, py = w.player.pos
    cx_origin = px - CROP_W // 2
    cy_origin = py - CROP_H // 2

    pygame.draw.rect(surface, (30, 30, 36), (gx, gy, grid_w, grid_h))
    for dy in range(CROP_H):
        for dx in range(CROP_W):
            wx = (cx_origin + dx) % w.cfg.width
            wy = (cy_origin + dy) % w.cfg.height
            cell = (wx, wy)
            rx = gx + dx * CELL
            ry = gy + dy * CELL

            kind = w.terrain.get(cell)
            if kind in TERRAIN_COLORS:
                pygame.draw.rect(surface, TERRAIN_COLORS[kind], (rx, ry, CELL, CELL))
            if cell in w.grass:
                pygame.draw.rect(surface, GRASS, (rx, ry, CELL, CELL))

            occ = w.occupied.get(cell)
            if occ is None:
                continue
            if occ is w.player:
                inset = CELL // 6
                pygame.draw.rect(surface, PLAYER_COLOR,
                                 (rx + inset, ry + inset,
                                  CELL - 2 * inset, CELL - 2 * inset))
                pygame.draw.rect(surface, PLAYER_RING,
                                 (rx, ry, CELL, CELL), 3)
            else:
                color = w.species_defs[occ.species].color
                inset = CELL // 8
                pygame.draw.rect(surface, color,
                                 (rx + inset, ry + inset,
                                  CELL - 2 * inset, CELL - 2 * inset))

    title_font = load_font(84, bold=True)
    sub_font = load_font(26)
    title = title_font.render("FOOD CHAIN", True, TITLE_COLOR)
    sub = sub_font.render("climb the chain. don't become a meal.", True, SUB_COLOR)
    title_y = gy + grid_h + 24
    surface.blit(title, title.get_rect(centerx=W // 2, top=title_y))
    surface.blit(sub, sub.get_rect(centerx=W // 2, top=title_y + title.get_height() + 6))

    pygame.image.save(surface, str(out_path))
    print(f"wrote {out_path}  ({W}×{H})")


def render_banner(out_path: Path, size: tuple[int, int] = (1920, 600)) -> None:
    """Wide banner, title on the left, game vignette on the right.
    itch.io wants 960×300; we double it for retina."""
    W, H = size
    w = build_world(seed=12, warmup_ticks=60)

    surface = pygame.Surface((W, H))
    surface.fill(BG)

    cell = (H - 40) // w.cfg.height
    grid_w = cell * w.cfg.width
    grid_h = cell * w.cfg.height
    grid_origin = (W - grid_w - 40, (H - grid_h) // 2)
    draw_world(surface, w, cell, grid_origin)

    title_font = load_font(120, bold=True)
    sub_font = load_font(36)
    title = title_font.render("FOOD CHAIN", True, TITLE_COLOR)
    sub = sub_font.render("a turn-based survival roguelike", True, SUB_COLOR)

    tx = 60
    ty = (H - title.get_height() - sub.get_height() - 20) // 2
    surface.blit(title, (tx, ty))
    surface.blit(sub, (tx, ty + title.get_height() + 14))

    pygame.image.save(surface, str(out_path))
    print(f"wrote {out_path}  ({W}×{H})")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    render_cover(root / "cover.png")
    render_banner(root / "banner.png")
