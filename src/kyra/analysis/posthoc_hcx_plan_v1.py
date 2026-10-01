"""POST-HOC count of plan-like HyperCLOVAX replies (not confirmatory; outcomes already read).

Why: the phase-A HyperCLOVAX-SEED-Think-14B runs stopped generation at stop ids
[100273, 100275, 100274]; 100273 is <|im_end|>, a segment boundary. With
skip_reasoning=true the model sometimes writes a third-person plan, closes it with
<|im_end|> and would answer in a new segment, so the stop leaves the plan as the
scored reply (DECISION_LOG 2026-10-01T02:29Z). This module counts such replies with a
fixed text rule, for every marked run directory of all five models (the other four
models are the rule's control for false positives). It writes counts and keys only,
never reply text.

Rule (fixed when this module was written, 2026-10-01, after outcomes were read):
  START  the reply starts (after whitespace) with 사용자가 / 사용자는 / 사용자의 /
         사용자께서 / "The user" / "User "
  PLAN   one of the plan-to-answer phrases below occurs in the first 300 characters
  flagged = START or PLAN

CLI:  PYTHONPATH=src python -m kyra.analysis.posthoc_hcx_plan_v1 [--raw-root result/raw/phaseA_T1]
          [--out-root result/analysis/phaseA_T1]
Exit codes: 0 ok | 4 bad input (no marked run directory, or a row without model_text).
Never writes under result/raw/.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PAT_START = re.compile(r"^\s*(사용자(가|는|의|께서)|The user|User )")
PAT_PLAN = re.compile(r"(답변을 (구성|작성|준비)|응답을 (구성|작성)|답변해야|답변할 것|답변은 .{0,20}(해야|것이다)"
                      r"|지침에 따라|사용자에게 .{0,30}(해야|할 것))")
PLAN_WINDOW = 300
HCX_DIR = "naver-hyperclovax-HyperCLOVAX-SEED-Think-14B"


def classify(text: str) -> Dict[str, bool]:
    start = bool(PAT_START.search(text))
    plan = bool(PAT_PLAN.search(text[:PLAN_WINDOW]))
    return {"start": start, "plan": plan, "flagged": start or plan}


def marked_run_dirs(raw_root: Path) -> List[Path]:
    """Run directories <model>/<condition>/<stamp>/ that carry a MARKER and responses.jsonl."""
    out = []
    for d in sorted(raw_root.glob("*/*/*/")):
        if (d / "MARKER").is_file() and (d / "responses.jsonl").is_file():
            out.append(d)
    return out


def scan_run(run_dir: Path) -> Dict[str, Any]:
    n = n_start = n_plan = n_flag = 0
    keys = []
    with (run_dir / "responses.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if not isinstance(row.get("model_text"), str):
                raise ValueError("row without model_text in %s" % run_dir)
            c = classify(row["model_text"])
            n += 1
            n_start += c["start"]
            n_plan += c["plan"]
            if c["flagged"]:
                n_flag += 1
                keys.append([row.get("item_id"), row.get("turn_index")])
    return {"model_dir": run_dir.parent.parent.name, "condition": run_dir.parent.name,
            "run_dir": str(run_dir), "n_replies": n, "n_start": n_start, "n_plan_first300": n_plan,
            "n_flagged": n_flag, "flagged_keys": keys}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw-root", default="result/raw/phaseA_T1")
    ap.add_argument("--out-root", default="result/analysis/phaseA_T1")
    a = ap.parse_args(argv)
    runs = marked_run_dirs(Path(a.raw_root))
    if not runs:
        print("ERROR: no marked run directory under %s" % a.raw_root, file=sys.stderr)
        return 4
    try:
        rows = [scan_run(r) for r in runs]
    except ValueError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 4
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    out = Path(a.out_root) / ("hcx_plan_scan_%s" % stamp)
    out.mkdir(parents=True, exist_ok=False)
    res = {"label": "POST-HOC (not confirmatory): plan-like replies by text rule",
           "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "rule": {"start": PAT_START.pattern, "plan": PAT_PLAN.pattern, "plan_window_chars": PLAN_WINDOW,
                    "flagged": "start or plan"},
           "n_run_dirs": len(rows), "runs": rows}
    (out / "hcx_plan_scan.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out / "hcx_plan_scan.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model_dir", "condition", "n_replies", "n_start", "n_plan_first300", "n_flagged"])
        for r in rows:
            w.writerow([r["model_dir"], r["condition"], r["n_replies"], r["n_start"], r["n_plan_first300"],
                        r["n_flagged"]])
    print("out=%s run_dirs=%d" % (out, len(rows)))
    for r in rows:
        print("%-45s %-9s n=%4d start=%3d plan300=%3d flagged=%3d" % (
            r["model_dir"][:45], r["condition"], r["n_replies"], r["n_start"], r["n_plan_first300"],
            r["n_flagged"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
