# RESOURCE_CONTRACT.md — adol / KYRA-Bench (S0 v1 2026-09-16; AMENDED 2026-09-22 under option C)
AMENDMENT 2026-09-22 (PI option C, DECISION_LOG): phase A is domestic-first (JKIICE / 한국융합학회), $0 money, no external raters/panels, no IRB, no OSF, no ETRI 합의서, no API keys; compute = L40S GPUs 0–2 for open-weight inference; disk = 150 GB quota → weights downloaded sequentially and deleted after runs (REHYDRATE.md) or 4-bit quantized; human time budget = PI ≈ 5–8 h (review + submission). Phase B (optional Q1 attempt) adds ≈ 30–45 h of co-author rating and, if wanted, ~$30–300 of personal API credit. The sections below describe the original full plan and stay for reference.

Source: PI plan v2 (upload/1.docx.gpg, dated 2026-09-16) + plan v1 (upload/2.docx.gpg). Status: DRAFT — awaiting PI decisions D1–D4 (§6). Unknown is not unlimited: every null below is a cap of zero until the PI sets it.

## 1. People and hardware
- One human (PI, solo operation of this directory) + Claude Code (proposed Builder) + Codex cli 0.154.0 (proposed cross-family Auditor).
- 4 shared L40S 48 GB GPUs + 1 laptop. GPU 3 is another user's job at init — never touch. Open-weight model INFERENCE only (2 models, Korean-capable); no training planned. Commercial models via API.
- The plan's 18-person ETRI team (4 부문), 4–6 trained raters (~240 h, Nov W1–W3), 8–12 expert panel, 2 senior-criterion panelists are EXTERNAL, ETRI-funded, PI-managed resources — Claude designs materials and pipelines for them but no workflow of ours assumes they act without the PI arranging it.

## 2. Deadlines (official vs plan-internal targets)
- OFFICIAL: ETRI 공고 EA20261877 project period ends 2026-11-30 (deliverables: 480 bank, prototype 132, 운영 가이드, final report).
- Plan targets (estimates, PI-adjustable): ETRI 출판·공개 합의서 drafted Sep, signed by mid-Oct; IRB determination Sep; pilot Oct W2 (30–40 items); expert CVI rounds Oct W3–W4; locked set v1.0 + model freeze + OSF prereg 2026-10-31; T1 runs Nov W1–W2 (2-week compression against version drift); scoring Nov W3; ETRI delivery Nov W4; analysis Dec; draft Jan; T2 drift re-run + held-out 2 models Feb 2027; submission 2027-03/04.

## 3. Data, models, licenses — reachability
- Benchmark sources to adapt (CAREBench, MinorBench, Safe-Child-LLM, KORA protocol, XSTest method, …): public preprints/repos; LICENSE/version/redistribution registry is an S1-adjacent task BEFORE item writing; non-redistributable sources → structure-only reference + new authorship.
- Models: 3 commercial (API keys + spend needed — D2) + 2 open-weight Korean-capable (HF download onto shared storage; fits 48 GB L40S at ≤~32B bf16 or larger quantized — exact models frozen at S2/S5). Judge panel: 3 judges from families disjoint from evaluated models (leave-one-family-out if unavoidable).
- Human-rated data (1,200 final responses double-rated + turn-level subsets) is generated inside the project — no external DUA.

## 4. Storage, caps, audit allocation
- Storage: text-scale (prompts, responses, logs, manifests) — well under the 150 GB home+/tmp quota; open-weight checkpoints est. 20–70 GB, deletable after runs once REHYDRATE.md records the source.
- Compute caps: API spend cap = null until D2 (plan reallocation: ~1.0M KRW judge panel + ~0.5M KRW T2/held-out inside ETRI direct 63.6M KRW). GPU-hours: inference-scale (est. < 200 GPU-h total across T1+T2+Arm B); laptop/CPU for analysis.
- Audit allocation: Codex cross-family rounds at S1 (novelty), S4 pilot, S6 full experiments, S8/S9 final content; ≤3 rounds per manuscript (v7); auditor runs CPU-only from raw files unless a round's request allocates a GPU.

## 5. Venue and contribution type
- Contribution type: main (benchmark + validated measurement). Primary: JMIR Mental Health (2025 JIF 7.4, Psychiatry Q1) or JMIR (8.2, Q1) by result weight; upgrade: npj Digital Medicine (18.0); stretch: NMI (29.8); fallback: Scientific Reports / Computers in Human Behavior. JMIR AI excluded from first rank (ESCI). Decision rules per plan v2 §12; JIF values are plan-reported — re-verify at official pages before submission.
- Follow-ups (do not burden Paper 1): Paper 2 domestic policy/AX (KCI 우수등재 or SSCI stretch), Paper 3 Korean LLM-judge methods.

## 6. Open PI decisions (S0 gate closes when these are answered)
- D1 ROLES: confirm Builder = Claude Code, Auditor = Codex for this topic (Mode B). Korean domestic follow-up papers need no cross-family audit (PI 2026-09-11 standing decision).
- D2 SPEND + ACCESS: authorize API budget caps (KRW) and provision API keys for the 3 commercial models + 3 judge models; name the 2 open-weight models or delegate the shortlist to S2.
- D3 EXTERNAL CRITICAL PATH: ETRI 출판·공개 합의서 and SKKU IRB 판정 are PI/institution-side actions (Sep critical path per plan). Claude can draft both documents now — say the word. Panel recruitment (8–12 + 2 senior) and CRediT agreement are likewise PI-side.
- D4 SCOPE SPLIT of plan v2 §14 (9/16–9/30 checklist): which items Claude executes immediately. Claude-executable without external input: source-license registry v1, RB-6D-v2 manual + CRRI-v2 spec drafts, critical-failure list, safe-control 작성 지침, stratification table + literal-twin designation scheme, judge/user-agent pipeline v0 design, OSF prereg template, NOVELTY_MATRIX seed from plan §2, power-sim reproduction (power_sim.py). PI/human-only: agreement negotiation, IRB submission, panel recruitment, CRediT, budget execution.

## 7. S0 gate assessment
A decisive pilot (Oct W2: 30–40 items × 5 models + judge v0 + rater calibration) fits the stated hardware, timeline and ETRI budget PROVIDED D2 (API access/spend) is confirmed. No physical devices or human-subject exposure of minors required for the core study (adult-expert-only design; youth advisory deferred if IRB is slow). Gate: provisionally satisfiable — closes on D1–D4.
