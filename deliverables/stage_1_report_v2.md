# Stage 1 report v2 — adol / KYRA-Bench (2026-09-21; supersedes v1 of 2026-09-16)

## Process (rules v3.2 §14.4 record)
Conductor: Claude Code, Fable 5.1, effort max (PI-set). Delegated: four `scout` agents (Sonnet 5, medium, read-only) — full-text extraction of 16 papers on a fixed 9-question schema; one `coder` agent (Opus 5, high) — pipeline v0 skeleton on a task card, receipt re-verified by the conductor. Auditor: Codex (reports GPT-6), round r002. One scout card failed on an API refusal (health-safety PDF); resolved at abstract level by the conductor.

## What changed since v1
1. Evidence basis upgraded from abstracts to full texts (21 PDFs; research/sweeps/fulltext_extraction_2026-09-21.md). Four v1 negatives were overturned (TSJ expert-validated judge κw 0.790 and an Emotional Dependence domain; TAF-MED recovery counts 495/2,521; KSAFE-MM over-refusal + translation effects; CAREBench's named isolation/anti-referral constructs), and the H3 design was found to exist for Korean general safety (Culturally-Adapted Red-Teaming, 1:1 DT/CA pairs, KO +9.1 pp; ROK-FORTRESS transcreation matrix; KSAFE-MM).
2. Pitch rewritten (NOVELTY_MATRIX.md §C): a testable incremental-validity question replaces the causal premise; localization narrowed to a defined paired rewriting-procedure comparison (domain replication); within-session ≤8-turn construct with immediate/eventual/sustained recovery and censoring; endpoints separated (model over-refusal vs judge FPR with their own reference labels); transcript-aware baselines added; non-claims consolidated.
3. Audit r002 (audit/r002/out/): VERDICT = AWAITING_PI. F-r001-2/3/4/6/7 RESOLVED; F-r001-1 PARTIALLY; F-r001-5 OPEN (PI). All four numerical spot-checks the request suggested were confirmed against the PDFs. New: F-r002-1 (KIDBench runs equal-turn benign dialogues, Tab.17, and scores secrecy in Boundary-setting → our control claim narrowed to item-paired lexical twins), F-r002-2 (my record misattributed ROK's human–human κ 0.874 as judge–human; panel κ 0.736 → corrected; judge-gate inequality insufficient → common-reference gate), F-r002-3 (CogManip has human-scored, trajectory-aware manipulation measurement, MRI outcome, AI/human correlation 0.459 → added as a transcript-aware baseline candidate), F-r002-4 (precision items → corrected). All corrected in v3; auditor verification (r003) needs the PI's word.
4. Pipeline v0 skeleton: src/kyra (stdlib only; MockProvider; runner with MARKER-on-validation; judge wrapper that raises on any malformed output; crri), 31 unit tests, planted-violation and zero-item cases fail as required; smoke run recorded (never evidence).

## Residual contribution — honest classification (auditor-concurred)
(1) Korean-adolescent relational/crisis benchmark with matched controls = benchmark EXTENSION (ETRI deliverable). (2) H5/H6 — does a history-sensitive index carry incremental information about blinded practitioner global judgment on held-out scenarios/models/age bands, beyond final-turn, max, unweighted, refusal-only, CRB-count AND transcript-aware/recency competitors = the candidate IMPORTANT claim, currently a proposal. (3) Paired localization comparison = replication of an established effect in a new domain/unit. (4) Hazard + recovery = analysis representation. Importance is the PI's judgment.

## PI decision package (audit/r002/out/VERDICT.md, six items)
1 Contribution level · 2 Measurement-success contract (metric, threshold, frozen weights, holdouts, transcript-aware baseline incl. CogManip reconciliation, 8-turn failure/recovery/censoring definitions, concurrent vs prospective) · 3 Ratify paired-rewrite localization replication · 4 Evidence threshold: r003 before closing S1, or conditional S2 with F-r002 tracked · 5 Claim contract + null path · 6 NEW judge-calibration gate (common reference, critical-error limits, uncertainty, coverage, held-out).

## Disclosures
ROK κ misattribution (mine; corrected). Sonnet scout API refusal on a health-safety PDF. Conductor cannot render PDFs (pypdf in venv used). arXiv API 406 (abs pages used). Venue lines are PDF-printed only; G1 pending. Nothing under audit rounds was edited after launch; r002 input = tag audit/kyra-r002.

## Instruction conflicts
None identified.

## Status
S1 awaiting_pi. Next gate: PI decisions 1–6 (+ r003 authorization) → S1 close → S2 freeze (OSF 10-31).
