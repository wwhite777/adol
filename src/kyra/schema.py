"""Item and judge-output schemas for KYRA-Bench pipeline v0.

Field names follow research/stratification_scheme_v1.md (5 stratification axes,
twin_id / cue_variant) and manual/RB6D_v2_annotation_manual_draft_v1.md
(D1-D6, CRRI axes A1-A4, critical-failure codes CF1-CF6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

RISK_GROUPS = ("R1", "R2", "R3", "R4", "R5", "R6", "CTRL")
TURN_TYPES = ("single", "multi")
AGE_BANDS = ("12-14", "15-17")
EXPLICITNESS = ("explicit", "implicit")
LOCALIZATIONS = ("literal", "localized", "anchor_en")

D_KEYS = ("D1", "D2", "D3", "D4", "D5", "D6")
A_KEYS = ("A1", "A2", "A3", "A4")
CF_CODES = ("CF1", "CF2", "CF3", "CF4", "CF5", "CF6")

_ITEM_REQUIRED = (
    "item_id",
    "risk_group",
    "turn_type",
    "turns",
    "age_band",
    "explicitness",
    "localization",
)
_ITEM_OPTIONAL = ("cue_variant", "twin_id", "control_pair_id")
_ITEM_ALLOWED = set(_ITEM_REQUIRED) | set(_ITEM_OPTIONAL)


@dataclass(frozen=True)
class Item:
    """One benchmark item (a scenario run against one model under one condition)."""

    item_id: str
    risk_group: str
    turn_type: str
    turns: List[str]
    age_band: str
    explicitness: str
    localization: str
    cue_variant: Optional[str] = None
    twin_id: Optional[str] = None
    control_pair_id: Optional[str] = None

    def __post_init__(self) -> None:
        _check_str("item_id", self.item_id)
        _check_enum("risk_group", self.risk_group, RISK_GROUPS)
        _check_enum("turn_type", self.turn_type, TURN_TYPES)
        _check_enum("age_band", self.age_band, AGE_BANDS)
        _check_enum("explicitness", self.explicitness, EXPLICITNESS)
        _check_enum("localization", self.localization, LOCALIZATIONS)
        if not isinstance(self.turns, list) or not self.turns:
            raise ValueError(
                "item %r: 'turns' must be a non-empty list of user utterances"
                % (self.item_id,)
            )
        for i, t in enumerate(self.turns):
            if not isinstance(t, str) or not t.strip():
                raise ValueError(
                    "item %r: turns[%d] must be a non-empty string" % (self.item_id, i)
                )
        if self.turn_type == "single" and len(self.turns) != 1:
            raise ValueError(
                "item %r: turn_type 'single' requires exactly 1 turn, got %d"
                % (self.item_id, len(self.turns))
            )
        if self.turn_type == "multi" and len(self.turns) < 2:
            raise ValueError(
                "item %r: turn_type 'multi' requires at least 2 turns, got %d"
                % (self.item_id, len(self.turns))
            )
        for name in _ITEM_OPTIONAL:
            v = getattr(self, name)
            if v is not None and (not isinstance(v, str) or not v.strip()):
                raise ValueError(
                    "item %r: %s must be a non-empty string or null"
                    % (self.item_id, name)
                )

    @property
    def n_turns(self) -> int:
        return len(self.turns)


@dataclass
class JudgeRecord:
    """Parsed judge-panel output for one conversation.

    D: RB-6D dimension scores D1..D6, each 0-2.
    A: per-turn CRRI axis scores, one dict A1..A4 (each 0-2) per turn.
    critical_failure: override flag, independent of the total score.
    cf_codes: subset of CF1..CF6 justifying critical_failure.
    rationale: one-sentence justification.
    """

    D: Dict[str, int]
    A: List[Dict[str, int]]
    critical_failure: bool
    cf_codes: List[str] = field(default_factory=list)
    rationale: str = ""


def _check_str(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("field %r must be a non-empty string, got %r" % (name, value))


def _check_enum(name: str, value: Any, allowed: tuple) -> None:
    if value not in allowed:
        raise ValueError(
            "field %r must be one of %s, got %r" % (name, list(allowed), value)
        )


def item_from_dict(obj: Any, where: str = "<dict>") -> Item:
    """Build an Item from a decoded JSON object, raising ValueError on any problem."""
    if not isinstance(obj, dict):
        raise ValueError("%s: item record must be a JSON object, got %s" % (where, type(obj).__name__))
    missing = [k for k in _ITEM_REQUIRED if k not in obj]
    if missing:
        raise ValueError("%s: missing required field(s): %s" % (where, ", ".join(missing)))
    unknown = [k for k in obj if k not in _ITEM_ALLOWED]
    if unknown:
        raise ValueError("%s: unknown field(s): %s" % (where, ", ".join(sorted(unknown))))
    try:
        return Item(
            item_id=obj["item_id"],
            risk_group=obj["risk_group"],
            turn_type=obj["turn_type"],
            turns=obj["turns"],
            age_band=obj["age_band"],
            explicitness=obj["explicitness"],
            localization=obj["localization"],
            cue_variant=obj.get("cue_variant"),
            twin_id=obj.get("twin_id"),
            control_pair_id=obj.get("control_pair_id"),
        )
    except ValueError as exc:
        raise ValueError("%s: %s" % (where, exc)) from exc


def load_items(path) -> List[Item]:
    """Load items from a JSONL file. Raises ValueError on any malformed record.

    Returns [] for an empty file; callers (the runner) must treat a zero-item
    load as a hard error rather than a silent empty run.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError("items file not found: %s" % p)
    items: List[Item] = []
    seen = set()
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            where = "%s:%d" % (p, lineno)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("%s: invalid JSON (%s)" % (where, exc)) from exc
            item = item_from_dict(obj, where=where)
            if item.item_id in seen:
                raise ValueError("%s: duplicate item_id %r" % (where, item.item_id))
            seen.add(item.item_id)
            items.append(item)
    return items
