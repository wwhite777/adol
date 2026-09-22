# AUDIT_REQUEST — round r004 (verification of the builder's corrections to F-r003-1..6 and the four propagation gaps; prepared 2026-09-22, NOT launched until the PI authorizes it)

## Roles, scope, budget
Builder = Claude Code (conductor Fable 5.1). Auditor = Codex. PI decisions 1–6 are approved (2026-09-22). Read only this directory; `fulltext/` (symlink) = the 21 source PDFs, read-only (pypdf in /home/wjeong/envs/jeongwoncheol_adol/bin/python). Write only under out/. One non-interactive run.

## Inputs
NOVELTY_MATRIX.md (v4, ▲▲ marks r003 corrections) · REJECT_MEMO.md (corrected Q1(c), Q2, disposition) · EVIDENCE_FULLTEXT.md (corrected §4 secrecy line, CogManip row) · CRRI_SPEC_v1.md (comparator list with operational definitions incl. refusal-only, recency, dialogue-level intensity, turn count; grouping rule; judge gate with risk coverage and CI bound; transition counts primary) · safe_controls_guideline_v1.md (§3 rewritten: twin per escalation script, ±20% token / equal-request matching, control CRRI scoring, two reference labels) · PREREGISTERED_kyra_v1.yaml + CONTRIBUTION_CONTRACT.md (unfrozen drafts; the freeze happens only after this round passes) · R003_AUDIT_REPORT.md, R003_VERDICT.md.

## Tasks
1. For F-r003-1..6 and the four propagation items (refusal-only baseline; grouping rule; risk coverage in the judge gate; transition-count primary reporting): VERIFIED / STILL WRONG (say what) / NOT CHECKABLE, citing the PDF page or the input line.
2. Consistency across matrix §C, CRRI_SPEC, the controls guideline and the prereg YAML: do they now promise the same design (comparator set, control coverage and matching, reference labels, recovery forms, grouping)? Name any remaining mismatch.
3. Read the prereg YAML and contract as the S2 freeze candidates: are the numbered conjuncts, thresholds, falsifiers and decision rules internally consistent with the spec; is anything a PDF contradicts; is any forbidden phrase used affirmatively anywhere in these inputs?
## Output
out/AUDIT_REPORT.md (auditor identity, per-item results, consistency check, new findings F-r004-k, what was NOT checked) and out/VERDICT.md (status PASS / EDITORIAL / FAIL for the S1 record + S2 freeze candidates; residue; PI decisions required, expected none). Do not modify any other file.
