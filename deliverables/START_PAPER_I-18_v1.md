# START PAPER brief — I-18 (+ I-19): Measuring multi-turn youth-safety judges without human raters
Written 2026-09-28 by Claude Code (Opus 5.5, adol session) from ~/repos/ideas/IDEA_LEDGER.md I-18 and I-19, on the PI's "go with A + B, start the S1 brief". Status: brief only; the project directory is opened by the paper protocol (S0), and S1 runs there.

## Identity
- Ledger IDs I-18 (core) + I-19 (second leg). Seed page ~/repos/wiki/projects/adol.md; new mechanism row "Invalid-output handling manufactures effects" in wiki/negative-results.md.
- Proposed project root: /home/wjeong/kyrameas (a new directory; adol stays the JKIICE phase-A paper). Mode B: Builder = Claude Code; Auditor = Codex (cross-family, required because this is a Q1/T1 line, not a domestic journal).
- PI constraint (2026-09-27/28): NO human raters. Validity comes from labels known by construction, invariances, and known groups.

## Seed (evidence label: quoted from adol result files; EXPOSED — motivates, cannot confirm)
- adol analysis 20260926T0213Z: benign-twin CF flag rate 1/120 → 20/120 from depth 1 to 6 (OR 9.71); 16/20 depth-6 flags were ties after one judge failed (posthoc_20260927T2328Z a_judge_validity.csv); J3 failures 23/120 benign vs 2/120 risk at depth 6, with longer judge inputs (median 14,492 vs 13,480 tokens); tie handling S1–S3 moves the risk × depth interaction from Holm p 0.204 to 0.018–0.049 (b_n1_sensitivity.csv).
- crossfam: a frozen-grammar parser changed 499/9,600 labels and flipped a gate; Phi-3.5 62% INVALID under the grammar (wiki/projects/crossfam.md).
- Confirmation needs NEW constructed data (planted and dosed sets) under a protocol frozen before collection.

## Question and value
Who needs it: anyone reporting multi-turn safety numbers from LLM judges, especially for minors, where human rating is costly or ethically heavy. What changes: (1) whether depth/length effects in judged safety are real or produced by judge failures and missing-output rules; (2) a rater-free validity battery a benchmark must pass before its numbers are reported.

## Claim shape (draft for S2; the PI fixes the central claim)
"Multi-turn LLM-judge safety measurements produce spurious depth/length effects because judge output failures rise with transcript length and missing-output rules turn them into flags; a label-free validity battery — planted violations, metamorphic tests and known-groups doses — measures and removes the artefact across ≥ 4 target models × ≥ 3 judges, without human raters."
- C1 (artefact): on planted-CLEAN views (labels clean by construction), the panel's CF-flag rate rises with depth under the tie rule and does not rise under failure-aware aggregation (invalid = missing / abstain); the difference is explained by the per-depth judge-failure rate.
- C2 (criterion by construction): panel sensitivity to a planted CF sentence at turn d and specificity on matched clean views, per judge and per aggregation rule, as functions of depth and judge-input length; the failure-aware rule is non-inferior in sensitivity (margin to fix at S2).
- C3 (metamorphic): verdict invariance under meaning-preserving edits (paraphrase of benign turns, padding with neutral turns, formatting) and directional change under a violation insertion or crisis-resource deletion; violation rates per judge.
- C4 (known groups, I-19): targets pushed by system prompts at doses 0–3 toward secrecy, exclusivity and isolation are ordered monotonically by CF rate and CRRI (Jonckheere / Spearman), and better than a length-only baseline.
- Known fact vs hypothesis: judge length/verbosity and position sensitivities are reported in the literature (to be read at S1); the hypothesis is the missing-output mechanism in multi-turn safety, plus a battery that validates without raters.

## Alternatives and mandatory baselines
- Strongest simple explanations: (i) judges are simply length-biased (verbosity bias), with failures incidental; distinguished by conditioning on failure (C1 under failure-aware aggregation). (ii) Planted sentences are trivially detectable (surface cues); distinguished by a keyword/length detector baseline and by paraphrased plants.
- Mandatory baselines: response/transcript length alone; a refusal/keyword detector; the single best judge; majority vote with invalid = missing (no tie rule); the undosed model (C4).

## Novelty risk — queries to run and date at S1 (arXiv API / OpenReview / ACL Anthology / PMLR; no hit is asserted here)
"LLM-as-a-judge verbosity bias", "judge position bias", "LLM judge robustness perturbation", "metamorphic testing LLM evaluator", "invalid output / parse failure LLM judge aggregation", "abstention LLM judge", "multi-turn safety evaluation judge length", "known-groups validity benchmark LLM", "system prompt induced unsafe persona companion evaluation", "synthetic ground truth safety judge calibration", "Korean LLM safety judge". Closest-three to be locked blind by Codex before our pitch. Forbidden wording starts with: "first rater-free", "validated judge", "proves", "guarantees", "human-level".

## Decisive test (kill pilot, ≤ one GPU-day, $0)
- Reuse the adol main-run transcripts (5 models; 24 six-turn risk scripts + 24 benign twins). Build planted sets: +1 CF sentence in the AI reply at turn d ∈ {1, 3, 6} (relational CF3/CF6-type wording only), crisis-resource deletion, and clean controls; ≈ 720 views; 3 judges (J1 Llama-3.1-8B, J2 Mistral-Small int4, J3 Phi-4 FP8), sequential decoding as pinned in adol.
- KILL if planted-CF sensitivity is flat in depth (|Δ| < 0.05 from d = 1 to 6) AND judge failure is flat in input length, or if the length/keyword baseline is within 0.05 of the panel's sensitivity.
- C4 pilot after GO: 2 target models × 4 doses × 24 relational scripts (R2/R3/R4/R6).

## Feasibility
- GPUs 1–2 (L40S; GPU 0 and 3 belong to others); sequential judging ≈ 26 s/view for J3 → ~5 GPU-h per 720 views per judge (J1/J2 faster). Target-model weights were deleted; re-download per the adol REHYDRATE recipes for C4 (disk hazard on the shared volume).
- Venv: reuse ~/envs/jeongwoncheol_adol or create ~/envs/jeongwoncheol_kyrameas at S0.

## Venue plan (verify at S1; nothing asserted)
- SCI Q1 journal in AI-evaluation / information-processing / measurement methods (candidates to verify on JCR sources per reference_journal_metrics_sources), or a T1 evaluations/benchmarks track (NeurIPS 2027 D&B; dates not announced). Authorship: with Hayoung Oh (Q1/T1 line).

## Boundaries and hazards
- Planted and dosed texts address simulated minors: relational risks only; no sexual content (R1 excluded from planting and dosing); no self-harm methods (R5 plants limited to resource deletion). Raw outputs stay private and are never published; dose prompts are described, not released.
- No human raters (PI). The paper claims validity by construction, invariance and known groups, never human-anchored accuracy.
- The adol phase-A seed numbers are exposed and cannot be reused as confirmation.
