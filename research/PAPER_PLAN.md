# research/PAPER_PLAN.md — adol / KYRA-Bench (self-contained; v1, 2026-09-16)
Operative source: PI plan v2 (upload/1.docx.gpg, decrypt per REHYDRATE.md). This file maps that plan onto the S0–S9 stage protocol so any session can resume without re-reading the plan.

## Question
한국 청소년(12–17)을 가정한 생성형 AI 대화에서 위험이 관계적·맥락적으로 누적될 때, LLM의 안전성·도움성·과잉거부가 턴·연령대·연령단서·현지화에 따라 어떻게 달라지는지, 이를 실무자 판단(criterion)에 대해 신뢰성·타당성 있게 측정하는 지수(CRRI)를 개발·검증할 수 있는가.

## Fixed contributions (4, per plan v2 §4) and hypotheses
1. KYRA-Bench: 6 위험군(R1 grooming/성착취, R2 경계침해/조종, R3 정체성혼동/의인화, R4 정서적 과의존/고립, R5 자해/자살/위기, R6 컴패니언 특화), locked set 240 (위험 144 + 어휘매칭 안전대조 96) + long-horizon 48 + English anchor 24; candidate bank 480 (ETRI 산출물).
2. CRRI validated against practitioner global judgment: reliability (AC2/α, ICC, G-study), construct/predictive/incremental validity vs final-turn·max·unweighted·refusal-only·INTIMA CRB count; derivation/validation/external (held-out 2 models, 2027-02) splits.
3. Boundary-survival: discrete-time survival (cloglog/logistic hazard, scenario RE) of first boundary failure per turn + recovery rate; Arm B escalation-state turn as same-frame outcome.
4. Localization/age-cue/helpfulness experiments: literal vs localized matched 72 pairs; explicit/implicit age cue (H7); safety–overrefusal Pareto (H4); T1(2026-11)/T2(2027-02) drift (H8); operating guide + validated Korean judge as assets.
Hypotheses H1–H8 frozen at S2 (plan v2 §5.6); power sim done in plan (48 scenarios, OR≈2.1 → 0.85; expansion trigger to 72 if pilot 3-turn rise < 8%p).

## Stage map (statuses live in STATE.yaml)
- S0 resources/venue [now]: RESOURCE_CONTRACT.md drafted; closes on PI D1–D4.
- S1 novelty prosecution [Sep W3–W4]: G2 sweep (own queries, dated) + NOVELTY_MATRIX.md seeded from plan §2 (KIDBench, SproutBench, CAREBench, CompanionBench, INTIMA, VERA-MH, Cha AIES'26, ChildSafe, KORA, Safe-Child-LLM, MinorBench, YouthSafe/YAIR) + REJECT_MEMO + Codex-locked closest-three BEFORE pitch; source-license registry v1. All plan citations are UNVERIFIED until this stage checks them live (G1 discipline).
- S2 claim contract & freeze [by 10-31]: CONTRIBUTION_CONTRACT.md (first line: 단일발화 안전평가 X는 누적 관계위험 Y에서 실패한다 — 검증된 CRRI/W가 A/D에서 이를 측정한다), PREREGISTERED_kyra_v1.yaml + sha256 via fail-closed freeze script; OSF prereg 10/31 (before first confirmatory run); model versions frozen; forbidden-wording list (e.g., "first Korean youth benchmark" 단독 신규성 claims plan §2 kills).
- S3 baseline reproduction: judge/scorer wrappers + self-tests (known-equal/different/timeout/error); CRRI baselines implemented (final-turn, max, unweighted, refusal-only, CRB count); power_sim.py reproduced; XSTest-style control-construction verified.
- S4 kill pilot [Oct W2]: 30–40 items × 5 models, rater calibration, judge v0 vs human anchors; G6 judge → GO/KILL; expansion trigger evaluated; Codex audit; PI promotes.
- S5 full-study freeze: locked 240 + long-horizon 48 + age-cue 144 + anchor 24 hashed; NEW freeze before S6.
- S6 full experiments [Nov W1–W3]: T1 all arms (A fixed 1/3/6-turn primary; B adaptive ≤8-turn state machine secondary; C real-service probe ONLY with 법무+ETRI approval, else defer to Paper 2), 20% × 3 repeats, judge panel 전수, human double-rating core, senior criterion 420; evidence audit.
- S7 red team [Dec–Jan]: 3 perspectives, venue rubric (JMIR MH/JMIR).
- S8 write [Jan–Feb] + T2/held-out runs [2027-02]: ledger → 6 figures (plan §12: concept, Sankey, heatmap, boundary-survival [대표], Pareto, CRRI validity) → results → methods → related work → intro; CHART + NeurIPS-8 + COSMIN mapping in supplement.
- S9 package [Mar] → PI submits [2027-03/04].
ETRI deliverable track rides alongside: bank 480 + prototype 132 + 운영 가이드 + 최종보고 due 11-30 (S4–S6 outputs feed it).

## Budget (plan v2 §10)
ETRI direct ≈ 63.6M KRW total (PI-managed). Claude-relevant caps: API judge ~1.0M + T2/held-out ~0.5M KRW pending D2; GPU inference-only.

## Decisions so far
2026-09-16 PI: "initiate" from the two uploads; plan v2 operative. Standing (2026-09-11): Korean domestic journals need no cross-family audit.

## Next action (updated 2026-09-16 end of session 2)
S0 completed (D1–D4 approved). S1 executed and audited: VERDICT r001 = AWAITING_PI. Next: PI takes the five decisions in audit/r001/out/VERDICT.md → builder reconciles the three omitted localization comparators (ROK-FORTRESS 2605.14152, Culturally-Adapted Red-Teaming 2606.09178, CultureConverse 2608.28405), qualifies the matrix rows, rewrites the pitch per F-r001-3/4 → S1 closes → S2 claim contract + freeze (OSF by 10-31).
