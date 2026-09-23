"""Batched (64) vs sequential (v0.2, on-disk) J1 judge outputs on the same 564 prompts."""
import json, sys, collections

seq_path = "result/raw/phaseA_T1/superseded_judge_prompt_v0.2/Qwen-main/judge_J1.jsonl"
bat_path = "/tmp/claude-1011/-home-wjeong/407cdd4b-f055-4859-8e47-fbc41fca59f3/scratchpad/batchcmp/judge_J1_batched.jsonl"
seq = {(r["item_id"], r["condition"], r["depth"]): r for r in map(json.loads, open(seq_path))}
bat = {(r["item_id"], r["condition"], r["depth"]): r for r in map(json.loads, open(bat_path))}
print("views: sequential %d, batched %d, common %d" % (len(seq), len(bat), len(set(seq) & set(bat))))
keys = sorted(set(seq) & set(bat))
same_prompt = sum(1 for k in keys if seq[k]["prompt_sha256"] == bat[k]["prompt_sha256"])
print("identical prompt_sha256: %d / %d" % (same_prompt, len(keys)))
st = collections.Counter((seq[k]["status"], bat[k]["status"]) for k in keys)
print("status pairs (sequential, batched):", dict(st))
raw_same = sum(1 for k in keys if seq[k]["raw_text_sha256"] == bat[k]["raw_text_sha256"])
print("identical raw_text_sha256 (byte-identical judge text): %d / %d = %.1f%%" % (raw_same, len(keys), 100.0 * raw_same / len(keys)))
both_ok = [k for k in keys if seq[k]["status"] == "ok" and bat[k]["status"] == "ok"]
def scores(rec):
    r = rec["record"]
    return (json.dumps(r.get("D"), sort_keys=True), json.dumps(r.get("A"), sort_keys=True), r.get("critical_failure"), json.dumps(sorted(r.get("cf_codes") or [])), r.get("over_refusal"), r.get("helpfulness"))
eq_scores = sum(1 for k in both_ok if scores(seq[k]) == scores(bat[k]))
eq_rat = sum(1 for k in both_ok if (seq[k]["record"].get("rationale") or "").strip() == (bat[k]["record"].get("rationale") or "").strip())
print("both ok: %d | identical scores (D, A, critical, cf, control fields): %d (%.1f%%) | identical rationale: %d" % (len(both_ok), eq_scores, 100.0 * eq_scores / max(1, len(both_ok)), eq_rat))
diff = [k for k in both_ok if scores(seq[k]) != scores(bat[k])]
for k in diff[:8]:
    print("  differs:", k, "| seq D", seq[k]["record"]["D"], "| bat D", bat[k]["record"]["D"], "| A eq:", seq[k]["record"]["A"] == bat[k]["record"]["A"])
by_depth_bat = collections.Counter(bat[k]["depth"] for k in keys if bat[k]["status"] != "ok"); tot = collections.Counter(k[2] for k in keys)
print("batched ERROR by depth:", {d: "%d/%d" % (by_depth_bat[d], tot[d]) for d in sorted(tot)})
meta = json.load(open(bat_path.replace(".jsonl", ".meta.json")))
print("meta:", {k: meta[k] for k in ("decode_mode", "batch_size", "n_views", "n_ok", "n_parse_errors_first_pass", "n_retried", "n_error_final", "started_utc", "finished_utc")})
