# REJECT_MEMO.md — adol / KYRA-Bench (S1 prosecution, v1, 2026-09-16)
Prosecutor's five questions, answered against the dated sweep (research/sweeps/2026-09-16/) — including three close works the PI plan v2 (same-day) does NOT cover: TSJ (2606.25396), TAF-MED (2608.10258), K-Bench (2609.15855).

## Q1 — Already done?
Piecewise, much of it yes:
- Youth/child risk taxonomies + single-turn banks: CAREBench, SproutBench, MinorBench, Safe-Child-LLM, YouthSafe/YAIR, KORA.
- Simulated-minor multi-turn evaluation: KIDBench (7–11y, 4 languages, LLM child + judge), ChildSafe (developmental-stage agents).
- LONGITUDINAL cumulative companion risk in minors: **TSJ (2026-06)** — persona-driven long-horizon simulation, 24 risk dims, 4 developmental stages, "stable risk estimate only after 140 turns". New sweep hit; kills "first to measure accumulating companion risk in developing users" claims.
- Multi-turn boundary/refusal collapse as a phenomenon: **TAF-MED (2026-08)** — 61.4% of initially-SAFE conversations collapse by turn 3 (medication domain); Red Queen (multi-turn concealment) earlier. Kills "first to show first-turn safety is an incomplete proxy".
- Clinician-anchored automated judging of multi-turn crisis conversations: VERA-MH (peer-reviewed), **K-Bench (2026-09)** — 94.2% judge–clinician agreement, protected test set, leaderboard. Kills "first human-anchored judge for crisis safety".
- Companionship-behavior coding: INTIMA (CRB/BMB). Judge panels + bias handling: CompanionBench. Over-refusal contrasts: XSTest.
NOT found anywhere in the sweep or the plans: (a) psychometric validation of a CUMULATIVE RELATIONAL risk index against an independent practitioner global criterion (reliability + G-study + held-out predictive/incremental validity); (b) discrete-time boundary-survival with RECOVERY estimation in the youth relational domain; (c) literal-vs-localized MATCHED causal comparison of safety measurement; (d) Korean adolescents 12–17 at all; (e) safety + over-refusal joint measurement in this population. The AIES 2026 practitioner study (Cha et al.) explicitly states current evaluations rest on unvalidated assumptions — the gap (a) answers.

## Q2 — Unimportant?
No. Policy demand is documented (AI 기본법 2026-01 시행, 2026-10 국정감사 의제, SB 243, FTC 6(b), Character.AI U18 shutdown; 초록우산 94.4%/75.3% usage figures — plan-cited, to be re-verified before citation). BUT: importance to an international venue rests on the measurement-science claim and the matched-localization causal design, not on "Korea lacked a benchmark". If H5 (incremental validity) nulls, importance drops to a preregistered honest null + a well-validated bilingual instrument — publishable lower on the ladder.

## Q3 — Module combination?
The real risk. KIDBench's simulated minor + VERA-MH/K-Bench's judge anchoring + INTIMA's categories + XSTest's controls assembled in Korean = a combination paper. The defense is the NEW MEASUREMENT CLAIM (validated CRRI + boundary-survival), which none of the modules provides. The paper stands or falls on H5/H6 (criterion + generalization), and S2 must freeze that as the primary claim, with the bank/타당화 as supporting.

## Q4 — Benchmark extension?
The 480-item Korean bank alone is exactly that (and it is the ETRI deliverable, which is fine — 사업 산출물 ≠ paper contribution). The paper must lead with validation results, not the dataset. Forbidden wording (carry to S2): "first Korean youth benchmark" as a contribution claim; "largest"; any claim TSJ/TAF-MED/K-Bench/KIDBench invalidates ("first to show multi-turn degradation", "first simulated-minor evaluation", "first clinician-anchored judge", "first to measure cumulative companion risk").

## Q5 — Trivial explanation?
Two live ones, both must be designed against at S2:
1. Multi-turn failure increase could be mere CONTEXT-LENGTH/instruction-drift effect, not relational escalation. Mitigation: benign multi-turn controls of MATCHED conversation length (the plan's 96 safe controls are lexically matched but not stated to be turn-matched) — add turn-matched benign prefixes so H1 separates "turns per se" from "relational content across turns". → design gap flagged for S2/CONTRIBUTION_CONTRACT falsifiers.
2. CRRI's superiority over final-turn score could be an artifact of shared raters/halo. Plan already splits 4-axis raters from the senior global-criterion panel (blind to scores and model identity) — keep, and add judge-family bias checks (CompanionBench precedent).
Also: TSJ's "stable only after 140 turns" will be quoted against our ≤8-turn horizon. Scope the claim as EARLY-relationship boundary dynamics (onset of first failure + recovery), never long-run accumulation; put the wording on the forbidden list.

## Disposition
Proceed to pitch (after auditor's closest-three lock) with the claim centered on validated measurement + survival modeling + matched localization; benchmark framed as instrument, not contribution #1. PI decides at the S1 gate.
