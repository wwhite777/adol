"""Fig. 1 of the JKIICE manuscript: study-design overview (design counts only, no outcomes).
Counts are read from research/items/items_phaseA_v1.jsonl, not typed by hand."""
import json, collections, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = pathlib.Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in open(ROOT / "research/items/items_phaseA_v1.jsonl", encoding="utf-8")]
risk = [r for r in rows if r["risk_group"] != "CTRL"]
ctrl = [r for r in rows if r["risk_group"] == "CTRL"]
n_single_loc = sum(1 for r in risk if r["turn_type"] == "single")
n_multi_loc = sum(1 for r in risk if r["turn_type"] == "multi" and r["localization"] == "localized")
n_literal = sum(1 for r in risk if r["localization"] == "literal")
n3 = sum(1 for r in risk if r["localization"] == "localized" and len(r["turns"]) == 3)
n6 = sum(1 for r in risk if r["localization"] == "localized" and len(r["turns"]) == 6)
n_lex = sum(1 for r in ctrl if r["turn_type"] == "single")
n_twin = sum(1 for r in ctrl if r["turn_type"] == "multi")
views = sum(len(r["turns"]) for r in rows)
assert len(rows) == 156 and views == 564, (len(rows), views)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
fig, ax = plt.subplots(figsize=(7.0, 5.2), dpi=300)
ax.set_xlim(0, 100); ax.set_ylim(0, 84); ax.axis("off")
C = ["#2F6DB5", "#C0692B", "#3B8E5A", "#7A4FA3"]

def panel(x, y0, w, color, tag, title, lines):
    ax.add_patch(FancyBboxPatch((x, y0), w, 36, boxstyle="round,pad=0.4,rounding_size=1.5",
                                fc="white", ec=color, lw=1.4))
    ax.text(x + 1.5, y0 + 34.0, f"({tag}) {title}", color=color, weight="bold", fontsize=9, va="top")
    y = y0 + 29.5
    for ln in lines:
        bold = ln.startswith("*")
        ax.text(x + 2.0, y, ln.lstrip("*"), fontsize=7.8, va="top", weight="bold" if bold else "normal")
        y -= 3.1

def arrow(p0, p1):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=14, lw=1.8, color="#444444"))

panel(1, 44, 46, C[0], "a", "Item bank (156)", [
    f"*Risk, localized: {n_single_loc + n_multi_loc}",
    "  6 groups R1-R6",
    f"  single-turn {n_single_loc}",
    f"  multi-turn {n_multi_loc} (3-turn {n3}, 6-turn {n6})",
    f"*Literal twins: {n_literal}",
    "  one per multi-turn risk item",
    f"*Controls: {n_lex + n_twin}",
    f"  lexical contrasts {n_lex} (1 turn)",
    f"  benign twins {n_twin} (6 turns)",
])
arrow((47.8, 62), (52.2, 62))
panel(53, 44, 46, C[1], "b", "Generation", [
    "*5 open-weight models",
    "  Qwen2.5-14B, EXAONE-4.0-32B,",
    "  Kanana-1.5-8B, Gemma-3-27B,",
    "  HyperCLOVAX-SEED-Think-14B",
    "*main: 156 items, T = 0",
    "*repeats: 31-item subset,",
    "  T = 0.7 x 3",
    "*20 run directories",
    f"  {views} + 3 x 116 prefix views/model",
])
arrow((76, 43.4), (76, 41.6))
panel(53, 5, 46, C[2], "c", "Judging", [
    "*prefix view d = 1..T",
    "  (judge sees turns 1..d only)",
    "*3 judges, disjoint families",
    "  J1 Llama-3.1-8B",
    "  J2 Mistral-Small-3.2-24B",
    "  J3 Phi-4",
    "*sequential decoding, T = 0",
    "*panel = median of 3",
    "  RB-6D D1-D6, CF flag, A1-A4",
])
arrow((52.2, 23), (47.8, 23))
panel(1, 5, 46, C[3], "d", "Frozen claims", [
    "*N1 escalation",
    "  OR(6 vs 1 turn) >= 1.6",
    "  benign twins as control",
    "*N2 localization",
    "  |delta| >= 0.03 (TOST)",
    "*N3 judge reliability",
    "  AC2 >= 0.70, flag >= 0.80",
    "*G6 verdict (script)",
])
pass
out = pathlib.Path(__file__).with_name("fig1_design.png")
fig.savefig(out, bbox_inches="tight", facecolor="white")
print("wrote", out, "items", len(rows), "views", views, n_single_loc, n_multi_loc, n3, n6, n_literal, n_lex, n_twin)
