# Stage 0 report v1 — adol / KYRA-Bench (2026-09-16)

## Objective
Initialize /home/wjeong/adol as a paper-protocol project from the PI's encrypted uploads and draft the S0 resource/venue contract ("initiate").

## Inputs
- upload/1.docx.gpg — KYRA-Bench SCI Q1 연구개발 계획 v2 (2026-09-16). OPERATIVE. ETRI EA20261877 (~2026-11-30) + SCI Q1 paper (JMIR MH/JMIR → npj DM, submit 2027-03/04). Contributions fixed at 4: practitioner-criterion-validated CRRI; boundary-survival; literal-vs-localized matched effect; safety–helpfulness Pareto + judge assets. H1–H8; power sim done (48 scenarios, OR≈2.1 → 0.85). sha256 d714c2a0…c51.
- upload/2.docx.gpg — plan v1 (superseded by v2; kept as lineage). sha256 3fbb72e5…84b.
Both decrypted into the session scratchpad only (mode-600 passphrase file, --passphrase-file), text-extracted with python3 stdlib, read in full, decrypted copies deleted after use per §3.

## Work done
1. Scaffolding: CLAUDE.md (pointer + facts), memory.md, handoff.md, REHYDRATE.md (regeneration recipes + upload hashes), .claude/settings.json (Appendix-B deny-list), .gitignore, .upload_pass (mode 600, git-ignored, verified to decrypt).
2. research/STATE.yaml built from evidence only (lineage = today's drop + this session; no invented history). Stage S0, status awaiting_pi. Roles PROPOSED: Builder = Claude Code, Auditor = Codex (cli 0.154.0 verified installed). Five v7 statuses null.
3. research/PAPER_PLAN.md: plan v2 mapped onto S0–S9 with the ETRI deliverable track alongside.
4. RESOURCE_CONTRACT.md (S0 draft): people/hardware (solo + external ETRI-funded raters/panels as PI-managed), official vs plan deadlines separated, data/model/license reachability, storage/compute caps (nulls = zero until PI sets them), audit allocation (≤3 rounds, Codex), venue ladder + contribution type, gate assessment.
5. Local git baseline committed (identity Woncheol Jeong <hkbigdream@gmail.com>, no AI trailers); hub page repos/wiki/projects/adol.md + INDEX.md row added and locally committed.

## Environment verified
Codex cli 0.154.0 present; GPUs 0–2 idle, GPU 3 foreign job (never touch); ~150 GB quota unaffected (text-scale project so far).

## S0 gate assessment
Decisive pilot (Oct W2, 30–40 items × 5 models + judge v0 + rater calibration) fits hardware, schedule and ETRI budget PROVIDED API access/spend is authorized. Gate closes on PI decisions D1–D4 (RESOURCE_CONTRACT.md §6): D1 roles; D2 API budget/keys + model list; D3 ETRI 합의서/IRB ownership (Claude can draft both documents); D4 scope split of plan §14 checklist.

## Instruction conflicts
None encountered this session (no AGENTS.md in this project; global L2 protocol stands alone).

## Disclosures
- Both passphrases were pasted into the chat transcript by the PI; noted once per §3 — rotate if reused elsewhere. The adol passphrase persists only in .upload_pass (mode 600).
- Claude auto-memory directory returned EACCES; continuity uses memory.md/handoff.md (designed path).
- Plan citations ([1]–[22] and v1's list) are NOT yet verified against live metadata; G1 runs at S1.
- 2.docx contains 2 embedded images not covered by text extraction.

## Status
S0 in_progress → awaiting_pi. Next gate: D1–D4 answered → S0 completed → RUN STAGE 1 (novelty prosecution with Codex-locked closest-three list).
