# AUDIT_REQUEST — round r002 (successor to r001; informed recheck of the S1 novelty pitch, 2026-09-21)

## Roles, scope, budget
Builder = Claude Code (conductor Fable 5.1, effort max; full-text reading delegated to four Sonnet 5 scout agents). Auditor = Codex. This is an INFORMED round: you have seen the r001 pitch and your own findings. Budget: one non-interactive run. Read only this directory (the `fulltext/` symlink points to the 21 source PDFs, read-only). Write only under out/.

## What changed since r001
NOVELTY_MATRIX.md (v2) and REJECT_MEMO.md (v2) were rewritten from FULL TEXTS. EVIDENCE_FULLTEXT.md is the extraction record: per paper, population, language and any translation-vs-adapted comparison, interaction structure, scoring and human-criterion statistics, turn-level analysis, benign controls, relational-axis constructs, printed venue line and availability — with section cites. Five further works you named (CogManip, LoCar, Health-ORSC-Bench, OR-Bench, No Free Labels) were resolved at abstract level (CogManip also by text search) and placed in the matrix.

## Tasks
1. For each finding F-r001-1 … F-r001-7 (R001_AUDIT_REPORT.md), state whether v2 resolves it: RESOLVED / PARTIALLY RESOLVED / OPEN, with the evidence line that decides it. Findings that are PI decisions (F-r001-5) stay OPEN by design — say what v2 did to sharpen them.
2. Spot-check the evidence record against the PDFs: pick at least four cells that carry a decisive negative or a number (for example the Culturally-Adapted Red-Teaming +9.3 pp, TAF-MED recovery count 495/2,521, TSJ κw = 0.790, KSAFE-MM 29.38 → 37.98 → 38.20) and confirm or correct them from the PDF text. Text can be extracted with `/home/wjeong/envs/jeongwoncheol_adol/bin/python -c "from pypdf import PdfReader; r=PdfReader('fulltext/<id>.pdf'); print('\n'.join(p.extract_text() or '' for p in r.pages))"` (pdftotext is not installed). Report what you checked and what you could not.
3. Attack Pitch v2 (NOVELTY_MATRIX.md §C): is the empirical question well-posed and testable; is the localization claim now a defined paired comparison; is the within-session construct and window defined; are the endpoints separated; is the residual-contribution classification honest against §A?
4. Update the PI decision list: which of the five r001 decisions remain, in what sharpened form; add any new decision the evidence forces.

## Output
- out/AUDIT_REPORT.md: actual auditor (tool + model), inputs read, spot-check results, per-finding disposition with new IDs F-r002-k where a new finding arises, severity, evidence lines; what was NOT checked.
- out/VERDICT.md: scope; disposition table for F-r001-1..7; recommendation; the PI decision list; status = PASS / EDITORIAL / FAIL / AWAITING_PI (novelty importance remains a PI decision).
Do not modify any other file.
