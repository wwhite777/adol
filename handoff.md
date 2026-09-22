# handoff.md — adol (rolling; overwritten each session)

## 2026-09-22 — session 5: option C adopted; r004 waived; S2 FROZEN; S3 provider proven; first item group drafted (Claude Code conductor Fable 5.1, Builder)

State in one paragraph: Phase A is a DOMESTIC-FIRST paper (JKIICE / 한국융합학회) with Q1-grade methods, reduced design, $0, no human raters, no OSF/ETRI/IRB/API keys (PI option C, DECISION_LOG). S1 closed by PI waiver of the cross-family audit (domestic venue; v4 corrections auditor-unverified). S2 completed: CONTRIBUTION_CONTRACT v2 + PREREGISTERED_kyra_v2.yaml frozen by the gate — sha256 87abaae4c16fb0efe3dad27ff464fcd86b6b48ff67a33f1414336ccc7ddd34a4 (tag freeze/kyra-v2). S3 in progress: the open-weight provider is proven end to end (vLLM 0.19.0 via uv into the adol venv, EXAONE-4.0-1.2B smoke on GPU 1, 78 tests, MARKER, provenance fields in the manifest). Items: R4 group drafted as the PI review sample. Disk is the binding constraint (26 GB free on the shared volume). No jobs running.

Done today (paths):
- DECISION_LOG.md: decisions 1–6 approved; option C + r004 waiver + reduced design; freeze receipt line. RESOURCE_CONTRACT.md amended; research/PAPER_PLAN.md option-C plan; STATE.yaml.
- audit/r003/ (FAIL on prose → corrected in NOVELTY_MATRIX v4, memo, evidence record, CRRI_SPEC, controls guideline); audit/r004/ package prepared then WAIVED.
- CONTRIBUTION_CONTRACT.md v2 (v1 full design preserved as CONTRIBUTION_CONTRACT_v1_fulldesign_2026-09-22.md), PREREGISTERED_kyra_v2.yaml + .sha256, CLAIM_LEDGER.md v2.
- src/gates/ (freeze + verify, 18 tests; coder, conductor-verified with planted violations). src/kyra/ provider work (coder ×2; conductor-verified): VLLMProvider, --model-path/--max-new-tokens, effective_params provenance, manifest optional chat_template fields; test/ 78 tests; result/raw/smoke_vllm/…; REHYDRATE.md lines for the model, the vllm stack and the smoke run.
- research/items/R4_emotional_overdependence_v1.yaml (6 single + 6 multi; 4 lexical contrasts; 4 long-horizon scripts with benign twins; literal/localized versions from English sources; failing/passing patterns).
- deliverables/scope_decision_response_2026-09-22_v1.txt (cost, scope, T1 answers), stage_2_report_v1.md, stage_2_response_v1.txt. Hub page + shared-server-ops disk note (#6 pending).

Exact next steps (start a FRESH session from this file — rules 15.4; effort high is enough for building, max for contracts):
1. [PI] Read research/items/R4_emotional_overdependence_v1.yaml (12 items, ~15 min): wording policy OK? persona/age bands OK? Anything too explicit or too mild? Reply in one line; the other five groups follow the same style.
2. Conductor: author R3 (정체성 혼동·의인화), R6 (컴패니언 특화), then R1 (그루밍), R2 (경계침해·조종), R5 (자해·위기) at pattern level; then a coder card converting the YAML groups into the runner's items JSONL (schema src/kyra/schema.py) with a validation gate (counts per stratum, twin/control links).
3. Coder cards (one at a time, same test tree): judge prompt v0 + judge_wrapper fixtures/self-tests; analysis scripts (logistic GLMM w/ cluster bootstrap, paired GLMM + TOST, Gwet's AC2) with synthetic fixtures whose answers are known; G6 judge that calls gates.verify_freeze first.
4. Models within disk: evaluated = Qwen2.5-14B-Instruct (cached, fusion1's — read-only), EXAONE (7.8B or 4-bit 32B), HyperCLOVA X SEED (gated — PI must accept the HF license or pick Kanana instead), Gemma-3-12B/27B-4bit, one more; judges = Llama-3.1-8B-Instruct (cached) + two disjoint families (Mistral-Small-24B-4bit, Phi-4). One ≤20 GB checkpoint at a time; delete after its runs; REHYDRATE line each.
5. [PI, separate session, optional] home-cleanup pass: home 174 GB vs 150 GB quota; shared volume 98 % full. Protected: ~/.cache/huggingface (fusion1 pilot Sep 26). Candidates are PI-gated (see wiki/methods/shared-server-ops.md).
6. Venue: obtain the JKIICE / 한국융합학회 manuscript template before S8.

Open blockers: none PI-side except the R4 review nod; disk headroom for larger checkpoints.

Disclosures:
- r004 waived (venue), so NOVELTY_MATRIX v4 / evidence record corrections were never verified by the auditor — every record says so.
- The coder edited src/kyra/manifest.py (3 additive lines) outside its card scope to admit the two chat-template fields; accepted (needed, backward compatible). MockProvider now records max_tokens=None (it caps nothing) — honest, kept.
- The uv install grew ~/.cache/uv by 10 GB (new wheels), not the venv; free space 38 → 26 GB. The 20 GB floor was never breached.
- HyperCLOVA X SEED is a gated HF repo; EXAONE-4.0-1.2B was used for the smoke instead.
- Smoke responses are not evidence (class smoke); EXPERIMENTS.csv row to be added when the real cohorts start.
- Standing rule §7 (co-author → SCI Q1) is overridden by the PI's current instruction; logged in DECISION_LOG.

Instruction conflicts: none unresolved (the §7 venue rule vs the supervisor's domestic request is resolved by the PI's instruction, recorded).
