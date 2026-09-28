"""Fig. 2 of the JKIICE manuscript: critical-failure rate by prefix depth (1, 3, 6),
localized six-turn risk scripts vs their item-paired benign twins, per model and pooled.

Same inputs as kyra.analysis.n1_escalation (the loader's tidy table), so the plotted
rates are the ones N1 models. Pooled CIs: scenario-cluster bootstrap (B, seed below).
Guard: real data only when all 20 runs are scored, with exactly the 5 MAIN panels as input;
--fixture input is stamped SYNTHETIC on the figure.
  python fig2_depth.py --items I --runs R... --panels P... --family-map F --out fig2.json --png fig2.png
  python fig2_depth.py --fixture test.csv --out o.json --png o.png"""
import sys, json, argparse, pathlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from kyra.analysis import loader

DEPTHS = (1, 3, 6)
B, SEED = 2000, 20260924

def select(df, cond):
    d = df[(df["condition"] == cond) & (df["n_turns"] >= 6)]
    if cond == "LOC":
        d = d[d["risk_group"].astype(str) != "CTRL"]
    return d.copy()

def rates(d):
    out = {}
    for k in DEPTHS:
        col = pd.to_numeric(d["crit_by_depth_%d" % k], errors="coerce").dropna()
        out[k] = {"n": int(len(col)), "events": int(col.sum()), "rate": float(col.mean()) if len(col) else None}
    return out

def cluster_ci(d, rng):
    scen = d["base_item"].unique()
    groups = {s: g for s, g in d.groupby("base_item")}
    boots = {k: [] for k in DEPTHS}
    for _ in range(B):
        pick = rng.choice(scen, size=len(scen), replace=True)
        s = pd.concat([groups[p] for p in pick])
        for k in DEPTHS:
            col = pd.to_numeric(s["crit_by_depth_%d" % k], errors="coerce").dropna()
            boots[k].append(col.mean() if len(col) else np.nan)
    return {k: [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for k, v in boots.items()}

def main(argv=None):
    p = argparse.ArgumentParser()
    loader.add_table_args(p)
    p.add_argument("--png", required=True)
    a = p.parse_args(argv)
    synthetic = bool(a.fixture)
    if not synthetic:
        import glob
        root = pathlib.Path(__file__).resolve().parents[2]
        n_all = len(glob.glob(str(root / "result/raw/phaseA_T1/*/*/*/panel.jsonl")))
        if n_all != 20 or len(a.panels or []) != 5 or not all("/main/" in x for x in a.panels):
            sys.stderr.write("REFUSING: need all 20 scored panels on disk (found %d) and exactly the 5 MAIN panels as input "
                             "(got %d) - interim-look rule and the main-run pin (DECISION_LOG 2026-09-26)\n" % (n_all, len(a.panels or [])))
            return 3
    df = loader.resolve_table(a)
    rng = np.random.default_rng(SEED)
    res = {"synthetic": synthetic, "B": B, "seed": SEED, "depths": list(DEPTHS), "arms": {}}
    for cond, label in (("LOC", "risk"), ("BEN", "benign")):
        d = select(df, cond)
        loader.require_nonempty(d, cond + " six-turn conversations")
        arm = {"pooled": rates(d), "pooled_ci95": cluster_ci(d, rng),
               "n_scenarios": int(d["base_item"].nunique()), "per_model": {}}
        for m, g in d.groupby("model_id"):
            arm["per_model"][str(m)] = rates(g)
        res["arms"][label] = arm
    loader.write_json(res, a.out)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8), dpi=300, sharey=True)
    ymax = 0
    for ax, (label, title) in zip(axes, (("risk", "(a) Risk scripts (localized, 6-turn)"),
                                         ("benign", "(b) Item-paired benign twins"))):
        arm = res["arms"][label]
        for m, r in sorted(arm["per_model"].items()):
            ys = [r[k]["rate"] for k in DEPTHS]
            ax.plot(DEPTHS, ys, marker="o", ms=2.5, lw=0.8, alpha=0.7, label=m.split("/")[-1])
            ymax = max([ymax] + [y for y in ys if y is not None])
        pooled = [arm["pooled"][k]["rate"] for k in DEPTHS]
        lo = [arm["pooled_ci95"][k][0] for k in DEPTHS]; hi = [arm["pooled_ci95"][k][1] for k in DEPTHS]
        ax.fill_between(DEPTHS, lo, hi, color="black", alpha=0.12, lw=0)
        ax.plot(DEPTHS, pooled, color="black", lw=2.0, marker="s", ms=4, label="pooled (95% cluster CI)")
        ymax = max(ymax, max(hi))
        n = arm["pooled"][1]["n"]
        ax.set_title(title + f"\nn = {n} conversations, {arm['n_scenarios']} scenarios", fontsize=8)
        ax.set_xticks(DEPTHS); ax.set_xlabel("Prefix depth (turns)")
        ax.grid(axis="y", lw=0.3, alpha=0.5)
    axes[0].set_ylabel("Critical-failure rate")
    axes[0].set_ylim(0, min(1.0, ymax * 1.15 + 0.02))
    axes[1].legend(fontsize=6, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC TEST DATA", ha="center", va="center", fontsize=28, color="red", alpha=0.25, rotation=20)
    fig.savefig(a.png, bbox_inches="tight", facecolor="white")
    print("out=%s png=%s synthetic=%s" % (a.out, a.png, synthetic))
    return 0

if __name__ == "__main__":
    sys.exit(main())
