# Synthetic claim contract (gate fixture) — omits one forbidden phrase

Version: 1.0

SYNTHETIC fixture: pairs with reject_contract_forbidden.yaml, whose
forbidden_wording list has three entries. The third entry is missing below,
so the gate must refuse with exit 4. (That phrase is deliberately absent from
this whole file, comments included.)

## Claims
- N1 (primary): toy metric A increases from condition 1 to condition 3.
- N2 (supporting): toy index B adds discrimination over the toy baseline.

## NOT-claims (forbidden wording, verbatim)
- "first toy benchmark of its kind"
- "guaranteed toy safety"
