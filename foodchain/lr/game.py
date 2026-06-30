"""Culture Sort (L/R) — bag/culture simulation. No pygame."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from foodchain.lr.config import AgentDef, LRConfig

_STAT_LABELS = {
    "vitality": "Vitality",
    "harmony": "Harmony",
    "productivity": "Productivity",
    "stability": "Stability",
}


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


@dataclass
class BagStats:
    vitality: float = 50.0
    harmony: float = 50.0
    productivity: float = 50.0
    stability: float = 50.0

    def copy(self) -> "BagStats":
        return BagStats(
            vitality=self.vitality,
            harmony=self.harmony,
            productivity=self.productivity,
            stability=self.stability,
        )

    def apply(self, vit=0.0, har=0.0, prod=0.0, stab=0.0) -> None:
        self.vitality = _clamp(self.vitality + vit)
        self.harmony = _clamp(self.harmony + har)
        self.productivity = _clamp(self.productivity + prod)
        self.stability = _clamp(self.stability + stab)

    def delta_from(self, before: "BagStats") -> Dict[str, float]:
        return {
            "vitality": self.vitality - before.vitality,
            "harmony": self.harmony - before.harmony,
            "productivity": self.productivity - before.productivity,
            "stability": self.stability - before.stability,
        }

    def net_change(self, before: "BagStats") -> float:
        d = self.delta_from(before)
        return d["vitality"] + d["harmony"] + d["productivity"] + d["stability"]

    def as_dict(self) -> Dict[str, float]:
        return {
            "vitality": self.vitality,
            "harmony": self.harmony,
            "productivity": self.productivity,
            "stability": self.stability,
        }


@dataclass
class AssignmentFeedback:
    side: str
    bag_label: str
    agent_key: str
    agent_display: str
    events: List[str]
    stat_deltas: Dict[str, float]
    trait_label: str
    net_positive: bool


@dataclass
class Bag:
    label: str
    agents: List[str] = field(default_factory=list)
    stats: BagStats = field(default_factory=BagStats)
    collapsed: bool = False

    def trait_label(self) -> str:
        if self.collapsed:
            return "Collapsed"
        s = self.stats
        if s.harmony < 25:
            return "Unstable"
        if s.vitality < 25:
            return "Wilting"
        lead = self.dominant_trait()
        labels = {
            "harmony": "Cooperative",
            "productivity": "Competitive",
            "vitality": "Thriving",
            "stability": "Stable",
        }
        return labels.get(lead, "Emerging")

    def culture_line(self) -> str:
        if self.collapsed:
            return "collapsed"
        label = self.trait_label()
        if label in ("Unstable", "Wilting", "Collapsed"):
            return label.lower()
        return f"{label.lower()} culture"

    def dominant_trait(self) -> str:
        s = self.stats
        return max(
            ("vitality", s.vitality),
            ("harmony", s.harmony),
            ("productivity", s.productivity),
            ("stability", s.stability),
            key=lambda x: x[1],
        )[0]

    def count_type(self, name: str) -> int:
        return sum(1 for a in self.agents if a == name)


def _fmt_delta(stat: str, amount: float) -> str:
    sign = "+" if amount >= 0 else ""
    return f"{sign}{int(round(amount))} {_STAT_LABELS[stat]}"


def _largest_deltas(
    before: BagStats, after: BagStats, n: int = 2
) -> List[Tuple[str, float]]:
    d = after.delta_from(before)
    ranked = sorted(d.items(), key=lambda x: abs(x[1]), reverse=True)
    return [(k, v) for k, v in ranked if abs(v) >= 0.5][:n]


class LRGame:
    """One incoming agent at a time; player assigns L or R."""

    def __init__(self, cfg: LRConfig):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.agent_defs: Dict[str, AgentDef] = {a.name: a for a in cfg.roster}
        self.bag_l = Bag("LEFT")
        self.bag_r = Bag("RIGHT")
        self.bag_l.stats = BagStats(
            vitality=cfg.initial_stat,
            harmony=cfg.initial_stat,
            productivity=cfg.initial_stat,
            stability=cfg.initial_stat,
        )
        self.bag_r.stats = BagStats(
            vitality=cfg.initial_stat,
            harmony=cfg.initial_stat,
            productivity=cfg.initial_stat,
            stability=cfg.initial_stat,
        )
        self.deck: List[str] = self._build_deck()
        self.round_index: int = 0
        self.current: Optional[str] = self.deck[0] if self.deck else None
        self.phase: str = "title"
        self.last_log: str = ""
        self.last_feedback: Optional[AssignmentFeedback] = None
        self.end_label: str = ""

    def _build_deck(self) -> List[str]:
        names = [a.name for a in self.cfg.roster]
        deck: List[str] = []
        while len(deck) < self.cfg.total_agents:
            deck.extend(names)
        deck = deck[: self.cfg.total_agents]
        self.rng.shuffle(deck)
        return deck

    @property
    def is_playing(self) -> bool:
        return self.phase == "playing"

    @property
    def is_finished(self) -> bool:
        return self.phase == "end"

    def start(self) -> None:
        self.phase = "playing"
        self.last_log = "assign each agent — tap left or right"

    def current_def(self) -> Optional[AgentDef]:
        if self.current is None:
            return None
        return self.agent_defs.get(self.current)

    def assign(self, side: str) -> bool:
        """Assign current agent to 'L' or 'R'. Returns False if no-op."""
        if self.phase != "playing" or self.current is None:
            return False
        bag = self.bag_l if side == "L" else self.bag_r
        agent_name = self.current
        adef = self.agent_defs[agent_name]

        before = bag.stats.copy()
        bag.agents.append(agent_name)
        feedback = self._apply_join(adef, bag, side, before)
        self.last_feedback = feedback
        self.last_log = feedback.events[0] if feedback.events else f"+{adef.display_name}"

        if bag.stats.vitality <= 0:
            bag.collapsed = True
            bag.stats.vitality = 0.0
            feedback.trait_label = "Collapsed"

        self.round_index += 1
        if self.round_index >= len(self.deck):
            self._finish()
        elif self.bag_l.collapsed or self.bag_r.collapsed:
            self._finish()
        else:
            self.current = self.deck[self.round_index]
        return True

    def _apply_join(
        self,
        adef: AgentDef,
        bag: Bag,
        side: str,
        before: BagStats,
    ) -> AssignmentFeedback:
        s = bag.stats
        events: List[str] = []
        step = s.copy()

        # Base join
        s.apply(
            vit=adef.vitality,
            har=adef.harmony,
            prod=adef.productivity,
            stab=adef.stability,
        )
        base_deltas = _largest_deltas(step, s)
        if base_deltas:
            parts = ", ".join(_fmt_delta(k, v) for k, v in base_deltas)
            events.append(f"{adef.display_name} joined → {parts}")
        else:
            events.append(f"{adef.display_name} joined the bag")
        step = s.copy()

        if adef.name == "operator":
            n = bag.count_type("operator")
            if n >= 2:
                s.apply(har=-4.0 * (n - 1), prod=2.0)
                events.append(
                    "Two Operators clashed → "
                    f"{_fmt_delta('harmony', s.harmony - step.harmony)}, "
                    f"{_fmt_delta('productivity', s.productivity - step.productivity)}"
                )
                step = s.copy()

        elif adef.name == "cooperator":
            n = bag.count_type("cooperator")
            if n >= 2:
                s.apply(har=3.0 * (n - 1), vit=1.0)
                events.append(
                    "Cooperators rallied together → "
                    f"{_fmt_delta('harmony', s.harmony - step.harmony)}"
                )
                step = s.copy()

        elif adef.name == "extractor":
            s.apply(prod=4.0)
            others = max(0, len(bag.agents) - 1)
            har_drain = 0.0
            if others:
                har_drain = -2.5 * min(others, 3)
                s.apply(har=har_drain)
            coop_n = bag.count_type("cooperator")
            prod_gain = s.productivity - step.productivity
            har_chg = s.harmony - step.harmony
            if coop_n > 0:
                events.append(
                    f"Extractor took advantage of Cooperators → "
                    f"{_fmt_delta('harmony', har_chg)}"
                )
                if prod_gain > 0.5:
                    events.append(
                        f"But boosted overall output → {_fmt_delta('productivity', prod_gain)}"
                    )
            elif prod_gain > 0.5:
                events.append(
                    f"Extractor pushed output → {_fmt_delta('productivity', prod_gain)}"
                )
            step = s.copy()

        elif adef.name == "conformist":
            trait = bag.dominant_trait()
            boost = 5.0
            if trait == "vitality":
                s.apply(vit=boost)
            elif trait == "harmony":
                s.apply(har=boost)
            elif trait == "productivity":
                s.apply(prod=boost)
            else:
                s.apply(stab=boost)
            events.append(
                f"Conformist reinforced the majority → "
                f"{_fmt_delta(trait, getattr(s, trait) - getattr(step, trait))}"
            )
            step = s.copy()

        elif adef.name == "disruptor":
            swing = self.rng.uniform(-12.0, 12.0)
            s.apply(vit=swing, har=swing * 0.8, prod=swing * 0.6)
            top = _largest_deltas(step, s, n=2)
            detail = ", ".join(_fmt_delta(k, v) for k, v in top) if top else "mixed shift"
            events.append(f"Disruptor shook up the bag → {detail}")
            step = s.copy()

        elif adef.name == "stabilizer":
            for attr in ("vitality", "harmony", "productivity", "stability"):
                val = getattr(s, attr)
                pull = (50.0 - val) * 0.15
                setattr(s, attr, _clamp(val + pull))
            stab_chg = s.stability - step.stability
            events.append(
                f"Stabilizer smoothed extremes → {_fmt_delta('stability', stab_chg)}"
            )
            step = s.copy()

        elif adef.name == "producer":
            if bag.count_type("producer") >= 2:
                s.apply(vit=3.0)
                events.append(
                    f"Producers regrew resources → "
                    f"{_fmt_delta('vitality', s.vitality - step.vitality)}"
                )
                step = s.copy()
            elif adef.vitality > 0:
                events.append(
                    f"Producer added resources → {_fmt_delta('vitality', adef.vitality)}"
                )

        if len(bag.agents) > 1:
            others = bag.agents[:-1]
            sample_n = min(3, len(others))
            picks = self.rng.sample(others, sample_n)
            for other_name in picks:
                pair_events = self._pair_interact(adef.name, other_name, s, step)
                events.extend(pair_events)
                step = s.copy()

        trait = bag.trait_label()
        short_bag = "Left" if side == "L" else "Right"
        events.append(f"{short_bag} bag is now leaning {trait}")

        stat_deltas = s.delta_from(before)
        net = s.net_change(before)

        return AssignmentFeedback(
            side=side,
            bag_label=bag.label,
            agent_key=adef.name,
            agent_display=adef.display_name,
            events=events,
            stat_deltas=stat_deltas,
            trait_label=trait,
            net_positive=net >= 0,
        )

    def _pair_interact(
        self,
        a: str,
        b: str,
        stats: BagStats,
        step: BagStats,
    ) -> List[str]:
        pair = frozenset((a, b))
        adef = self.agent_defs.get(a)
        other = self.agent_defs.get(b)
        other_name = other.display_name if other else b

        if pair == frozenset(("cooperator", "cooperator")):
            stats.apply(har=2.0)
            return [
                f"Cooperators synced up → "
                f"{_fmt_delta('harmony', stats.harmony - step.harmony)}"
            ]
        if pair == frozenset(("operator", "cooperator")):
            stats.apply(prod=2.0, har=-1.0)
            return [
                f"Operator overrode {other_name} → "
                f"{_fmt_delta('productivity', stats.productivity - step.productivity)}, "
                f"{_fmt_delta('harmony', stats.harmony - step.harmony)}"
            ]
        if pair == frozenset(("extractor", "cooperator")):
            har_d = -3.0
            prod_d = 2.0
            stats.apply(har=har_d, prod=prod_d)
            return [
                f"Extractor drained {other_name} → {_fmt_delta('harmony', har_d)}",
                f"But boosted output → {_fmt_delta('productivity', prod_d)}",
            ]
        if pair == frozenset(("disruptor", "stabilizer")):
            stats.apply(stab=4.0, har=1.0)
            return [
                f"Disruptor met Stabilizer → chaos calmed, "
                f"{_fmt_delta('stability', stats.stability - step.stability)}"
            ]
        if pair == frozenset(("producer", "extractor")):
            stats.apply(vit=2.0, har=-2.0)
            return [
                f"Producer vs Extractor tug-of-war → "
                f"{_fmt_delta('vitality', 2.0)}, {_fmt_delta('harmony', -2.0)}"
            ]
        return []

    def _finish(self) -> None:
        self.phase = "end"
        self.current = None
        self.end_label = self._score_label()

    def _score_label(self) -> str:
        l_ok = not self.bag_l.collapsed
        r_ok = not self.bag_r.collapsed
        if l_ok and r_ok:
            diff = abs(
                sum(self.bag_l.stats.as_dict().values())
                - sum(self.bag_r.stats.as_dict().values())
            )
            if diff < 40:
                return "Balanced Cultures"
            return "Two Paths Diverged"
        if l_ok != r_ok:
            return "One Thriving, One Collapsed"
        return "Both Cultures Collapsed"

    def total_score(self) -> int:
        def bag_score(b: Bag) -> int:
            if b.collapsed:
                return 0
            s = b.stats
            return int((s.vitality + s.harmony + s.productivity + s.stability) / 4)

        return bag_score(self.bag_l) + bag_score(self.bag_r)

    def restart(self) -> None:
        self.__init__(self.cfg)