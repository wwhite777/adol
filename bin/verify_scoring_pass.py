"""Verify one model's scoring pass against the pinned procedure (no score values are printed).

    ~/envs/jeongwoncheol_adol/bin/python bin/verify_scoring_pass.py <label> <model_dir> [--marker <file>] [--record <campaign_*_scoring.json>]

Run from the repo root. Receipt: the launcher marker (exit=0), or — when the marker is stale or missing — the campaign's
own scoring record (--record): status "completed" and exit-0 judge_runs for J1/J2/J3 plus an exit-0 panel_run for every
marked run dir (the record is written by the scoring process itself, never by hand; the marker's staleness is printed).
Checks: receipt; every run dir with a MARKER has judge_J1/J2/J3.jsonl + .meta.json and panel.jsonl;
each sidecar records the pinned procedure (batch_size 1, decode_mode sequential, enable_prefix_caching false,
attention_backend FLASH_ATTN, max_model_len 16384, VLLM_BATCH_INVARIANT=1, template sha 65460efc…, anchors sha
7f54fdbd…); n_views equals the panel record count; no unmerged shard file in a run-dir root; per-judge ERROR
rates are reported with denominators (the prereg bar is 2% per judge). Exit 0 = all checks pass, 1 = a check failed.
"""
import glob, json, os, sys

TEMPLATE_SHA = "65460efc95d2415f85f5020a3c028165b0a6051c0e28eb6bf86213869bf94921"
ANCHORS_SHA = "7f54fdbded6071d7f5e202d1b7820fe4a64b454dc695b6eb39def227c3373679"
PINNED_ENGINE = {"attention_backend": "FLASH_ATTN", "enable_prefix_caching": False, "max_model_len": 16384}


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    label, model_dir = argv[0], argv[1].rstrip("/")
    opts = dict(zip(argv[2::2], argv[3::2]))
    marker = opts.get("--marker", "result/raw/phaseA_T1_score_%s.DONE" % label)
    record = opts.get("--record")
    failures = []
    run_dirs = sorted(d for d in glob.glob(os.path.join(model_dir, "*", "*")) if os.path.isfile(os.path.join(d, "MARKER")))
    print("run dirs with MARKER:", len(run_dirs), "(expect 4)")
    if len(run_dirs) != 4: failures.append("expected 4 marked run dirs, found %d" % len(run_dirs))
    receipt_ok, why = False, []
    if os.path.isfile(marker):
        text = open(marker, encoding="utf-8").read().strip()
        print("marker:", text)
        receipt_ok = "exit=0" in text
        if not receipt_ok: why.append("marker exit != 0")
    else:
        why.append("marker missing: %s" % marker)
    if not receipt_ok and record:
        r = json.load(open(record, encoding="utf-8"))
        want = sorted(os.path.abspath(d) for d in run_dirs)
        ok_j = {(os.path.abspath(j.get("run_dir", "")), j.get("judge_id")) for j in r.get("judge_runs", []) if j.get("exit_code") == 0 and not j.get("failure")}
        ok_p = {os.path.abspath(p.get("run_dir", "")) for p in r.get("panel_runs", []) if p.get("exit_code") == 0 and not p.get("failure")}
        tag = lambda d: d.split(os.sep)[-2]
        missing = ["%s/%s" % (tag(d), jid) for d in want for jid in ("J1", "J2", "J3") if (d, jid) not in ok_j]
        missing += ["%s/panel" % tag(d) for d in want if d not in ok_p]
        if r.get("status") == "completed" and not missing and len(want) == 4:
            receipt_ok = True
            print("receipt: campaign record %s status=completed; exit-0 entries cover all 4 run dirs x (J1,J2,J3,panel) [%d judge, %d panel]; marker stale: %s" % (record, len(ok_j), len(ok_p), "; ".join(why)))
        else:
            why.append("record %s: status=%s, missing exit-0 entries: %s" % (record, r.get("status"), ", ".join(missing) or "none"))
    if not receipt_ok: failures.extend(why)
    for d in run_dirs:
        tag = d.split(os.sep)[-2]
        panel = os.path.join(d, "panel.jsonl")
        n_panel = sum(1 for _ in open(panel, encoding="utf-8")) if os.path.isfile(panel) else 0
        if n_panel == 0: failures.append("%s: panel.jsonl missing or empty" % tag)
        stray = [f for f in os.listdir(d) if ".shard" in f]
        if stray: failures.append("%s: unmerged shard file(s) in run dir root: %s" % (tag, ", ".join(stray)))
        for jid in ("J1", "J2", "J3"):
            jf, mf = os.path.join(d, "judge_%s.jsonl" % jid), os.path.join(d, "judge_%s.meta.json" % jid)
            if not (os.path.isfile(jf) and os.path.isfile(mf)):
                failures.append("%s: judge %s file or sidecar missing" % (tag, jid)); continue
            m = json.load(open(mf, encoding="utf-8")); pep = m.get("provider_effective_params") or {}
            n, e = m.get("n_views") or 0, m.get("n_error_final") or 0
            rate = 100.0 * e / max(1, n)
            print("  %-9s %s: %d/%d ERROR = %.2f%% | first-pass re-asks %s | %s" % (tag, jid, e, n, rate, m.get("n_parse_errors_first_pass"), "shards %s" % m.get("shards") if m.get("shards") else "single engine"))
            if rate > 2.0: failures.append("%s %s: ERROR rate %.2f%% > 2%% (prereg bar; report + decide)" % (tag, jid, rate))
            if n != n_panel: failures.append("%s %s: n_views %d != panel records %d" % (tag, jid, n, n_panel))
            if m.get("batch_size") != 1 or m.get("decode_mode") != "sequential": failures.append("%s %s: not sequential batch 1 (%s/%s)" % (tag, jid, m.get("decode_mode"), m.get("batch_size")))
            if m.get("prompt_template_sha256") != TEMPLATE_SHA: failures.append("%s %s: template sha %s" % (tag, jid, str(m.get("prompt_template_sha256"))[:12]))
            if m.get("anchors_sha256") != ANCHORS_SHA: failures.append("%s %s: anchors sha %s" % (tag, jid, str(m.get("anchors_sha256"))[:12]))
            if (pep.get("engine_kwargs") or {}) != PINNED_ENGINE: failures.append("%s %s: engine kwargs %s" % (tag, jid, pep.get("engine_kwargs")))
            if (pep.get("vllm_env") or {}).get("VLLM_BATCH_INVARIANT") != "1": failures.append("%s %s: VLLM_BATCH_INVARIANT not 1" % (tag, jid))
    print("RESULT:", "PASS" if not failures else "FAIL")
    for f in failures: print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
