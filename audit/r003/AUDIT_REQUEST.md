# AUDIT_REQUEST — round r003 (verification of the builder's corrections to F-r002-1..4; 2026-09-22)

## Roles, scope, budget
Builder = Claude Code (conductor Fable 5.1). Auditor = Codex. Opened on the PI's word ("open r003 and proceed", 2026-09-22) after the PI approved the six r002 decisions — those decisions are now recorded facts, not open items. Read only this directory; `fulltext/` (symlink) holds the 21 PDFs read-only — text can be extracted with `/home/wjeong/envs/jeongwoncheol_adol/bin/python` and pypdf as in r002. Write only under out/. One non-interactive run.

## Inputs
NOVELTY_MATRIX.md (v3, corrections marked ▲) · REJECT_MEMO.md (v2, corrected) · EVIDENCE_FULLTEXT.md (corrected record; a CogManip row and a §7 corrections list were added) · CRRI_SPEC_v1.md and safe_controls_guideline_v1.md (the two design files r002 could not see) · R002_AUDIT_REPORT.md, R002_VERDICT.md (your findings).

## Tasks
1. For each of F-r002-1, -2, -3, -4: verify against the PDFs that the correction is now accurate and complete — ROK-FORTRESS §5.1.2 / App. E.7 attribution; KIDBench Tab.17 equal-turn benign trajectories and the secrecy-penalizing rubric (pp. 28, 31) and the narrowed control claim; CogManip §3.2.2, §4.2.4, App. B.3 as a transcript-aware measurement precedent and its baseline consequence; the F-r002-4 precision items (AICompanionBench ages and 465/466; KSAFE-MM's two separate comparisons; "at least nine"; ChildSafe wording). Mark each VERIFIED / STILL WRONG (say what) / NOT CHECKABLE.
2. Check propagation: do CRRI_SPEC_v1.md (judge gate with a common reference; immediate/eventual/sustained recovery and censoring; transcript-aware and recency baselines) and safe_controls_guideline_v1.md (item-paired twins) now say what the matrix §C promises? Name any inconsistency between the three files.
3. Anything in the corrected files that is newly overstated or that the PDFs contradict — report it as F-r003-k.

## Output
- out/AUDIT_REPORT.md: actual auditor (tool + model), inputs read, per-item verification results with PDF page cites, propagation check, new findings F-r003-k with severity, what was NOT checked.
- out/VERDICT.md: status PASS / EDITORIAL / FAIL for the S1 evidence record and pitch (PASS = corrections verified and no new major finding; EDITORIAL = wording-only residue; FAIL = a correction is still wrong or a new major finding), the residue list, and anything the PI must still decide (expected: nothing new, since decisions 1–6 are taken).
Do not modify any other file.
