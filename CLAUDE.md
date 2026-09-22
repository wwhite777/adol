# adol/ — KYRA-Bench (Korean Youth Relational AI-safety Benchmark + CRRI)
No project AGENTS.md: the global rules' L2 paper protocol stands alone (v3.2 incl. L5 orchestration); roles come from research/STATE.yaml.
Purpose: ETRI EA20261877 benchmark deliverables (due 2026-11-30) + SCI Q1 paper (JMIR MH / JMIR → npj DM; submit 2027-03/04).
Status and next steps: handoff.md (read it first; memory.md before that). Stage records: deliverables/stage_<N>_report_v<K>.md.
Venue/state: S1 audited (r001–r003), S2 contract + freeze 2026-09-22 — details in handoff.md; hub page: /home/wjeong/repos/wiki/projects/adol.md
Source plans (PI uploads, encrypted): upload/1.docx.gpg = plan v2 (OPERATIVE); upload/2.docx.gpg = plan v1. Decrypt into the session scratchpad ONLY and delete after use:
  gpg --batch --decrypt --passphrase-file /home/wjeong/adol/.upload_pass -o <scratchpad>/1.docx upload/1.docx.gpg
Passphrase file: /home/wjeong/adol/.upload_pass (mode 600; never on a command line; never committed — .gitignore covers it).
Venv: ~/envs/jeongwoncheol_adol/bin/python (stdlib + pypdf + pyyaml). Run modules with PYTHONPATH=src (src/kyra pipeline v0; src/gates freeze/verify).
Data roots: upload/ (PI drops), result/raw/<cohort>/<run_id>/ (immutable; MARKER = validated), research/sweeps/ (sweep + full texts, PDFs git-ignored).
Frozen protocol: PREREGISTERED_kyra_v1.yaml + .sha256 (receipt written only by src/gates/freeze.py; confirmatory scripts call gates.verify_freeze first). Contract: CONTRIBUTION_CONTRACT.md; ledger: CLAIM_LEDGER.md.
Deliverables: deliverables/ (versioned, plaintext). Audit rounds: audit/r<NNN>/ (inputs = tagged snapshot audit/kyra-r<NNN>; auditor writes out/ only).
Definition of done for the current stage (S2): freeze receipt exists, its hash is in DECISION_LOG.md, STATE.yaml protocol_freeze set; PI registers on OSF (external, by 10-31).
Project traps: GPU 3 is another user's job — never touch. Conductor's Read cannot render PDFs here (use venv pypdf); arXiv API throttles (use abs pages). Health/self-harm-adjacent PDFs may trip the Sonnet scout's classifier — conductor reads those. Every transcribed statistic keeps metric + reference + unit + denominator.
