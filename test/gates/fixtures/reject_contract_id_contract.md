# Synthetic claim contract (gate fixture) — omits the second claim id

Version: 1.0

SYNTHETIC fixture: pairs with reject_contract_id.yaml, which declares two
top-level claims. Only the first one is listed below, so the freeze gate must
refuse with exit 4. (The omitted id is deliberately absent from this whole
file, comments included.)

## Claims
- N1 (primary): toy metric A increases from condition 1 to condition 3.

## NOT-claims (forbidden wording, verbatim)
- "first toy benchmark of its kind"
- "guaranteed toy safety"
