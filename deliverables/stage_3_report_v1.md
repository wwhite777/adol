# Stage 3 report v1 — adol / KYRA-Bench (2026-09-22): phase-A infrastructure complete, item bank complete, runs pending the PI's item sign-off

## Process (rules v3.2 §14.4)
Conductor: Claude Code, Fable 5.1, effort max throughout (the PI kept the session; a fresh session at high was recommended for the build phase). Coders (Opus 5, high), one card each, receipts re-verified by the conductor: vLLM provider (two cards), items builder + gate (two cards), judge runner + panel (one card + three follow-ups), analysis package (one card + one follow-up), G6 + campaign (one card + three follow-ups). Scouts: none today. Auditor: none (phase A waiver). Full test suite run by the conductor at the end: 315 tests, OK.

## What exists now (all committed locally)
- Frozen protocol: PREREGISTERED_kyra_v2.yaml (sha256 87abaae4…), CONTRIBUTION_CONTRACT v2, CLAIM_LEDGER v2; pre-data pinnings logged (prefix-view judging; direct over-refusal field; bootstrap interaction p; N2 on the rate scale; repeat seeds; non-cumulative critical-by-depth; N1.2 power expectation).
- Item bank: 6 groups × (6 single + 6 multi), 36 literal/localized pairs, 24 long-horizon scripts with gate-matched benign twins, 24 lexical contrasts → research/items/items_phaseA_v1.jsonl (156 items, sha 8ab7cda1…), stratification table; PI review sheet (72 items).
- Pipeline: src/kyra — schema, runner (conditions/temperature/seed, MARKER on validation), VLLMProvider (effective params + chat-template hash in the manifest), items builder + fail-closed design gate (+ diagnose), judge (prefix views, control fields, anchors, item-coverage guard), panel (LOFO, median, conservative tie, per depth), analysis package (N1/N2/N3/transitions/Pareto with known-answer fixtures), G6 (frozen-hash check, coded rules asserted against the YAML, producer field names), campaign run + score steps (disk/GPU guards, freeze check, repeats, EXPERIMENTS rows, coverage and overwrite guards, anchors provenance); src/gates freeze/verify. Judge prompt v0.2 + anchors v1.
- Evidence of function (all class smoke, never evidence): vLLM smoke run (EXAONE-4.0-1.2B, GPU 1, MARKER); judge probes J0/J0b/J0c (parse errors 57 % → 0 % at final view; prefix views 21 % on the 1.2B, depth-driven); chain probe 2: two judge instances → panel (14 per-depth records, 4 control views with over_refusal) → transitions/Pareto/n3 on real records; G6 fixtures for every aggregate; tamper → exit 6.

## Findings that changed the design before any data (all logged)
1. Panel v0 scored D1–D6 once per conversation → per-turn definitions were uncomputable → prefix-view judging.
2. Schema example zeros were copied by a weak judge as "valid" scores → non-degenerate illustrative example, no-copy rule, rationale first.
3. Benign twins matched by eye failed the token/request gate on 39 turns → coder-matched under the rule, every rewrite reviewed.
4. D3 = 0 is "complied with harm", not "refused" → direct over_refusal/helpfulness fields for controls.
5. VB p-values optimistic → cluster-bootstrap interaction p; bootstrap CIs are the interval of record.
6. Scoring against the wrong item file silently dropped control status → coverage guards in campaign and judge; a missing EXPERIMENTS row is refused rather than guessed.

## What remains before runs
[PI] item review sign-off; HF license choice (HyperCLOVA X SEED) or Kanana; model shortlist within ~25 GB free (research/models_phaseA_v1.json; 4-bit variants for 27–32B classes; one checkpoint at a time); then `campaign run` (class confirmatory after the freeze check) and `campaign score` with three family-disjoint judges; then analysis → G6 → ledger → figures → Korean manuscript.

## Disclosures
r004 waived; sensitive item groups at pattern level; all probes labeled smoke; one stale test (runner default) fixed by the conductor after the full suite exposed it; coders' scope deviations accepted and listed in handoff.md; disk 25 GB free on the shared volume; no jobs running.
