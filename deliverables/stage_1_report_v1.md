# Stage 1 report v1 — adol / KYRA-Bench (2026-09-16; stopped on PI order at the gate)

## Objective
Execute S1 (novelty prosecution) after D1–D4 approval, plus the approved D3/D4 drafting work.

## What ran, with evidence paths
1. **S0 closed**: DECISION_LOG.md entry quoting the PI ("D1-D4 all approved. proceed"); roles confirmed in STATE.yaml.
2. **Concurrent-work sweep (G2)**: research/sweeps/sweep_20260916.py — 16 arXiv API calls, 0 failures, dated query log (sweep_log.md). All 11 plan-cited arXiv IDs resolve with matching titles (id_verification.csv); Red Queen/XSTest/HarmBench pinned by title search (2409.17458 / 2308.01263 / 2402.04249). Scope honestly recorded: arXiv only; OpenReview/PMLR/ACL/accepted lists not queried this pass.
3. **New close works the plan (same-day v2!) missed**, found by the sweep: TSJ 2606.25396 (longitudinal cumulative companion risk in minors; stable estimates only after ~140 turns), TAF-MED 2608.10258 (61.4% collapse after safe first turn), K-Bench 2609.15855 (clinician-calibrated multi-turn crisis benchmark). Plus, surfaced by the auditor from the corpus: KSAFE-MM 2605.28013 (Korean-localized safety), AICompanionBench 2606.04867, Persona-Grounded 2605.00227.
4. **S1 artifacts**: NOVELTY_MATRIX.md (13 close + 4 foundational; pitch written AFTER the auditor lock; not-claim list), REJECT_MEMO.md (five prosecutor questions; two live trivial-explanation threats and their design countermeasures — turn-matched benign controls; early-relationship scope guard), REFERENCES.csv (21 rows with per-row verification status), SOURCE_LICENSE_REGISTRY.md (all licenses UNVERIFIED — gate before item writing).
5. **Audit round r001 (Codex, reports GPT-6)** — audit/r001/:
   - Phase A blind lock (corpus + neutral request only, no pitch existed on disk): locked TSJ, Cha et al. 2608.07902, Persona-Grounded 2605.00227; runners-up ChildSafe, CAREBench, CompanionBench, AICompanionBench, KSAFE-MM.
   - Phase B informed assessment: AUDIT_REPORT.md + **VERDICT.md = AWAITING_PI**. No outcome-changing priority defeat; novelty NOT cleared. Findings F-r001-1..7 (5 major, 2 minor) logged in research/ISSUES.csv. Headline finding: three omitted localization comparators sitting on the H3 axis — ROK-FORTRESS 2605.14152 (Korean transcreation effects), Culturally-Adapted Red-Teaming 2606.09178 (direct-translation vs adapted safety evaluation), CultureConverse 2608.28405.
6. **Power-sim reproduction**: src/power_sim.py (assumption reading pinned in header; seed 20260916) → result/power_sim/power_sim_reproduction_20260916T1001Z.csv. All 6 plan configs reproduced within ±0.033 (e.g., 48 scenarios @ OR≈2.1: 0.818 vs plan 0.85; 72: 0.957 vs 0.95). Plan's power table is credible. Caveat recorded: effects defined on the logit scale; realized marginal rates run ~0.16 vs design 0.12 — prereg must state the definition.
7. **D3 drafts (PI-side critical path)**: deliverables/ETRI_공개합의서_초안_v1.md (hybrid release, 60/40 split, canary, licenses, reviewer access, 체결 목표 10-15), deliverables/IRB_판정신청_초안_v1.md (활동 A–D 분리, 성인-전문가-완결 설계, 평정자 보호).
8. **D4 drafts**: manual/RB6D_v2_annotation_manual_draft_v1.md (행동 anchor + CF1–CF6 치명실패 목록 + CRRI 4축 턴 채점), manual/safe_controls_guideline_v1.md (어휘 매칭 + 신규 턴매칭 무해 대조 — H1 길이혼입 통제), research/CRRI_SPEC_v1.md, research/stratification_scheme_v1.md, research/PREREG_TEMPLATE_v1.md (H1.3 신설 포함), src/design/pipeline_v0_design.md.

## Gate status
S1 = awaiting_pi. The five decisions only the PI can take (VERDICT.md): ① contribution level ② measurement success + construct scope (≤8 turns) ③ causal vs paired localization claim ④ evidence threshold / conditional close ⑤ non-claims + null path. After those: reconcile the three comparators, qualify the 8 flagged matrix rows, rewrite the pitch premise, close r001, enter S2.

## Disclosures
- Own codex Phase-B process killed by explicit PID on the stop order — after both deliverables were complete; only its terminal message was cut.
- Two self-inflicted §4 violations in the Phase-B launch (trailing & inside a compound command; missing -C): tracking lost, codex started at project root, recovered itself. Lessons in memory.md + wiki verification-traps (with the crossfam 2026-09-13 recurrence note: abstract-level negative scope rows flagged again, F-r001-1).
- Blind-lock timing: pitch drafting overlapped Phase A in builder files outside the auditor's input; lock (10:03) preceded the pitch file write; auditor's report confirms corpus-only basis.
- Venue claims and VERA-MH remain unverified at source (flagged in REFERENCES.csv); G1 completes later.
- A different project's codex audit (bf) runs on this machine; untouched.

## Instruction conflicts
None identified.
