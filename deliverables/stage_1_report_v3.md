# Stage 1 report v3 — adol / KYRA-Bench (2026-09-22; supersedes v2 of 2026-09-21)

## Process (rules v3.2 §14.4)
Conductor Claude Code, Fable 5.1, effort max. Delegated today: one `coder` (Opus 5, high) — freeze gate + hash verifier, receipt re-verified by the conductor with planted violations. Auditor: Codex (GPT-6), round r003 (PI-authorized). No scouts today.

## What happened
1. PI approved VERDICT r002 decisions 1–6 ("decisions 1-6 all approved. open r003 and proceed"); operationalization logged in DECISION_LOG.md.
2. r003 (tag audit/kyra-r003) verified F-r002-2 (ROK numbers), F-r002-3 (CogManip precedent + baseline inclusion) and F-r002-4 (four precision items) against the PDFs, but returned **FAIL** for the record/pitch prose: F-r003-1 (two surviving KIDBench exclusions in synthesis prose — major), F-r003-2 (controls guideline required twins for only 12/48 scripts, no length/information matching, no control CRRI scoring, no separate response-level reference — major), F-r003-3 (K-Bench acceptance-logic wording — minor), F-r003-4 (added baselines presented as ruling out recency/single-event explanations — major), F-r003-5 (CogManip "adults" unsupported — minor), F-r003-6 (stale status language — minor), plus four propagation gaps (refusal-only baseline, grouping rule, risk coverage in the judge gate, transition-count primary reporting). "PI decisions still required: none."
3. All corrected the same day: NOVELTY_MATRIX v4; REJECT_MEMO; evidence record; CRRI_SPEC (operationally defined comparators incl. refusal-only, recency λ = 0.5, dialogue-level axis intensity, turn count; inference limited — no accumulation guarantee; grouping rule; judge gate per language/age/risk with CI lower bound ≥ 0.80; transition counts primary; hazard = representation); safe_controls_guideline §3 (twin per escalation script 48/72, ±20% token and equal-request matching, control CRRI scoring, benign-request vs benign-response reference labels); PREREGISTERED_kyra_v1.yaml (definitions.controls, comparator_inference, grouping_rule, judge_gate). ISSUES.csv: 18 rows.
4. S2 prepared: CONTRIBUTION_CONTRACT.md v1 (primary N1 with conjuncts N1.1–N1.5; supporting N2–N4; H4/H7/H8 registered secondaries; thresholds; baselines; splits; statistics; interim-look rule; kill rules; judge gate; null path; separate endpoints; forbidden wording; definitions), PREREGISTERED_kyra_v1.yaml (13 claims, one top-level primary, three supporting), CLAIM_LEDGER.md. Freeze gate src/gates/freeze.py (fail-closed: parse 2 / schema 3 / contract 4 / write 5; receipt written and re-read by the gate itself) + verify_freeze.py (exit 6 on mismatch), 18 tests, 9 fixtures; conductor's planted violations refused. Pre-check of the real files against the freeze conditions passes. NOT frozen: by decision 4 the freeze follows a passing record.

## Gate status
S1 remains awaiting_pi on process: the corrected record needs auditor PASS/EDITORIAL (r004, packaged in audit/r004/, not launched — a further self-initiated round is barred by rules 12.4) or a PI waiver. On pass: S1 completed → freeze → S2 completed → PI registers on OSF.

## Disclosures
r003 FAIL was on my prose/propagation, not on re-checked facts; two "corrections" had left the original contradictory sentences in place. No freeze receipt exists; the coder's informational hash (72671d66…) predates today's YAML edits and is not a freeze. No jobs running.

## Instruction conflicts
None. ("proceed" read as continue-to-gate, not as authorization for further self-initiated audit rounds.)
