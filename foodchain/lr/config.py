"""Culture Sort (L/R) — data-driven agent definitions and game config."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class AgentDef:
    """One assignable agent type. Stats are base deltas on join; interactions
    in game.py layer on type-specific rules."""

    name: str
    display_name: str
    color: Tuple[int, int, int]
    glyph: str
    lines: Tuple[str, ...]
    vitality: float = 0.0
    harmony: float = 0.0
    productivity: float = 0.0
    stability: float = 0.0


AGENT_ROSTER: Dict[str, AgentDef] = {
    "producer": AgentDef(
        name="producer",
        display_name="Producer",
        color=(80, 200, 100),
        glyph="P",
        lines=(
            "Green nurturer.",
            "+vitality to the bag.",
            "Helps resources regrow.",
        ),
        vitality=8.0,
        harmony=2.0,
        stability=3.0,
    ),
    "operator": AgentDef(
        name="operator",
        display_name="Operator",
        color=(220, 70, 70),
        glyph="O",
        lines=(
            "Red efficiency driver.",
            "+productivity.",
            "Too many alike → -harmony.",
        ),
        productivity=10.0,
        harmony=-2.0,
    ),
    "cooperator": AgentDef(
        name="cooperator",
        display_name="Cooperator",
        color=(90, 150, 240),
        glyph="C",
        lines=(
            "Team player.",
            "+harmony.",
            "Boosts similar agents.",
        ),
        harmony=9.0,
        vitality=2.0,
    ),
    "extractor": AgentDef(
        name="extractor",
        display_name="Extractor",
        color=(200, 120, 50),
        glyph="X",
        lines=(
            "High output, high cost.",
            "+productivity, -harmony.",
            "Drains others' harmony.",
        ),
        productivity=14.0,
        harmony=-6.0,
    ),
    "conformist": AgentDef(
        name="conformist",
        display_name="Conformist",
        color=(170, 170, 190),
        glyph="F",
        lines=(
            "Mirrors the dominant trait.",
            "Amplifies whatever leads.",
            "Safe but unoriginal.",
        ),
        stability=4.0,
    ),
    "disruptor": AgentDef(
        name="disruptor",
        display_name="Disruptor",
        color=(240, 200, 60),
        glyph="D",
        lines=(
            "Chaos agent.",
            "Big random swing.",
            "Can help or hurt.",
        ),
    ),
    "stabilizer": AgentDef(
        name="stabilizer",
        display_name="Stabilizer",
        color=(100, 200, 200),
        glyph="S",
        lines=(
            "Calms extremes.",
            "Pulls stats toward balance.",
            "+stability.",
        ),
        stability=8.0,
        harmony=3.0,
    ),
}


@dataclass
class LRConfig:
    seed: int = 12
    total_agents: int = 30
    initial_stat: float = 50.0
    roster: List[AgentDef] = field(
        default_factory=lambda: list(AGENT_ROSTER.values())
    )