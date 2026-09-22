# Stage 2 report v1 — adol / KYRA-Bench (2026-09-22): claim contract + freeze under option C

## Process (rules v3.2 §14.4)
Conductor Claude Code, Fable 5.1, effort max. Coder (Opus 5, high): freeze gate + verifier (earlier today, conductor-verified); vLLM provider (two cards — the first stopped correctly at the disk guardrail). No scouts. Auditor: none in phase A — r004 waived by the PI's venue change (domestic journals need no cross-family audit, PI rule 2026-09-11); the S1 v4 corrections are therefore labeled auditor-unverified in every record.

## Decisions that shaped S2 (DECISION_LOG 2026-09-22)
- PI option C: domestic-first paper (JKIICE / 한국융합학회) with Q1-grade methods; phase B (optional) = co-author double rating → Q1 attempt. Dropped from phase A: OSF, ETRI 합의서, IRB, API keys, external panels and raters. $0 money; PI time ≈ 5–8 h.
- Standing rule §7 (co-author → SCI Q1) overridden by the PI's current instruction; logged.

## Frozen protocol
- CONTRIBUTION_CONTRACT.md Version: v2 (sha256 in DECISION_LOG); PREREGISTERED_kyra_v2.yaml, receipt written by src/gates/freeze.py: **87abaae4c16fb0efe3dad27ff464fcd86b6b48ff67a33f1414336ccc7ddd34a4** (2026-09-22T08:05:21Z; verify_freeze exit 0; git tag freeze/kyra-v2). v1 full-design contract/prereg preserved unfrozen as the phase B basis.
- Design: 120 items (risk 72 = 6 groups × [6 single + 6 multi]; controls 48 = 24 lexical contrasts + 24 benign twins of the 24 long-horizon scripts); 36 literal/localized pairs; 1/3/6-turn prefixes; 5 open-weight Korean-capable models; 3 open-weight judges (leave-one-family-out).
- Claims: N1 primary — escalation with the length control (OR(6 vs 1) ≥ 1.6, CI excl. 1; benign twins OR ≤ 1.2 or significant interaction); N2 — localization replication (|Δ| ≥ 0.03, CI excl. 0; TOST ±0.03 falsifier); N3 — judge reliability (AC2 ≥ 0.70 per dimension, flag agreement ≥ 0.80, leave-one-family-out change ≤ 0.10). H4 Pareto, CRRI, transitions: descriptive. Criterion validity: phase B amendment only. No interim look. Kill rules, fallback and 18 forbidden phrases in the contract.
- CLAIM_LEDGER v2 opened (v1 rows preserved as superseded).

## Verification of delegated work
Freeze gate: 18 tests; conductor's own planted violations (threshold as string → exit 3, forbidden phrase changed → exit 4) refused with no receipt; one-byte change → verify exit 6. Provider: 65 tests pass with a mocked engine; real-engine smoke pending the second card (uv install with hardlinked wheels; disk guardrail 20 GB).

## Disk finding (cross-project)
The server volume is 98 % full (38 GB free); my home is 174 GB against the 150 GB quota. The 43 GB HF cache (Qwen2.5-14B-Instruct, Llama-3.1-8B-Instruct) is protected by fusion1's handoff for its Sep 26 pilot and is reused read-only here. A home-cleanup pass (PI-gated candidates) is tabled for a separate session; phase A runs one ≤20 GB checkpoint at a time, deleted after its runs (REHYDRATE.md).

## Content started
research/items/R4_emotional_overdependence_v1.yaml — first risk group (6 single + 6 multi, 4 lexical contrasts, 4 long-horizon scripts with benign twins, literal/localized versions from English sources; pattern-level wording; failing/passing response patterns for judge anchors) — PI review sample.

## Status
S2 completed; S3 in_progress (provider proof + judge/analysis tooling), item authoring to continue in a fresh session from handoff.md.
