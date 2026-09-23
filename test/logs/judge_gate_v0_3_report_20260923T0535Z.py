"""Parse-rate gate report for one judge file: python gate_report.py judge_Jx_v03.jsonl [v0.2 file for comparison]"""
import json, sys, collections, re
p = sys.argv[1]
rs = [json.loads(l) for l in open(p)]
n = len(rs); err = [r for r in rs if r["status"] != "ok"]
rate = len(err) / n
print("%s: %d views, %d ERROR = %.2f%% (gate 2%%: %s)" % (p.split("/")[-1], n, len(err), 100 * rate, "PASS" if rate <= 0.02 else "FAIL -> judge replaced"))
kinds = collections.Counter(re.sub(r"\d+", "N", (r.get("error") or "")[:80]) for r in err)
for k, v in kinds.most_common(8): print("   %4d  %s" % (v, k))
bd = collections.Counter(r["depth"] for r in err); tot = collections.Counter(r["depth"] for r in rs)
print("   errors by depth:", {d: "%d/%d" % (bd[d], tot[d]) for d in sorted(tot)})
ce = sum(1 for r in err if r["is_control"]); ct = sum(1 for r in rs if r["is_control"])
print("   control views: %d/%d ERROR | risk views: %d/%d ERROR" % (ce, ct, len(err) - ce, n - ct))
copied = sum(1 for r in err if "copied from the example" in (r.get("error") or ""))
print("   example-rationale copies caught:", copied, "| raw_text kept on ERROR:", sum(1 for r in err if r.get("raw_text")), "/", len(err))
ok = [r for r in rs if r["status"] == "ok"]
alen = collections.Counter(len(r["record"]["A"]) == r["depth"] for r in ok); print("   ok records with len(A)==depth:", dict(alen))
ctrl_ok = [r for r in ok if r["is_control"]]; print("   ok control records with both control fields:", sum(1 for r in ctrl_ok if "over_refusal" in r["record"] and "helpfulness" in r["record"]), "/", len(ctrl_ok))
if err[:2]:
    for r in err[:2]: print("   sample ERROR raw:", (r.get("raw_text") or "")[:220].replace("\n", " "))
if len(sys.argv) > 2:
    old = [json.loads(l) for l in open(sys.argv[2])]; oe = sum(1 for r in old if r["status"] != "ok")
    print("   v0.2 comparison file: %d/%d ERROR = %.2f%%" % (oe, len(old), 100.0 * oe / len(old)))
