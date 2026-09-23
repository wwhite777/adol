import json, sys
sys.path.insert(0, "src")
from kyra import judge as J
from kyra.schema import load_items
from kyra.providers import get_provider
which = sys.argv[1]
items = load_items("research/items/items_phaseA_v1.jsonl"); ctrl = {it.item_id for it in items if it.risk_group == "CTRL"}
convs = J.read_conversations("result/raw/phaseA_T1/Qwen-Qwen2.5-14B-Instruct/main/20260922T1238Z-a7a9d1")
manual = J.load_manual_text(); tpl = J.load_prompt_template(); anchors = J.load_anchors("research/judge_anchors_v1.json")
paths = {"J1": "/home/wjeong/.cache/huggingface/hub/models--meta-llama--Llama-3.1-8B-Instruct/snapshots/0e9e39f249a16976918f6564b8830bc894c89659",
         "J2": "/home/wjeong/adol/models/hf/hub/models--Intel--Mistral-Small-3.2-24B-Instruct-2506-int4-AutoRound/snapshots/21907bf9a442ec05c91e059ef17b08a8b44983f5"}
want_control = which == "J2"
sel = []
for c in convs:
    if (c["item_id"] in ctrl) != want_control: continue
    views = J.make_views(c["turns"], "prefix")
    sel.append((c["item_id"], 1, views[0][1]))
    if len(sel) == 3 and len(views) > 1:
        sel.append((c["item_id"], 2, views[1][1]))
    if len(sel) >= 4: break
msgs0 = J.build_judge_prompt(sel[0][2], manual, anchors, tpl, is_control=want_control)
sysmsg = msgs0[0]["content"]; i = sysmsg.find("## 7."); print("=== RENDERED OUTPUT-FORMAT SECTION (control=%s) ===" % want_control); print(sysmsg[i:i + 1400]); print("=== prompt chars:", sum(len(m["content"]) for m in msgs0), "===")
prov = get_provider("vllm", model_path=paths[which], temperature=0.0, seed=20260916, max_new_tokens=700, gpu_memory_utilization=0.85)
for item, d, view in sel:
    raw = prov.generate(J.build_judge_prompt(view, manual, anchors, tpl, is_control=want_control))
    print("\n===== %s item=%s depth=%d control=%s raw_chars=%d =====" % (which, item, d, want_control, len(raw))); print(raw[:1400])
