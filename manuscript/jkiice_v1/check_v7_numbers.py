"""Self-check of the numbers added in manuscript content v7 against the post hoc result files.

Every expected string is built from the result CSV/JSON (never typed by hand) and must occur in
content_v7.py. Exit 0 = all found; 1 = at least one missing (each listed). --plant replaces one
expected value with a wrong one to prove the check can fail.
"""
import csv, sys
from pathlib import Path

ROOT = Path("/home/wjeong/adol")
RD = ROOT / "result/analysis/phaseA_T1/posthoc_rd_20261001T0226Z"
HCX = ROOT / "result/analysis/phaseA_T1/hcx_plan_scan_20261001T0258Z/hcx_plan_scan.csv"
text = (ROOT / "manuscript/jkiice_v1/content_v7.py").read_text(encoding="utf-8")

a = {r["labeling"]: r for r in csv.DictReader(open(RD / "a_rd_did.csv", encoding="utf-8"))}
b = {r["labeling"]: r for r in csv.DictReader(open(RD / "b_benign_or.csv", encoding="utf-8"))}
c = {(r["labeling"], r["arm"]): r for r in csv.DictReader(open(RD / "c_vb_scenario_sd.csv", encoding="utf-8"))}
h = [r for r in csv.DictReader(open(HCX, encoding="utf-8"))]

pp = lambda x: "%.1f" % (100 * float(x))            # proportion -> percentage points, 1 decimal
f1 = lambda x: "%.1f" % float(x)
f2 = lambda x: "%.2f" % float(x)
def ci(x, lo, hi, neg_to=False):
    lo_s, hi_s = pp(lo), pp(hi)
    if lo_s.startswith("-"):
        lo_s = "−" + lo_s[1:]
    return "%s (%s%s%s)" % (pp(x), lo_s, " to " if neg_to else "-", hi_s)
def rng(vals, fmt):
    v = sorted(float(x) for x in vals)
    return "%s–%s" % (fmt(v[0]), fmt(v[-1]))
def thou(x):
    return "{:,}".format(int(round(float(x))))

S = ["S1", "S2", "S3"]
exp = {}
for lab, neg in (("S0", True), ("S1", False), ("S2", False), ("S3", False), ("R1", True), ("R2", False)):
    exp["T7 DiD " + lab] = ci(a[lab]["did"], a[lab]["did_lo"], a[lab]["did_hi"], neg_to=neg)
exp["abstract DiD range"] = rng([a[k]["did"] for k in S + ["R2"]], pp) + "%p"
ev = sorted(int(a[k]["benign_d1_k"]) + int(a[k]["benign_d6_k"]) for k in S + ["R2"])
exp["abstract benign events EN"] = "only %d–%d benign events" % (ev[0], ev[-1])
exp["abstract benign events KO"] = "사건이 %d–%d건" % (ev[0], ev[-1])
s0 = a["S0"]
exp["RD risk S0"] = "위험 대본 %s%%p(95%% CI %s–%s)" % (pp(s0["rd_risk"]), pp(s0["rd_risk_lo"]), pp(s0["rd_risk_hi"]))
exp["RD benign S0"] = "무해 쌍둥이 %s%%p\"\n      \"(%s–%s)" % (pp(s0["rd_benign"]), pp(s0["rd_benign_lo"]), pp(s0["rd_benign_hi"]))
exp["DiD S0 text"] = "%s%%p(−%s–%s)" % (pp(s0["did"]), pp(s0["did_lo"])[1:], pp(s0["did_hi"]))
exp["denominators"] = "S1 %s·%s, S2 %s·%s, S3 %s·%s" % tuple(x for k in S for x in (a[k]["benign_d1_n"], a[k]["benign_d6_n"]))
exp["exact lower"] = "하한 " + rng([b[k]["exact_lo"] for k in S], f2)
exp["firth or"] = rng([b[k]["firth_or"] for k in S], f1)
exp["firth pl lower"] = "하한 " + rng([b[k]["firth_pl_lo"] for k in S], f2)
exp["firth pl upper"] = "상한 %s–%s" % (thou(min(float(b[k]["firth_pl_hi"]) for k in S)), thou(max(float(b[k]["firth_pl_hi"]) for k in S)))
exp["S0 exact"] = "%s[%s–%s]" % (f1(b["S0"]["exact_or"]), f1(b["S0"]["exact_lo"]), "%d" % round(float(b["S0"]["exact_hi"])))
exp["S0 firth"] = "%s[%s–%s]" % (f1(b["S0"]["firth_or"]), f1(b["S0"]["firth_pl_lo"]), "%d" % round(float(b["S0"]["firth_pl_hi"])))
exp["benign RD S1-S3"] = rng([a[k]["rd_benign"] for k in S], pp) + "%p"
exp["DiD S1-S3"] = rng([a[k]["did"] for k in S], pp) + "%p(95% CI 하한 " + rng([a[k]["did_lo"] for k in S], pp) + ")"
exp["SD risk"] = rng([c[(k, "risk")]["sd_median"] for k in ["S0"] + S], f2)
exp["SD benign"] = rng([c[(k, "benign")]["sd_median"] for k in ["S0"] + S], f2)
r1, r2 = a["R1"], a["R2"]
exp["R2 benign RD"] = "%s%%p(%s–%s)" % (pp(r2["rd_benign"]), "%d" % round(100 * float(r2["rd_benign_lo"])), pp(r2["rd_benign_hi"]))
exp["R2 DiD"] = "%s%%p(%s–%s)" % (pp(r2["did"]), pp(r2["did_lo"]), pp(r2["did_hi"]))
exp["R1 pair"] = "%s%%p와 %s%%p" % (pp(r1["rd_benign"]), pp(r1["did"]))
hx = {r["condition"]: r for r in h if r["model_dir"].startswith("naver-hyperclovax")}
exp["HCX main"] = "%s개 중 %s개" % (hx["main"]["n_replies"], hx["main"]["n_flagged"])
exp["HCX repeats"] = "116개 중 %s·%s·%s개" % tuple(hx["repeat_%d" % i]["n_flagged"] for i in (1, 2, 3))
others = [int(r["n_flagged"]) for r in h if r["condition"] == "main" and not r["model_dir"].startswith("naver")]
exp["others main"] = "다른 네 모델의 주 실행에서는 %d–%d개" % (min(others), max(others))

if "--plant" in sys.argv:
    exp["T7 DiD S1"] = exp["T7 DiD S1"].replace("12.7", "12.9")
missing = [(k, v) for k, v in exp.items() if v not in text]
for k, v in exp.items():
    print("%-28s %-8s %s" % (k, "ok" if v in text else "MISSING", v.replace("\n", "\\n")))
print("checked %d, missing %d" % (len(exp), len(missing)))
sys.exit(1 if missing else 0)
