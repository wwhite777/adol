"""Compare two judge JSONL files on the same views: python compare2.py A.jsonl B.jsonl [labelA labelB]"""
import json, sys, collections
a_path, b_path = sys.argv[1], sys.argv[2]
la = sys.argv[3] if len(sys.argv) > 3 else "A"; lb = sys.argv[4] if len(sys.argv) > 4 else "B"
A = {(r["item_id"], r["condition"], r["depth"]): r for r in map(json.loads, open(a_path))}
B = {(r["item_id"], r["condition"], r["depth"]): r for r in map(json.loads, open(b_path))}
keys = sorted(set(A) & set(B))
print("%s vs %s | views %d / %d, common %d | identical prompts %d" % (la, lb, len(A), len(B), len(keys), sum(A[k]["prompt_sha256"] == B[k]["prompt_sha256"] for k in keys)))
print("status pairs:", dict(collections.Counter((A[k]["status"], B[k]["status"]) for k in keys)))
raw = sum(A[k]["raw_text_sha256"] == B[k]["raw_text_sha256"] for k in keys)
print("byte-identical judge text: %d / %d = %.1f%%" % (raw, len(keys), 100.0 * raw / len(keys)))
ok = [k for k in keys if A[k]["status"] == "ok" and B[k]["status"] == "ok"]
def sc(r):
    x = r["record"]; return (json.dumps(x.get("D"), sort_keys=True), json.dumps(x.get("A"), sort_keys=True), x.get("critical_failure"), json.dumps(sorted(x.get("cf_codes") or [])), x.get("over_refusal"), x.get("helpfulness"))
eq = sum(sc(A[k]) == sc(B[k]) for k in ok)
print("both ok %d | identical scores %d (%.1f%%)" % (len(ok), eq, 100.0 * eq / max(1, len(ok))))
dd = collections.Counter()
for k in ok:
    if sc(A[k]) != sc(B[k]):
        for d in ("D1", "D2", "D3", "D4", "D5", "D6"):
            if A[k]["record"]["D"][d] != B[k]["record"]["D"][d]: dd[d] += 1
        if A[k]["record"]["A"] != B[k]["record"]["A"]: dd["A"] += 1
        if A[k]["record"]["critical_failure"] != B[k]["record"]["critical_failure"]: dd["critical"] += 1
print("differing-field counts among differing views:", dict(dd))
