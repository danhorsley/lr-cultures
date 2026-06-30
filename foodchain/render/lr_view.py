"""Portrait mobile UI for Culture Sort (L/R)."""
from __future__ import annotations

import asyncio
from typing import Dict, Optional, Tuple

import pygame

from foodchain.lr.config import LRConfig
from foodchain.lr.game import AssignmentFeedback, Bag, LRGame

# Base design resolution (portrait phone). Everything scales via UI_SCALE.
BASE_W = 390
BASE_H = 780

FEEDBACK_FRAMES = 180   # ~3 s at 60 fps
FLASH_FRAMES = 90       # ~1.5 s bag highlight

BG = (14, 14, 20)
PANEL = (28, 28, 38)
PANEL_EDGE = (55, 55, 72)
TEXT = (230, 230, 240)
DIM = (130, 130, 145)
ACCENT_L = (90, 160, 255)
ACCENT_R = (255, 130, 90)
WIN = (120, 220, 140)
LOSE = (240, 100, 100)
FLASH_POS = (50, 170, 90)
FLASH_NEG = (210, 70, 70)
IMPACT_BG = (22, 26, 36)

STAT_COLORS = {
    "vitality": (80, 200, 100),
    "harmony": (100, 160, 255),
    "productivity": (240, 180, 60),
    "stability": (120, 200, 200),
}


def _safe_font(size: int, bold: bool = False) -> pygame.font.Font:
    try:
        f = pygame.font.SysFont("menlo,monospace,courier", size, bold=bold)
        if f is not None:
            return f
    except Exception:
        pass
    return pygame.font.Font(None, size)


def _scale_rect(x: float, y: float, w: float, h: float, sw: int, sh: int) -> pygame.Rect:
    return pygame.Rect(int(x * sw), int(y * sh), int(w * sw), int(h * sh))


class LRApp:
    def __init__(self, cfg: LRConfig):
        self.cfg = cfg
        self.game = LRGame(cfg)

        print("[lr] pygame.init()", flush=True)
        pygame.init()
        pygame.display.set_caption("Culture Sort")
        self.screen = pygame.display.set_mode((BASE_W, BASE_H))
        self.sw, self.sh = self.screen.get_size()
        self.ui_scale = min(self.sw / BASE_W, self.sh / BASE_H)
        self.clock = pygame.time.Clock()

        self.font_sm = _safe_font(max(12, int(14 * self.ui_scale)))
        self.font_md = _safe_font(max(16, int(18 * self.ui_scale)))
        self.font_lg = _safe_font(max(22, int(26 * self.ui_scale)), bold=True)
        self.font_xl = _safe_font(max(32, int(40 * self.ui_scale)), bold=True)
        print("[lr] LRApp ready", flush=True)

        self.feedback_frames = 0
        self.flash_frames = 0
        self.flash_side: Optional[str] = None
        self.flash_positive = True
        self.flash_deltas: Dict[str, float] = {}

    async def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self._on_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_tap(event.pos)

            self._tick_feedback()
            self._draw()
            pygame.display.flip()
            await asyncio.sleep(0)

        pygame.quit()

    def _tick_feedback(self) -> None:
        if self.feedback_frames > 0:
            self.feedback_frames -= 1
        if self.flash_frames > 0:
            self.flash_frames -= 1
            if self.flash_frames == 0:
                self.flash_side = None
                self.flash_deltas = {}

    def _trigger_feedback(self, fb: AssignmentFeedback) -> None:
        self.feedback_frames = FEEDBACK_FRAMES
        self.flash_frames = FLASH_FRAMES
        self.flash_side = fb.side
        self.flash_positive = fb.net_positive
        self.flash_deltas = dict(fb.stat_deltas)

    def _try_assign(self, side: str) -> None:
        if self.game.assign(side):
            if self.game.last_feedback is not None:
                self._trigger_feedback(self.game.last_feedback)

    def _on_key(self, key: int) -> bool:
        if key in (pygame.K_q, pygame.K_ESCAPE):
            return False
        if self.game.phase == "title":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.game.start()
            return True
        if self.game.phase == "end":
            if key in (pygame.K_r, pygame.K_RETURN, pygame.K_SPACE):
                self.game.restart()
                self.feedback_frames = 0
                self.flash_frames = 0
            return True
        if self.game.phase == "playing":
            if key in (pygame.K_LEFT, pygame.K_a):
                self._try_assign("L")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self._try_assign("R")
        return True

    def _on_tap(self, pos: Tuple[int, int]) -> None:
        x, y = pos
        if self.game.phase == "title":
            self.game.start()
            return
        if self.game.phase == "end":
            self.game.restart()
            self.feedback_frames = 0
            self.flash_frames = 0
            return
        if self.game.phase != "playing":
            return
        if y < int(0.35 * self.sh):
            return
        if x < self.sw // 2:
            self._try_assign("L")
        else:
            self._try_assign("R")

    # ------------------------------------------------------------------ draw

    def _draw(self) -> None:
        self.screen.fill(BG)
        if self.game.phase == "title":
            self._draw_title()
        elif self.game.phase == "end":
            self._draw_end()
        else:
            self._draw_play()

    def _draw_title(self) -> None:
        cx = self.sw // 2
        title = self.font_xl.render("CULTURE SORT", True, TEXT)
        self.screen.blit(title, title.get_rect(centerx=cx, top=int(0.12 * self.sh)))

        sub = self.font_md.render("L / R", True, ACCENT_L)
        self.screen.blit(sub, sub.get_rect(centerx=cx, top=int(0.20 * self.sh)))

        lines = [
            "One agent at a time.",
            "Tap left or right to build two cultures.",
            "",
            f"seed {self.cfg.seed}  ·  {self.cfg.total_agents} agents",
            "",
            "tap or press ENTER to start",
        ]
        y = int(0.32 * self.sh)
        for line in lines:
            color = DIM if line.startswith("tap") else TEXT
            surf = self.font_md.render(line, True, color)
            self.screen.blit(surf, surf.get_rect(centerx=cx, top=y))
            y += int(0.04 * self.sh)

    def _draw_play(self) -> None:
        self._draw_agent_card()
        self._draw_bag_panel(self.game.bag_l, ACCENT_L, "L", 0.0, 0.35, 0.5, 0.58)
        self._draw_bag_panel(self.game.bag_r, ACCENT_R, "R", 0.5, 0.35, 0.5, 0.58)
        if self.feedback_frames > 0 and self.game.last_feedback is not None:
            self._draw_impact_box(self.game.last_feedback)
        self._draw_log_bar()
        self._draw_progress()

    def _draw_impact_box(self, fb: AssignmentFeedback) -> None:
        alpha = min(255, int(255 * self.feedback_frames / FEEDBACK_FRAMES) + 80)
        rect = _scale_rect(0.05, 0.33, 0.90, 0.22, self.sw, self.sh)

        surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        surf.fill((*IMPACT_BG, min(alpha, 240)))
        self.screen.blit(surf, rect.topleft)
        flash_col = FLASH_POS if fb.net_positive else FLASH_NEG
        pygame.draw.rect(self.screen, flash_col, rect, 3, border_radius=12)

        pad = 12
        y = rect.top + pad
        bag_word = "Left" if fb.side == "L" else "Right"
        title = self.font_lg.render(f"{bag_word} Bag Impact", True, flash_col)
        self.screen.blit(title, (rect.left + pad, y))
        y += title.get_height() + 6

        agent_line = self.font_md.render(fb.agent_display, True, TEXT)
        self.screen.blit(agent_line, (rect.left + pad, y))
        y += agent_line.get_height() + 8

        # Show narrative lines (skip duplicate join line if crowded)
        show_events = [e for e in fb.events if "joined" not in e.lower() or len(fb.events) <= 2]
        if not show_events:
            show_events = fb.events
        for line in show_events[:4]:
            surf = self.font_sm.render(line, True, TEXT)
            self.screen.blit(surf, (rect.left + pad, y))
            y += self.font_sm.get_linesize() + 2

        # Compact delta strip
        delta_parts = []
        for key in ("vitality", "harmony", "productivity", "stability"):
            d = fb.stat_deltas.get(key, 0.0)
            if abs(d) >= 0.5:
                sign = "+" if d >= 0 else ""
                delta_parts.append(f"{key[:3].title()} {sign}{int(round(d))}")
        if delta_parts:
            delta_line = self.font_sm.render("  ".join(delta_parts), True, DIM)
            if y + delta_line.get_height() < rect.bottom - pad:
                self.screen.blit(delta_line, (rect.left + pad, rect.bottom - pad - delta_line.get_height()))

    def _draw_agent_card(self) -> None:
        rect = _scale_rect(0.06, 0.03, 0.88, 0.30, self.sw, self.sh)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=12)
        pygame.draw.rect(self.screen, PANEL_EDGE, rect, 2, border_radius=12)

        adef = self.game.current_def()
        if adef is None:
            hint = self.font_md.render("no more agents", True, DIM)
            self.screen.blit(hint, hint.get_rect(center=rect.center))
            return

        icon_r = int(min(rect.width, rect.height) * 0.22)
        icon_cx = rect.centerx
        icon_cy = rect.top + int(rect.height * 0.28)
        pygame.draw.circle(self.screen, adef.color, (icon_cx, icon_cy), icon_r)
        glyph = self.font_xl.render(adef.glyph, True, BG)
        self.screen.blit(glyph, glyph.get_rect(center=(icon_cx, icon_cy)))

        name = self.font_lg.render(adef.display_name, True, TEXT)
        self.screen.blit(name, name.get_rect(centerx=rect.centerx, top=icon_cy + icon_r + 8))

        y = icon_cy + icon_r + int(0.12 * rect.height)
        for line in adef.lines:
            surf = self.font_sm.render(line, True, DIM)
            self.screen.blit(surf, surf.get_rect(centerx=rect.centerx, top=y))
            y += self.font_sm.get_linesize()

        hint = self.font_sm.render("tap left half → L   ·   right half → R", True, DIM)
        self.screen.blit(hint, hint.get_rect(centerx=rect.centerx, bottom=rect.bottom - 8))

    def _draw_bag_panel(
        self,
        bag: Bag,
        accent: Tuple[int, int, int],
        side: str,
        x_frac: float,
        y_frac: float,
        w_frac: float,
        h_frac: float,
    ) -> None:
        pad = 0.02
        rect = _scale_rect(
            x_frac + pad, y_frac, w_frac - pad * 2, h_frac, self.sw, self.sh
        )

        flashing = self.flash_frames > 0 and self.flash_side == side
        if flashing:
            pulse = 0.5 + 0.5 * (self.flash_frames / FLASH_FRAMES)
            flash_col = FLASH_POS if self.flash_positive else FLASH_NEG
            glow = tuple(int(c * pulse) for c in flash_col)
            glow_rect = rect.inflate(8, 8)
            pygame.draw.rect(self.screen, glow, glow_rect, 4, border_radius=12)

        pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
        border_col = (
            (FLASH_POS if self.flash_positive else FLASH_NEG)
            if flashing
            else accent
        )
        pygame.draw.rect(self.screen, border_col, rect, 3, border_radius=10)

        label = self.font_lg.render(bag.label, True, accent)
        self.screen.blit(label, label.get_rect(centerx=rect.centerx, top=rect.top + 10))

        trait = bag.trait_label()
        trait_surf = self.font_md.render(f"{trait} ↑", True, TEXT)
        self.screen.blit(trait_surf, trait_surf.get_rect(centerx=rect.centerx, top=rect.top + 36))

        culture = self.font_sm.render(bag.culture_line(), True, DIM)
        self.screen.blit(culture, culture.get_rect(centerx=rect.centerx, top=rect.top + 58))

        if bag.collapsed:
            dead = self.font_md.render("COLLAPSED", True, LOSE)
            self.screen.blit(dead, dead.get_rect(center=rect.center))
            return

        icons = bag.agents[-8:]
        icon_size = max(14, int(22 * self.ui_scale))
        gap = 4
        row_w = len(icons) * icon_size + max(0, len(icons) - 1) * gap
        ix = rect.centerx - row_w // 2
        iy = rect.top + int(rect.height * 0.24)
        for name in icons:
            color = self.game.agent_defs[name].color
            pygame.draw.rect(
                self.screen, color, (ix, iy, icon_size, icon_size), border_radius=4
            )
            g = self.game.agent_defs[name].glyph
            gs = self.font_sm.render(g, True, BG)
            self.screen.blit(
                gs,
                gs.get_rect(center=(ix + icon_size // 2, iy + icon_size // 2)),
            )
            ix += icon_size + gap

        bar_left = rect.left + 12
        bar_w = rect.width - 24
        bar_h = max(10, int(14 * self.ui_scale))
        y = rect.top + int(rect.height * 0.40)
        show_deltas = flashing and self.flash_deltas
        for key in ("vitality", "harmony", "productivity", "stability"):
            val = getattr(bag.stats, key)
            delta = self.flash_deltas.get(key, 0.0) if show_deltas else 0.0
            self._draw_stat_bar(bar_left, y, bar_w, bar_h, key, val, delta)
            y += bar_h + 10

    def _draw_stat_bar(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        name: str,
        value: float,
        delta: float = 0.0,
    ) -> None:
        pygame.draw.rect(self.screen, (40, 40, 50), (x, y, w, h), border_radius=4)
        fill_w = int(w * value / 100.0)
        bar_col = STAT_COLORS[name]
        if abs(delta) >= 0.5:
            bar_col = FLASH_POS if delta > 0 else FLASH_NEG
        if fill_w > 0:
            pygame.draw.rect(self.screen, bar_col, (x, y, fill_w, h), border_radius=4)
        label = self.font_sm.render(f"{name[:4]} {int(value)}", True, TEXT)
        self.screen.blit(label, (x + 4, y - 1))
        if abs(delta) >= 0.5:
            sign = "+" if delta >= 0 else ""
            d_col = FLASH_POS if delta > 0 else FLASH_NEG
            d_surf = self.font_sm.render(f"{sign}{int(round(delta))}", True, d_col)
            self.screen.blit(d_surf, d_surf.get_rect(right=x + w - 4, centery=y + h // 2))

    def _draw_log_bar(self) -> None:
        rect = _scale_rect(0.04, 0.94, 0.92, 0.04, self.sw, self.sh)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=6)
        fb = self.game.last_feedback
        if self.feedback_frames > 0 and fb is not None:
            msg = fb.events[-1] if fb.events else self.game.last_log
        else:
            msg = self.game.last_log or "…"
        surf = self.font_sm.render(msg, True, TEXT)
        self.screen.blit(surf, surf.get_rect(midleft=(rect.left + 10, rect.centery)))

    def _draw_progress(self) -> None:
        total = self.cfg.total_agents
        done = min(self.game.round_index, total)
        txt = self.font_sm.render(f"{done} / {total}", True, DIM)
        self.screen.blit(txt, txt.get_rect(topright=(self.sw - 12, int(0.01 * self.sh))))

    def _draw_end(self) -> None:
        cx = self.sw // 2
        title = self.font_xl.render(self.game.end_label, True, WIN)
        self.screen.blit(title, title.get_rect(centerx=cx, top=int(0.08 * self.sh)))

        score = self.font_lg.render(f"score {self.game.total_score()}", True, TEXT)
        self.screen.blit(score, score.get_rect(centerx=cx, top=int(0.16 * self.sh)))

        panel_h = int(0.28 * self.sh)
        self._draw_end_bag(self.game.bag_l, ACCENT_L, int(0.06 * self.sh), panel_h)
        self._draw_end_bag(self.game.bag_r, ACCENT_R, int(0.40 * self.sh), panel_h)

        hint = self.font_md.render("tap or press R to play again", True, DIM)
        self.screen.blit(hint, hint.get_rect(centerx=cx, bottom=int(0.96 * self.sh)))

    def _draw_end_bag(
        self,
        bag: Bag,
        accent: Tuple[int, int, int],
        top: int,
        height: int,
    ) -> None:
        rect = pygame.Rect(int(0.06 * self.sw), top, int(0.88 * self.sw), height)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=10)
        pygame.draw.rect(self.screen, accent, rect, 2, border_radius=10)

        head = self.font_md.render(
            f"{bag.label} — {bag.trait_label()} ↑", True, accent
        )
        self.screen.blit(head, (rect.left + 12, rect.top + 10))

        s = bag.stats
        lines = [
            f"vitality {int(s.vitality)}   harmony {int(s.harmony)}",
            f"productivity {int(s.productivity)}   stability {int(s.stability)}",
            f"agents {len(bag.agents)}"
            + ("  (collapsed)" if bag.collapsed else ""),
        ]
        y = rect.top + 40
        for line in lines:
            surf = self.font_sm.render(line, True, TEXT)
            self.screen.blit(surf, (rect.left + 12, y))
            y += self.font_sm.get_linesize() + 4