# REJECT_MEMO.md — adol / KYRA-Bench (S1 prosecution, v2, 2026-09-21; v1 preserved as REJECT_MEMO_v1_2026-09-16.md)
Prosecutor's five questions, now answered from FULL TEXTS (research/sweeps/fulltext_extraction_2026-09-21.md) rather than abstracts. Corrections to v1 are marked ▲.

## Q1 — Already done?
Yes, for every component taken alone, and the full texts made this stronger than v1 said:
- ▲ Matched literal-vs-adapted safety evaluation INCLUDING KOREAN is established: Culturally-Adapted Red-Teaming (1:1 seed-matched DT/CA, KO +9.1 pp ΔASR; PDF carries an ICML 2026 proceedings line), ROK-FORTRESS (4-way transcreation matrix, Δling ≈ 10 pp), KSAFE-MM (translation vs contextualized). v1 called H3 "not found anywhere" — wrong; it is a replication in a new domain.
- ▲ Turn-level collapse AND recovery are counted in TAF-MED (§4.1, transition matrices); gate retreat/rebuild dynamics in CompanionBench; accumulation curves in TSJ. Only the hazard-model REPRESENTATION with recovery in the youth relational domain is absent — a representation, not a phenomenon.
- ▲ Human-anchored judging is standard: at least nine of the sixteen full texts report judge/classifier-vs-human statistics (TSJ κw 0.790; TAF-MED κ 0.895; K-Bench 94.2% vs consensus; CAREBench κ 0.55; SproutBench κ 0.78; KSAFE-MM κ 0.62; ROK-FORTRESS best panel κ 0.736 — its 0.874 is human–human [corrected after r002]; CultureConverse 90.1% ±1; Persona-Grounded 86.8% accuracy). The metrics, references and units differ — none of these inequalities is by itself an acceptance gate.
- ▲ (r002) KIDBench already runs benign dialogues through the same 5-turn simulation (equal-turn benign comparison) and its rubric scores secrecy encouragement; CogManip already has human-scored, trajectory-aware manipulation measurement with a user-independence outcome (MRI). Each narrows a component claim further.
- ▲ CRRI's four axes have named single-turn cousins in CAREBench (Social Isolation Reinforcement, Anti-Referral Pressure, Luring & Target Isolation), INTIMA (Isolation, Retention), TSJ (Emotional Dependence domain).
- Still not found in any full text read: (a) predictive/incremental validity of a CUMULATIVE multi-turn index against an independent practitioner global criterion on held-out scenarios and models; (b) Korean-language adolescent (12–17) relational/crisis conversations; (c) turn-matched benign controls. These are proposals.

## Q2 — Unimportant?
Policy demand stands (plan-cited figures; re-verify before citation). Importance to an international venue now rests almost entirely on (a) above — the H5/H6 measurement result — and on the honesty of the replication framing for H3/H7. If H5 nulls, what remains is a well-validated bilingual instrument + a preregistered null: publishable lower on the ladder, and the PI must say in advance whether that is acceptable (VERDICT r001 item 5).

## Q3 — Module combination?
The dominant risk, sharpened: judge panel (CompanionBench/K-Bench) + simulated-minor multi-turn (KIDBench/ChildSafe/TSJ) + youth taxonomy (CAREBench) + DT/CA pairs (Culturally-Adapted Red-Teaming) + XSTest controls, in Korean = assembly. Only a substantive H5/H6 result escapes this classification; S2 must freeze it as the primary claim with the bank as supporting.

## Q4 — Benchmark extension?
The 480-item Korean bank is exactly that and is the ETRI deliverable; the paper must lead with validation results. Forbidden wording is consolidated in NOVELTY_MATRIX.md §D.

## Q5 — Trivial explanation?
1. Turn-count/context-length confound for H1 → item-paired lexical benign twins of each escalation script, matched on turns and as far as feasible on length/informational demand (manual/safe_controls_guideline_v1.md §3; new H1.3) — required at S2. ▲ Equal-turn benign trajectories per se are KIDBench's (Tab.17); the item pairing is what we add.
2. Rater halo for CRRI-vs-criterion → separate criterion raters, blind to axis scores and model identity; judge family-bias check (leave-one-family-out).
3. ▲ Localization effect could be a translation-quality effect, not a cultural one. KSAFE-MM reports two separate comparisons (Fig.2a: +8.60 pp EN→translated KO, +0.22 pp contextualization; Tab.4: +2.7 pp on one model with 16.7% of sentences contextualized) — they show translation itself moves ASR but do NOT identify translation quality as the cause (r002 correction). Our paired design holds translation quality constant (literal twin = competent, reviewed literal translation), keeps rater/judge language fixed, and reports the rewriting-procedure effect as such — never "the effect of culture" (F-r001-4); local crisis-resource substitution is part of the treatment and may itself raise referral-quality scores, so component-wise reporting is required.
4. TSJ's ~140-turn stability result will be quoted against a ≤8-turn window → the claim is scoped to early-relationship onset + recovery, and the paper cites TSJ as the long-horizon complement.

## Disposition
Pitch v2 (NOVELTY_MATRIX.md §C) submitted to auditor recheck r002; the S1 gate decision stays with the PI (VERDICT r001 items 1–5), now with full-text evidence behind every row.
