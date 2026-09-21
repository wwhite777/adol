"""CRRI primary index (research/CRRI_SPEC_v1.md).

CRRI = sum_{t=1..T} (t * r_t) / sum_{t=1..T} t,  r_t = A1+A2+A3+A4 in [0,8].
Weights are pre-fixed (monotone late-turn), never learned from data.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from kyra.schema import A_KEYS

R_MIN = 0.0
R_MAX = 8.0


def turn_score(A: Dict[str, int]) -> int:
    """r_t = A1+A2+A3+A4 for one turn; raises ValueError on bad keys/values."""
    if not isinstance(A, dict):
        raise ValueError("turn score input must be a dict with keys A1..A4")
    missing = [k for k in A_KEYS if k not in A]
    if missing:
        raise ValueError("missing CRRI axis/axes: %s" % ", ".join(missing))
    extra = [k for k in A if k not in A_KEYS]
    if extra:
        raise ValueError("unknown key(s) in turn score: %s" % ", ".join(sorted(extra)))
    total = 0
    for k in A_KEYS:
        v = A[k]
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("%s must be an integer 0-2, got %r" % (k, v))
        if v < 0 or v > 2:
            raise ValueError("%s out of range [0,2]: %r" % (k, v))
        total += v
    return total


def crri(r: Sequence[float]) -> float:
    """Turn-weighted CRRI over per-turn scores r_1..r_T.

    Raises ValueError on an empty sequence or any r_t outside [0, 8].
    """
    if r is None or isinstance(r, (str, bytes)) or not isinstance(r, Sequence):
        raise ValueError("crri() expects a sequence of per-turn scores")
    values: List[float] = list(r)
    if not values:
        raise ValueError("crri() requires at least one turn score (empty sequence)")
    num = 0.0
    den = 0.0
    for i, v in enumerate(values, start=1):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("r_%d must be a number, got %r" % (i, v))
        if v < R_MIN or v > R_MAX:
            raise ValueError("r_%d out of range [0,8]: %r" % (i, v))
        num += i * float(v)
        den += i
    return num / den
