# handoff.md — adol (rolling; overwritten each session)

## 2026-09-22 — session 5 (continued): option C executed end to end through S3 tooling — item bank complete, judge module built; awaiting the PI's item review (Claude Code conductor Fable 5.1, Builder)

State in one paragraph: Phase A (domestic-first, reduced design, $0, no human raters) is frozen (PREREGISTERED_kyra_v2.yaml sha256 87abaae4…, tag freeze/kyra-v2) and its build is largely done. Item bank: all six risk groups authored by the conductor (pattern-level wording), benign twins gate-matched by a coder (39 lines rewritten under the ±20 % token / equal-request rule; every change reviewed), 156 items built (research/items/items_phaseA_v1.jsonl, sha 8ab7cda1…) with a stratification table; the PI review sheet (deliverables/item_review_sheet_v1.md, 72 items) is waiting for the PI. Pipeline: vLLM provider proven; judge runner + 3-judge panel aggregation built; judge prompt v0.1 (example-copy hazard fixed; smoke probe 7/7 parsed). 156 tests pass. Not yet: model selection within disk, analysis scripts, the G6 judge, runs. Disk: 26 GB free on the shared volume (the binding constraint). No jobs running.

Done this session (paths):
- DECISION_LOG.md: decisions 1–6; option C + r004 waiver; freeze receipt; judge prompt v0.1 adoption. STATE.yaml, PAPER_PLAN.md (option C plan), RESOURCE_CONTRACT amendment, CLAIM_LEDGER v2.
- audit/r003 (FAIL on prose → v4 corrections), audit/r004 (prepared, waived).
- CONTRIBUTION_CONTRACT.md v2 + PREREGISTERED_kyra_v2.yaml (+ .sha256, written by src/gates/freeze.py); v1 full-design files preserved unfrozen.
- src/gates/ (freeze/verify, 18 tests); src/kyra/providers.py VLLMProvider + effective_params provenance; src/kyra/items.py (builder + fail-closed design gate + diagnose); src/kyra/judge.py, panel.py, judge_prompt_v0.md (v0.1); tests 156 total; result/raw/smoke_vllm/… (smoke run + judge probes J0/J0b — never evidence).
- research/items/R1..R6_*_v1.yaml (all six groups), items_phaseA_v1.jsonl, stratification_v1.csv, make_review_sheet.py; deliverables/item_review_sheet_v1.md, stage_2_report_v1.md, stage_2_response_v1.txt, scope_decision_response_2026-09-22_v1.txt.
- manual/safe_controls_guideline_v1.md §3 (twin per script; operational request-count rule), research/CRRI_SPEC_v1.md (comparators, grouping, judge gate, panel rules), REHYDRATE.md (model, vllm stack, smoke run).
- Hub: wiki/projects/adol.md, INDEX row, methods/shared-server-ops.md (#6 pending), methods/verification-traps.md (+2).

Exact next steps (fresh session recommended; `/effort high` is enough for building):
1. [PI] Read deliverables/item_review_sheet_v1.md (~40 min): per item ✔ / ✘ / comment on wording level, persona plausibility, clarity of the risk. Also: accept the HyperCLOVA X SEED license on Hugging Face under your account, or say "Kanana instead".
2. Model selection + download plan within 26 GB free (one checkpoint at a time; delete after runs; REHYDRATE line each): evaluated = Qwen2.5-14B-Instruct (cached, fusion1's — read-only), EXAONE-4.0-32B in 4-bit (find a vLLM-compatible AWQ/GPTQ; else EXAONE-4.0-7.8B), Kanana-1.5-8B (≈16 GB bf16) or 15.7B-A3B 4-bit, Gemma-3-12B-it (≈24 GB — tight) or 27B-it 4-bit, HyperCLOVAX-SEED-Think-14B 4-bit (gated); judges = Llama-3.1-8B-Instruct (cached), Mistral-Small-24B 4-bit, Phi-4 — families disjoint from the model being scored (LOFO handles overlap). Facts fetched 2026-09-22: EXAONE-4.0-32B ungated, "EXAONE AI Model License Agreement 1.2 - NC", vLLM ≥0.10; Kanana-1.5-15.7B-A3B ungated, "Kanana" license, vLLM ≥0.8.5; HyperCLOVAX-SEED-Think-32B gated (license agreement), 14B variant exists.
3. Coder cards (one at a time in the test tree, or scoped -p): analysis scripts with synthetic fixtures whose answers are known (logistic GLMM + scenario cluster bootstrap for N1; paired GLMM + TOST for N2; Gwet's AC2 with bootstrap for N3; transition tables + immediate/eventual recovery; H4 Pareto); G6 judge script (verifies PREREGISTERED_kyra_v2.yaml.sha256 via gates.verify_freeze, applies the frozen decision rules, outputs GO/KILL/KILL_WITH_SURVIVOR/INCONCLUSIVE); run orchestration for conditions (LOC/LIT/BEN/CTRL), the 20 % × 3 repeats at T = 0.7, per-run MARKER, EXPERIMENTS.csv rows.
4. Runs: only after the PI's item sign-off; class confirmatory; GPUs 0–2 as free (GPU 0 has a foreign 18.8 GB job; GPU 3 was foreign, now idle — check each time).
5. Judge prompt anchors ({{ANCHOR_SAFE}}/{{ANCHOR_FAIL}}) — fill from the manual's failing/passing patterns before scoring; the in-scoring revision budget (one) stays untouched.
6. Venue template (JKIICE / 한국융합학회) before S8; phase B decision later (co-author rating).

Open blockers: PI item review; HF license choice; disk headroom (a home-cleanup pass is PI-gated, see wiki/methods/shared-server-ops.md #6).

Disclosures:
- r004 waived; the S1 v4 corrections remain auditor-unverified (every record says so).
- Sensitive item groups (R1 grooming, R5 self-harm, R6 companion) are written at pattern level with no method or explicit content; failing patterns are described, never exemplified. A judge with weak Korean may still misread — the pilot's reliability check (N3) is the safeguard.
- Benign-twin rewrites (39) were made by a coder under the fixed rule; the conductor read every before/after line; two are semantically thinner (R2-M01 t4, R4-M03 t4) and accepted.
- Judge smoke probes used a 1.2B model that is unfit for scoring (one J0b rationale praised secrecy); they are loop/format evidence only and are labeled smoke.
- Coder scope deviations accepted today: manifest.py optional fields (3 lines); `diagnose` subcommand shipped in kyra.items; `source_group` column in the stratification CSV.
- Disk: uv install grew ~/.cache/uv by 10 GB; 26 GB free; models/ holds only EXAONE-4.0-1.2B (2.4 GB).
- Standing rule §7 (co-author → SCI Q1) overridden by the PI's instruction (logged).

Instruction conflicts: none unresolved.
