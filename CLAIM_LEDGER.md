# CLAIM_LEDGER.md — adol / KYRA-Bench (v2, 2026-09-22; rows keyed to PREREGISTERED_kyra_v2.yaml — reduced design under option C). v1 rows (full design, N1 = CRRI criterion validity) are preserved below as SUPERSEDED, never deleted.
Columns: ID | scoped text / type | falsifier | inference unit | protocol | raw run/source paths | analysis command | figure/table | destructive test / result | scientific outcome | audit status.

## Active rows (phase A)
| ID | scoped text / type | falsifier | unit | protocol | raw paths | analysis command | figure/table | destructive test / result | scientific outcome | audit status |
|---|---|---|---|---|---|---|---|---|---|---|
| N1 | critical failure rises 1→3→6 turns in risk scripts, not explained by length (primary, H1) | N1.1 FAIL | conversation; cluster = scenario family | PREREGISTERED_kyra_v2 (frozen; receipt PREREGISTERED_kyra_v2.yaml.sha256) | result/raw/<phaseA cohort>/ (not yet run) | src/analysis/h1_glmm.py (to build) | Fig 4 turn-level transitions + survival | shuffle turn-depth labels within scenario → OR ≈ 1 (planned) | pending | waived (domestic venue; PI 2026-09-11 rule) — self-checks only |
| N1.1 | OR(6 vs 1) ≥ 1.6, CI excl. 1 | OR CI upper ≤ 1.2 | conversation | same | — | same | Fig 4 | — | pending | waived |
| N1.2 | benign twins OR ≤ 1.2 or risk×turn interaction significant | benign OR ≥ 1.6 (CI excl. 1) and interaction n.s. | conversation | same | — | same | Fig 4 inset | length-only control | pending | waived |
| N2 | localized − literal paired difference in critical-failure rate, |Δ| ≥ 0.03, CI excl. 0; components reported (supporting; replication) | TOST ±0.03 | pair (item × model) | same; 36 pairs × 5 models | — | src/analysis/h3_paired.py (to build) | paired plot | component ablation | pending | waived |
| N3 | 3-judge panel reliable (AC2 ≥ 0.70 per dim, flag agreement ≥ 0.80) with leave-one-family-out consistency (supporting) | N3.1 or N3.2 FAIL | response (dimension scores) | same | — | src/analysis/judge_reliability.py (to build) | Tab (reliability) | drop one judge → recompute | pending | waived |
| N3.1 | AC2 ≥ 0.70 every dim; flag agreement ≥ 0.80 | any dim CI upper < 0.70 after one revision | response | same | — | same | Tab | — | pending | waived |
| N3.2 | leave-one-family-out change ≤ 0.10 per dim | any change > 0.20 | response | same | — | same | Tab | — | pending | waived |
| SEC-H4 | safety–over-refusal Pareto (descriptive) | — | model | same | — | — | Fig 5 | — | not a claim | — |
| SEC-CRRI | CRRI descriptive distributions; first-failure turn; immediate/eventual recovery counts; censoring (descriptive) | — | conversation | same | — | — | Fig 4 / supp | — | not a claim (validity = phase B) | — |

## Superseded rows (v1 full design, 2026-09-22 morning; never frozen)
| ID | scoped text / type | status |
|---|---|---|
| v1-N1 (+N1.1–N1.5) | CRRI concurrent criterion validity vs senior-practitioner global judgment on held-out scenarios; ΔAUC ≥ 0.05 vs final-turn, refusal-only, transcript-aware; AUC ≥ 0.80 | SUPERSEDED — deferred to phase B as a pre-declared amendment (needs co-author double rating); no phase A claim |
| v1-N2 (+N2.1–N2.2) | generalization to 2 held-out models and both age bands | SUPERSEDED — no held-out models in phase A |
| v1-N3 | escalation with length control (now N1) | carried into v2 as N1 |
| v1-N4 | localization replication (now N2) | carried into v2 as N2 |
