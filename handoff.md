# handoff.md — adol (rolling; overwritten each session)

## 2026-09-16 — session 1: initiate (Claude Code, proposed Builder)
Done today:
- Decrypted and read both PI uploads in the session scratchpad (deleted after use): 1.docx = KYRA-Bench plan v2 (2026-09-16, OPERATIVE), 2.docx = plan v1 (superseded). Hashes in REHYDRATE.md.
- Initialized the project per the global L2 protocol (no AGENTS.md here): CLAUDE.md, memory.md, this file, REHYDRATE.md, .claude/settings.json (deny-list), .gitignore, .upload_pass (mode 600), research/STATE.yaml, research/PAPER_PLAN.md, RESOURCE_CONTRACT.md (S0 draft), deliverables/stage_0_report_v1.md + stage_0_response_v1.txt; local git baseline; hub page repos/wiki/projects/adol.md + INDEX row.
- Verified: Codex cli 0.154.0 installed (Auditor available); GPUs 0–2 idle, GPU 3 foreign job; git identity Woncheol Jeong <hkbigdream@gmail.com>.

Current state: stage S0, status awaiting_pi. Roles PROPOSED (Builder=Claude Code, Auditor=Codex), not yet confirmed.

Exact next steps:
1. PI answers D1–D4 in RESOURCE_CONTRACT.md §6 (roles; API budget/keys + model list; ETRI 합의서/IRB ownership — Claude can draft both; scope split of plan §14).
2. Then RUN STAGE 1: dated concurrent-work sweep with own queries; NOVELTY_MATRIX.md from plan §2 + sweep; REJECT_MEMO.md; ask Codex for the blind closest-three lock before writing the pitch; source-license registry v1.
3. Early parallel work possible without PI input (if D4 grants it): RB-6D-v2 manual draft, CRRI-v2 spec, critical-failure list, stratification table scheme, judge/user-agent pipeline v0 design, OSF prereg template, power_sim.py reproduction.

Open blockers: D1–D4; ETRI 출판·공개 합의서 + SKKU IRB are September critical path (PI/institution side).

Disclosures:
- Both passphrases (vault + adol uploads) were pasted into the chat transcript by the PI this session; §3 says to note it once — rotate if either is reused anywhere else. The adol passphrase now lives only in .upload_pass (mode 600, git-ignored).
- Claude auto-memory directory is EACCES-unreadable this session (noted in memory.md); continuity relies on this file + memory.md, which is the designed path anyway.
- Decrypted temporaries were deleted from the scratchpad at session end; originals untouched.
- None of the plans' citations have been independently verified yet (G1 pending at S1).
