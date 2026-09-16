#!/usr/bin/env python3
"""Reproduce plan v2 section 6 H1 power simulation (adol/KYRA-Bench, 2026-09-16).

Spec as stated in the plan: scenario random intercept SD 0.8, model SD 0.6,
scenario x model SD 0.5, 5 models, 1-turn vs 6-turn fatal-failure probability,
test = scenario cluster bootstrap 95% CI (two-sided alpha .05), 600 replications.

Reading pinned HERE (the plan does not fully specify it; disclosed in output):
- beta0 = logit(p1); turn effect delta = logit(p6) - logit(p1) applied on the
  logit scale, so realized MARGINAL rates differ from p1/p6 once random effects
  are added (realized rates are reported).
- One Bernoulli draw per scenario x model x turn-depth (paired within scenario).
- Statistic: mean over scenarios of d_s = mean_j y6_sj - mean_j y1_sj;
  percentile bootstrap over scenarios, B=500; significant if CI excludes 0.
Plan-reported values for comparison: (48,.12,.28)=0.98 (48,.12,.22)=0.85
(72,.12,.22)=0.95 (48,.20,.35)=0.91 (48,.12,.18)=0.47 (72,.12,.18)=0.61
"""
import csv, os, time
import numpy as np

RNG = np.random.default_rng(20260916)
N_MODELS, N_REP, N_BOOT = 5, 600, 500
SD_S, SD_M, SD_SM = 0.8, 0.6, 0.5
CONFIGS = [(48, .12, .28, .98), (48, .12, .22, .85), (72, .12, .22, .95),
           (48, .20, .35, .91), (48, .12, .18, .47), (72, .12, .18, .61)]

def logit(p): return np.log(p / (1 - p))
def sigmoid(x): return 1 / (1 + np.exp(-x))

rows = []
for S, p1, p6, plan_power in CONFIGS:
    b0, d = logit(p1), logit(p6) - logit(p1)
    sig = 0
    r1s, r6s = [], []
    for _ in range(N_REP):
        u = RNG.normal(0, SD_S, (S, 1))
        m = RNG.normal(0, SD_M, (1, N_MODELS))
        w = RNG.normal(0, SD_SM, (S, N_MODELS))
        eta = b0 + u + m + w
        y1 = RNG.random((S, N_MODELS)) < sigmoid(eta)
        y6 = RNG.random((S, N_MODELS)) < sigmoid(eta + d)
        r1s.append(y1.mean()); r6s.append(y6.mean())
        ds = y6.mean(axis=1) - y1.mean(axis=1)          # per-scenario paired diff
        idx = RNG.integers(0, S, (N_BOOT, S))            # cluster bootstrap
        boots = ds[idx].mean(axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        sig += (lo > 0) or (hi < 0)
    power = sig / N_REP
    rows.append({"n_scenarios": S, "p1_design": p1, "p6_design": p6,
                 "realized_rate_1turn": round(float(np.mean(r1s)), 4),
                 "realized_rate_6turn": round(float(np.mean(r6s)), 4),
                 "power_reproduced": round(power, 3), "power_plan": plan_power,
                 "diff": round(power - plan_power, 3)})
    print(rows[-1])

out_dir = "result/power_sim"
os.makedirs(out_dir, exist_ok=True)
stamp = time.strftime("%Y%m%dT%H%MZ", time.gmtime())
path = f"{out_dir}/power_sim_reproduction_{stamp}.csv"
with open(path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print(f"wrote {path} | reps={N_REP} boot={N_BOOT} seed=20260916")
