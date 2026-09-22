# Synthetic claim contract (gate fixture) — version disagrees

Version: 2.0

SYNTHETIC fixture: pairs with good_prereg.yaml, which declares version "1.0".
Claim ids and forbidden wording agree; only the version differs, so the gate
must refuse with exit 4.

## Claims
- N1 (primary): toy metric A increases from condition 1 to condition 3.
- N2 (supporting): toy index B adds discrimination over the toy baseline.

## NOT-claims (forbidden wording, verbatim)
- "first toy benchmark of its kind"
- "guaranteed toy safety"
