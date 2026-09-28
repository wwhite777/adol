"""Fig. 3 of the JKIICE manuscript: inter-judge agreement per RB-6D dimension (Gwet AC2 with
bootstrap 95% CI, frozen bar 0.70) and critical-failure flag agreement (bar 0.80), read from the
n3.json written by kyra.analysis.n3_reliability. Points are estimates, not significance marks.
  python fig3_reliability.py <n3.json> <out.png> [--synthetic]"""
import sys, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NAMES = {"D1": "D1 Risk recognition", "D2": "D2 Boundary setting", "D3": "D3 Safe refusal",
         "D4": "D4 Alternatives", "D5": "D5 Resource linkage", "D6": "D6 Transparency"}

def main(argv):
    src, out = argv[0], argv[1]
    synthetic = "--synthetic" in argv
    n3 = json.load(open(src, encoding="utf-8"))
    dims = [d for d in NAMES if d in n3["per_dimension"]]
    if len(dims) != 6:
        sys.stderr.write("REFUSING: n3.json has %d of 6 dimensions\n" % len(dims)); return 3
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig, ax = plt.subplots(figsize=(3.4, 2.9), dpi=300)
    ys = list(range(len(dims) + 1))[::-1]
    for y, d in zip(ys, dims):
        r = n3["per_dimension"][d]
        ci = r.get("ci95")
        if ci:
            ax.plot(ci, [y, y], color="#2F6DB5", lw=1.4)
        ax.plot(r["ac2"], y, "o", color="#2F6DB5", ms=4)
    fa = n3["flag_agreement"]
    ax.plot(fa, ys[-1], "D", color="#C0692B", ms=4)
    ax.plot([0.70, 0.70], [ys[-1] + 0.55, ys[0] + 0.5], color="#2F6DB5", ls="--", lw=0.8)
    ax.plot([0.80, 0.80], [ys[-1] - 0.45, ys[-1] + 0.45], color="#C0692B", ls=":", lw=1.0)
    ax.set_yticks(ys); ax.set_yticklabels([NAMES[d] for d in dims] + ["Critical-failure flag\n(pairwise agreement)"], fontsize=7)
    ax.set_xlim(min(0.0, min(n3["per_dimension"][d]["ac2"] for d in dims) - 0.05), 1.0)
    ax.set_xlabel("Gwet AC2 (dimensions) / agreement (flag)")
    ax.text(0.70, ys[0] + 0.6, "bar 0.70", color="#2F6DB5", fontsize=6, ha="center")
    ax.text(0.80, ys[-1] - 0.75, "bar 0.80", color="#C0692B", fontsize=6, ha="center")
    ax.set_ylim(-1.2, len(dims) + 0.9)
    ax.grid(axis="x", lw=0.3, alpha=0.5)
    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC", ha="center", va="center", fontsize=26, color="red", alpha=0.25, rotation=20)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    print("png=%s dims=%d flag=%s synthetic=%s" % (out, len(dims), fa, synthetic))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
