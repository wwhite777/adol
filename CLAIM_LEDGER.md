# CLAIM_LEDGER.md — adol / KYRA-Bench (opened at S2, 2026-09-22; rows keyed to PREREGISTERED_kyra_v1.yaml)
Columns: ID | scoped text / type | falsifier | inference unit | protocol | raw run/source paths | analysis command | figure/table | destructive test / result | scientific outcome | audit status. Rejected or superseded rows are preserved, never deleted.

| ID | scoped text / type | falsifier | unit | protocol | raw paths | analysis command | figure/table | destructive test / result | scientific outcome | audit status |
|---|---|---|---|---|---|---|---|---|---|---|
| N1 | CRRI predicts senior-practitioner global failure better than every trivial and transcript-aware baseline on held-out scenarios (primary; concurrent criterion validity) | N1.2 or N1.3 FAIL | conversation; cluster = scenario | PREREGISTERED_kyra_v1 (freeze pending r003) | result/raw/<T1 cohort>/ (not yet run) | src/analysis/h5_auc.py (to build) | Fig 6 ROC/PR + calibration | shuffle criterion labels within scenario → AUC ≈ 0.5 (planned) | pending | pending (r003 open on S1 evidence) |
| N1.1 | held-out AUC ≥ 0.80 | CI upper < 0.80 | conversation | same | — | same | Fig 6 | — | pending | pending |
| N1.2 | ΔAUC vs final-turn ≥ 0.05, Holm-adj p < 0.05 | Δ CI upper ≤ 0 | conversation | same | — | same | Tab (baselines) | — | pending | pending |
| N1.3 | ΔAUC vs refusal-only ≥ 0.05 | Δ CI upper ≤ 0 | conversation | same | — | same | Tab | — | pending | pending |
| N1.4 | ΔAUC vs transcript-aware strategy-sum ≥ 0.05 | Δ CI upper ≤ 0 | conversation | same | — | same | Tab | recency-only check (fallback) | pending | pending |
| N1.5 | no other baseline significantly beats CRRI | any baseline Δ CI upper ≤ 0 | conversation | same | — | same | Tab | — | pending | pending |
| N2 | generalization to 2 held-out models and both age bands (supporting) | N2.1 or N2.2 FAIL | conversation | same; external run 2027-02 | — | src/analysis/h6_external.py (to build) | Fig 6 held-out panel | — | pending | pending |
| N2.1 | AUC drop ≤ 0.05 on held-out models | drop CI lower > 0.05 | conversation | same | — | same | — | — | pending | pending |
| N2.2 | per-age-band AUC ≥ 0.75 | either CI upper < 0.75 | conversation | same | — | same | supp. fig | DIF exploration (exploratory) | pending | pending |
| N3 | critical failure rises 1→3→6 turns in risk scenarios, not comparably in benign twins (supporting) | N3.1 or N3.2 FAIL | conversation; GLMM scenario RE | same; Arm A long-horizon 48 (+72 trigger) | — | src/analysis/h1_glmm.py (to build) | Fig 4 boundary-survival | length-only control = N3.2 | pending | pending |
| N3.1 | OR(6 vs 1) ≥ 1.6, CI excl. 1 | OR CI upper ≤ 1.2 | conversation | same | — | same | Fig 4 | — | pending | pending |
| N3.2 | benign twins OR ≤ 1.2 or risk×turn interaction significant | benign OR ≥ 1.6 (CI excl. 1) and interaction n.s. | conversation | same | — | same | Fig 4 inset | — | pending | pending |
| N4 | localized − literal paired difference in critical-failure rate, |Δ| ≥ 0.03, CI excl. 0; components reported (supporting; replication) | TOST equivalence ±0.03 | pair (item × model) | same; 72 twin pairs × 5 models | — | src/analysis/h3_paired.py (to build) | supp. paired plot | component ablation (context vs crisis-resource substitution) | pending | pending |
| SEC-H4 | safety–over-refusal Pareto (registered secondary; descriptive) | — | model | same | — | — | Fig 5 | — | not a claim | — |
| SEC-H7 | age-cue explicit/implicit (registered secondary; replication of KIDBench in 12–17 Korean) | — | conversation | same | — | — | supp. | — | not a claim | — |
| SEC-H8 | T1/T2 drift (registered secondary) | — | model | same; T2 2027-02 | — | — | supp. | — | not a claim | — |
