"""Scoring progress across phaseA_T1 run directories: judge files, sidecar parse rates, panels.

    ~/envs/jeongwoncheol_adol/bin/python bin/scoring_progress.py [result/raw/phaseA_T1]
"""
import glob, json, os, sys

root = sys.argv[1] if len(sys.argv) > 1 else "result/raw/phaseA_T1"
rows = []
for run_dir in sorted(glob.glob(os.path.join(root, "*", "*", "*"))):
    if not os.path.isfile(os.path.join(run_dir, "MARKER")):
        continue
    model = run_dir.split(os.sep)[-3]; tag = run_dir.split(os.sep)[-2]
    judges = {}
    for meta in sorted(glob.glob(os.path.join(run_dir, "judge_*.meta.json"))):
        if ".shard" in os.path.basename(meta):
            continue  # judge_<id>.shard<k>of<N>.*: a slice, counted via the merged file
        m = json.load(open(meta, encoding="utf-8"))
        jid = m.get("judge_id") or os.path.basename(meta)[6:-10]
        n = m.get("n_views") or 0; e = m.get("n_error_final") or 0
        pinned = (m.get("provider_effective_params") or {}).get("vllm_env", {}).get("VLLM_BATCH_INVARIANT") == "1" and \
                 (m.get("provider_effective_params") or {}).get("engine_kwargs", {}).get("attention_backend") == "FLASH_ATTN"
        judges[jid] = "%d/%d=%.1f%%%s" % (e, n, 100.0 * e / max(1, n), "" if pinned else " UNPINNED")
    panel = os.path.join(run_dir, "panel.jsonl")
    n_panel = sum(1 for _ in open(panel, encoding="utf-8")) if os.path.isfile(panel) else 0
    rows.append((model, tag, judges, n_panel))
for model, tag, judges, n_panel in rows:
    print("%-45s %-9s judges(ERROR/views): %s | panel records: %d" % (model[:45], tag, ", ".join("%s %s" % kv for kv in sorted(judges.items())) or "-", n_panel))
done = sum(1 for r in rows if len(r[2]) == 3 and r[3] > 0)
print("run dirs with 3 judges + panel: %d / %d" % (done, len(rows)))
