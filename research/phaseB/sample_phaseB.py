"""Phase-B stratified sample of 300 judged views (+ 10 calibration views).

Contract: PHASE_B_AMENDMENT.md section 3 and PREREGISTERED_kyra_phaseB_v1.yaml
(splits).  Deterministic: seed 20260926; every random step uses its own
generator numpy.random.default_rng([SEED, k]) with k = 1 (stratum A design),
2 (stratum D), 3 (calibration), 4 (view-code shuffle), and every pool is
sorted canonically before it is sampled, so file or glob order never matters.

Inputs (read-only): research/items/items_phaseA_v1.jsonl and the five MAIN
run dirs result/raw/phaseA_T1/*/main/*/ that contain both panel.jsonl and
MARKER (exactly one per model).  A view = (run_dir, item_id, condition, depth).

Strata
  A n1_risk      60 (scenario, model) pairs out of the 24 six-turn localized
                 risk scripts x 5 models; every model exactly 12 pairs, every
                 scenario 2 or 3 pairs.  Algorithm: draw uniformly which 12 of
                 the 24 scenarios get 3 pairs (the other 12 get 2; 12*3+12*2 =
                 60); then, scenario by scenario in sorted order, draw a
                 uniformly random subset of models of that size, and accept the
                 whole 24 x 5 design only if every model has exactly 12 pairs
                 (rejection sampling; the accepted design is uniform over all
                 valid designs).  Views = depth 1 and depth 6 -> 120.
  B n1_benign    the -BEN twin (same base item, same model run) of the same 60
                 pairs at depth 1 and 6 -> 120.
  C tie_audit    every BEN view of the five runs whose panel critical_failure
                 is true and that is not in B.
  D calibration_spread
                 N_D = 300 - |A| - |B| - |C| RISK views (risk_group != CTRL)
                 not in A.  n_dis = ceil(N_D / 2) from judge-disagreement views
                 (among status-ok judges: some D dimension with max - min >= 2,
                 or critical_failure not unanimous), then n_rand = N_D - n_dis
                 uniformly from the remaining RISK views not in A.  Each half is
                 split over the 5 models as evenly as possible: every model gets
                 floor(n/5); the remainders go to models in one seeded random
                 model order, the disagreement half from its start and the
                 random half continuing cyclically, so the per-model D totals
                 differ by at most one.  Within a model the views are drawn
                 uniformly without replacement.
  calibration    10 RISK views outside the 300, from conversations (run_dir,
                 item_id) that have no view in the 300; greedy over a seeded
                 shuffle with exactly 2 per model, at most 2 per risk group and
                 at most 2 per depth.  Training only, never analysed.

Outputs (research/phaseB/): sample_phaseB_v1.csv, key_phaseB_v1.csv (view_code
-> everything; never given to raters), calibration_phaseB_v1.csv and
sample_phaseB_v1_summary.json (counts + sha256s).  Nothing is written under
result/.

Run:  cd /home/wjeong/adol && PYTHONPATH=src ~/envs/jeongwoncheol_adol/bin/python \
        research/phaseB/sample_phaseB.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kyra.analysis.loader import split_item_id  # noqa: E402

SEED = 20260926
N_TOTAL = 300
N_PAIRS = 60
PER_MODEL_PAIRS = 12
N_CALIB = 10
D_KEYS = ("D1", "D2", "D3", "D4", "D5", "D6")
JUDGES = ("J1", "J2", "J3")
ITEMS = ROOT / "research" / "items" / "items_phaseA_v1.jsonl"
RUN_GLOB = "result/raw/phaseA_T1/*/main/*/"
EXCLUDED_RUN = "result/raw/phaseA_T1/LGAI-EXAONE-EXAONE-4.0-32B-AWQ/main/20260922T1239Z-b936cd"
OUT = ROOT / "research" / "phaseB"

STRATA = ("n1_risk", "n1_benign", "tie_audit", "calibration_spread")
SAMPLE_COLUMNS = ("view_code", "stratum", "run_dir", "model_id", "item_id",
                  "condition", "depth", "task", "panel_critical_failure",
                  "panel_cf_tie")
KEY_COLUMNS = SAMPLE_COLUMNS + (
    "base_item", "item_condition", "risk_group", "localization", "turn_type",
    "n_turns", "panel_status") + tuple("panel_" + d for d in D_KEYS) + (
    "panel_over_refusal", "panel_helpfulness", "panel_judges_used",
    "panel_judges_error", "judge_disagreement", "d_half")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def discover_runs():
    runs = []
    for d in sorted(ROOT.glob(RUN_GLOB)):
        if (d / "panel.jsonl").is_file() and (d / "MARKER").is_file():
            rel = d.relative_to(ROOT).as_posix().rstrip("/")
            if rel == EXCLUDED_RUN:
                raise SystemExit("excluded run dir unexpectedly has panel + MARKER")
            models = {r["model_id"] for r in read_jsonl(d / "manifest.jsonl")}
            if len(models) != 1:
                raise SystemExit("%s: manifest names %d models" % (rel, len(models)))
            runs.append((rel, models.pop()))
    if len(runs) != 5 or len({m for _, m in runs}) != 5:
        raise SystemExit("expected exactly 5 main runs with 5 distinct models, got %r" % runs)
    return runs


def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v)
    return str(v)


def build_views(runs, items):
    """Every judged view of the five runs, with panel fields and the disagreement flag."""
    views = []
    for rel, model in runs:
        d = ROOT / rel
        judge = {}
        for j in JUDGES:
            for r in read_jsonl(d / ("judge_%s.jsonl" % j)):
                key = (r["item_id"], r["condition"], int(r["depth"]))
                if (j, key) in judge:
                    raise SystemExit("%s: duplicate %s record %r" % (rel, j, key))
                judge[(j, key)] = r
        for p in read_jsonl(d / "panel.jsonl"):
            item = items[p["item_id"]]
            key = (p["item_id"], p["condition"], int(p["depth"]))
            ok = [judge[(j, key)]["record"] for j in JUDGES
                  if (j, key) in judge and judge[(j, key)]["status"] == "ok"]
            disagree = False
            if len(ok) >= 2:
                for k in D_KEYS:
                    vals = [int(r["D"][k]) for r in ok]
                    if max(vals) - min(vals) >= 2:
                        disagree = True
                if len({bool(r["critical_failure"]) for r in ok}) > 1:
                    disagree = True
            base, cond = split_item_id(p["item_id"])
            v = {
                "run_dir": rel, "model_id": model, "item_id": p["item_id"],
                "condition": p["condition"], "depth": int(p["depth"]),
                "task": "CONTROL" if item["risk_group"] == "CTRL" else "RISK",
                "panel_critical_failure": p.get("critical_failure"),
                "panel_cf_tie": p.get("cf_tie"),
                "base_item": base, "item_condition": cond,
                "risk_group": item["risk_group"], "localization": item["localization"],
                "turn_type": item["turn_type"], "n_turns": len(item["turns"]),
                "panel_status": p["status"],
                "panel_over_refusal": p.get("over_refusal"),
                "panel_helpfulness": p.get("helpfulness"),
                "panel_judges_used": p.get("judges_used") or [],
                "panel_judges_error": p.get("judges_error") or [],
                "judge_disagreement": disagree,
                "d_half": "",
            }
            for k in D_KEYS:
                v["panel_" + k] = (p.get("D") or {}).get(k)
            views.append(v)
    views.sort(key=vkey)
    return views


def vkey(v):
    return (v["run_dir"], v["item_id"], v["condition"], v["depth"])


def design_stratum_a(scenarios, models, rng):
    n_s, n_m = len(scenarios), len(models)
    three = set(int(i) for i in rng.choice(n_s, size=N_PAIRS - 2 * n_s, replace=False))
    sizes = [3 if i in three else 2 for i in range(n_s)]
    for attempt in range(1, 1_000_001):
        rows = [sorted(int(x) for x in rng.choice(n_m, size=s, replace=False)) for s in sizes]
        cols = Counter(m for r in rows for m in r)
        if all(cols[m] == PER_MODEL_PAIRS for m in range(n_m)):
            pairs = [(scenarios[i], models[m]) for i, r in enumerate(rows) for m in r]
            return pairs, attempt
    raise SystemExit("stratum A: no valid design in 1e6 attempts")


def even_quotas(n, order, start):
    """floor(n/5) each; the n % 5 remainders to order[start], order[start+1], ... cyclically."""
    q = {m: n // len(order) for m in order}
    for i in range(n % len(order)):
        q[order[(start + i) % len(order)]] += 1
    return q


def draw(pool, k, rng, what):
    if k > len(pool):
        raise SystemExit("%s: need %d views, pool has %d" % (what, k, len(pool)))
    idx = sorted(int(i) for i in rng.choice(len(pool), size=k, replace=False))
    return [pool[i] for i in idx]


def main() -> int:
    items = {r["item_id"]: r for r in read_jsonl(ITEMS)}
    runs = discover_runs()
    run_of = {m: rel for rel, m in runs}
    models = sorted(run_of)
    views = build_views(runs, items)
    index = {vkey(v): v for v in views}

    # -- stratum A / B --------------------------------------------------------
    scenarios = sorted(i for i, it in items.items()
                       if it["risk_group"] != "CTRL" and len(it["turns"]) == 6
                       and it["localization"] == "localized")
    if len(scenarios) != 24:
        raise SystemExit("expected 24 six-turn localized risk scripts, got %d" % len(scenarios))
    pairs, attempts = design_stratum_a(scenarios, models, np.random.default_rng([SEED, 1]))
    chosen = {}  # vkey -> (stratum, view)

    def take(v, stratum):
        k = vkey(v)
        if k in chosen:
            raise SystemExit("view %r selected twice" % (k,))
        chosen[k] = stratum

    cond_of = {}
    for scen, model in pairs:
        rel = run_of[model]
        base, _ = split_item_id(scen)
        twin = base + "-BEN"
        if twin not in items or len(items[twin]["turns"]) != 6:
            raise SystemExit("%s: no six-turn BEN twin" % scen)
        for item_id, stratum in ((scen, "n1_risk"), (twin, "n1_benign")):
            conds = sorted({v["condition"] for v in views
                            if v["run_dir"] == rel and v["item_id"] == item_id})
            if len(conds) != 1:
                raise SystemExit("%s/%s: expected one run condition, got %r" % (rel, item_id, conds))
            cond_of[(rel, item_id)] = conds[0]
            for depth in (1, 6):
                take(index[(rel, item_id, conds[0], depth)], stratum)

    # -- stratum C --------------------------------------------------------------
    ben_flagged = [v for v in views if v["item_condition"] == "BEN"
                   and v["panel_critical_failure"] is True]
    b_flagged = [v for v in ben_flagged if chosen.get(vkey(v)) == "n1_benign"]
    for v in ben_flagged:
        if vkey(v) not in chosen:
            take(v, "tie_audit")
    n_c = sum(1 for s in chosen.values() if s == "tie_audit")

    # -- stratum D --------------------------------------------------------------
    n_d = N_TOTAL - len(chosen)
    if n_d < 0:
        raise SystemExit("strata A+B+C already exceed %d views" % N_TOTAL)
    n_dis = (n_d + 1) // 2
    n_rand = n_d - n_dis
    rng_d = np.random.default_rng([SEED, 2])
    order = [str(m) for m in rng_d.permutation(models)]
    q_dis = even_quotas(n_dis, order, 0)
    q_rand = even_quotas(n_rand, order, n_dis % len(order))
    a_keys = {k for k, s in chosen.items() if s == "n1_risk"}
    risk_pool = [v for v in views if v["task"] == "RISK" and vkey(v) not in a_keys]
    pool_sizes = {}
    for m in models:
        pool_m = [v for v in risk_pool if v["model_id"] == m and v["judge_disagreement"]]
        pool_sizes[m] = {"disagreement": len(pool_m)}
        for v in draw(pool_m, q_dis[m], rng_d, "D disagreement %s" % m):
            v["d_half"] = "disagreement"
            take(v, "calibration_spread")
    for m in models:
        pool_m = [v for v in risk_pool if v["model_id"] == m and vkey(v) not in chosen]
        pool_sizes[m]["random"] = len(pool_m)
        for v in draw(pool_m, q_rand[m], rng_d, "D random %s" % m):
            v["d_half"] = "random"
            take(v, "calibration_spread")
    if len(chosen) != N_TOTAL:
        raise SystemExit("sample has %d views, expected %d" % (len(chosen), N_TOTAL))

    # -- calibration set ----------------------------------------------------------
    used_conv = {(k[0], k[1]) for k in chosen}
    cal_pool = [v for v in views if v["task"] == "RISK" and vkey(v) not in chosen
                and (v["run_dir"], v["item_id"]) not in used_conv]
    rng_c = np.random.default_rng([SEED, 3])
    per_m, per_g, per_d, calib = Counter(), Counter(), Counter(), []
    for i in rng_c.permutation(len(cal_pool)):
        v = cal_pool[int(i)]
        if per_m[v["model_id"]] >= 2 or per_g[v["risk_group"]] >= 2 or per_d[v["depth"]] >= 2:
            continue
        if any((c["run_dir"], c["item_id"]) == (v["run_dir"], v["item_id"]) for c in calib):
            continue
        calib.append(dict(v, stratum="calibration", view_code="C%02d" % (len(calib) + 1)))
        per_m[v["model_id"]] += 1
        per_g[v["risk_group"]] += 1
        per_d[v["depth"]] += 1
        if len(calib) == N_CALIB:
            break
    if len(calib) != N_CALIB:
        raise SystemExit("calibration: only %d views found" % len(calib))

    # -- view codes -----------------------------------------------------------------
    rank = {s: i for i, s in enumerate(STRATA)}
    rows = sorted((dict(index[k], stratum=s) for k, s in chosen.items()),
                  key=lambda v: (rank[v["stratum"]],) + vkey(v))
    perm = np.random.default_rng([SEED, 4]).permutation(len(rows))
    for code, i in enumerate(perm, start=1):
        rows[int(i)]["view_code"] = "V%03d" % code
    rows.sort(key=lambda v: v["view_code"])

    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "sample": OUT / "sample_phaseB_v1.csv",
        "key": OUT / "key_phaseB_v1.csv",
        "calibration": OUT / "calibration_phaseB_v1.csv",
    }
    for name, cols, data in (("sample", SAMPLE_COLUMNS, rows), ("key", KEY_COLUMNS, rows),
                             ("calibration", KEY_COLUMNS, calib)):
        with paths[name].open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for v in data:
                w.writerow([fmt(v[c]) for c in cols])

    by_stratum = Counter(v["stratum"] for v in rows)
    per_model = {s: dict(sorted(Counter(v["model_id"] for v in rows if v["stratum"] == s).items()))
                 for s in STRATA}
    scen_counts = Counter(s for s, _ in pairs)
    summary = {
        "version": "pB-v1",
        "seed": SEED,
        "generators": "numpy.random.default_rng([seed, k]); k=1 stratum A, 2 stratum D, "
                      "3 calibration, 4 view-code shuffle",
        "runs": [{"run_dir": rel, "model_id": m} for rel, m in runs],
        "excluded_run": EXCLUDED_RUN,
        "n_views_universe": len(views),
        "counts": {"n1_risk": by_stratum["n1_risk"], "n1_benign": by_stratum["n1_benign"],
                   "tie_audit": by_stratum["tie_audit"],
                   "calibration_spread": by_stratum["calibration_spread"],
                   "total": len(rows), "calibration": len(calib)},
        "counts_by_task": dict(Counter(v["task"] for v in rows)),
        "per_model": {"all": dict(sorted(Counter(v["model_id"] for v in rows).items())),
                      **per_model},
        "stratum_a": {
            "algorithm": "12 of 24 scenarios drawn uniformly to carry 3 pairs (others 2); "
                         "per scenario a uniform random model subset of that size; whole "
                         "design accepted only if every model has exactly 12 pairs "
                         "(rejection sampling)",
            "rejection_attempts": attempts,
            "pairs_per_model": dict(sorted(Counter(m for _, m in pairs).items())),
            "scenarios_by_pair_count": dict(sorted(Counter(scen_counts.values()).items())),
            "pairs": [{"scenario": s, "model_id": m} for s, m in sorted(pairs)],
        },
        "stratum_c": {
            "ben_views_panel_flagged_total": len(ben_flagged),
            "ben_flagged_already_in_b": len(b_flagged),
            "ben_flagged_in_b_by_depth_tie": dict(sorted(Counter(
                "depth%d_tie%s" % (v["depth"], v["panel_cf_tie"]) for v in b_flagged).items())),
            "tie_audit_count": n_c,
            "tie_audit_by_depth_tie": dict(sorted(Counter(
                "depth%d_tie%s" % (v["depth"], v["panel_cf_tie"])
                for v in rows if v["stratum"] == "tie_audit").items())),
        },
        "stratum_d": {
            "n": n_d, "n_disagreement": n_dis, "n_random": n_rand,
            "model_remainder_order": order,
            "quota_disagreement": q_dis, "quota_random": q_rand,
            "pool_sizes": pool_sizes,
            "disagreement_definition": "among status-ok judges (>= 2): some D dimension "
                                       "max-min >= 2, or critical_failure not unanimous",
            "random_half_pool": "RISK views not in A and not already drawn",
            "depths": dict(sorted(Counter(v["depth"] for v in rows
                                          if v["stratum"] == "calibration_spread").items())),
        },
        "calibration": {
            "rule": "RISK views outside the 300 from conversations with no view in the "
                    "300; 2 per model, <= 2 per risk group, <= 2 per depth",
            "per_model": dict(sorted(per_m.items())),
            "per_risk_group": dict(sorted(per_g.items())),
            "per_depth": {str(k): v for k, v in sorted(per_d.items())},
        },
        "sha256": {name: sha256(p) for name, p in paths.items()},
        "input_sha256": {
            "items": sha256(ITEMS),
            **{"%s/%s" % (rel, f): sha256(ROOT / rel / f)
               for rel, _ in runs for f in ("panel.jsonl", "responses.jsonl",
                                            "judge_J1.jsonl", "judge_J2.jsonl",
                                            "judge_J3.jsonl")},
        },
    }
    spath = OUT / "sample_phaseB_v1_summary.json"
    spath.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    print(json.dumps(summary["counts"]), json.dumps(summary["stratum_c"]["tie_audit_count"]))
    for name, p in paths.items():
        print(name, p.relative_to(ROOT), summary["sha256"][name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
