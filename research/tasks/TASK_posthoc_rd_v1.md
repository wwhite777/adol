# Task card — KYRA phase A: risk-difference contrasts and sparse-cell sensitivity for JKIICE v7 (conductor, 2026-10-01)

Job: one new POST HOC analysis module that re-expresses the depth x risk contrast on the risk-difference scale, gives an exact or Firth
interval for the benign-twin depth effect, and reports the scenario random-intercept variance, for every CF labeling already in the
paper (fixed rules S0; S1, S2, S3 from result/analysis/phaseA_T1/posthoc_20260927T2328Z; the output-repair variants R1 and R2 reported in
manuscript v6, Table 7 rows "R1 output budget repair" and "R2 budget + JSON-schema decoding" — find their per-view records via git commit
aedcb36 and manuscript/jkiice_v1/content_v6.py; if R1/R2 per-view data are not reachable, say so and do S0-S3 only).
Why: an external review (adol/review/JMIRMH_review_2026-10-01.md, section 3.2 R1) showed that the odds-ratio intervals for the benign arm
(1/120 vs 20/120 under S0; 0 events at depth 1 under S1-S3) and the interaction ORs 2.84-3.69 (Holm p 0.018-0.049) rest on 0-1 event cells,
so the variational-Bayes + scenario-bootstrap percentile intervals report the prior more than the data. The frozen confirmatory results
(result/analysis/phaseA_T1/20260926T0213Z) never change; everything here is post hoc and labelled so.
1. src/kyra/analysis/posthoc_rd_v1.py (read src/kyra/analysis/posthoc_v1.py, n1_escalation.py and loader.py first; reuse their loaders and
   the same scenario clusters):
   (a) for each labeling: CF-flag proportions at depth 1 and depth 6 for risk scripts and benign twins (k/n), the depth risk differences
       RD_risk and RD_benign, and the difference in differences DiD = RD_risk - RD_benign, each with a scenario-cluster bootstrap 95%
       percentile interval (B = 2000, the paper's seed convention, resampling scenarios = base items with their localized/literal/twin
       variants together, exactly as the paper's bootstrap);
   (b) for the benign arm, the depth odds ratio with an exact conditional interval (scipy.stats.contingency.odds_ratio kind="conditional")
       and a Firth-penalized logistic fit (implement the Jeffreys-penalized likelihood with numpy if no library is present) on the crude
       2 x 2 counts; also the crude Woolf interval with the Haldane correction for comparison;
   (c) the estimated scenario random-intercept standard deviation of the frozen VB mixed model for risk and benign (read it from the frozen
       fit if stored; otherwise refit with the frozen code and seed and report it, noting the VB initialisation caveat already in the paper).
2. Output: result/analysis/phaseA_T1/posthoc_rd_<UTC>/ with posthoc_rd.json (every number with its k/n and method), a CSV table per
   section, and a log; code sha256 and input hashes recorded.
3. Checks (one log each, test/logs/posthoc_rd_*_<UTC>.log): reproduce the S0-S3 k/n counts of posthoc_20260927T2328Z exactly before
   computing anything new (exit 2 on mismatch); unit tests for the RD/DiD bootstrap on a tiny fixture with a known answer and for the
   Firth fit on a 2 x 2 with a zero cell (finite estimate expected).
Interpreter: /home/wjeong/envs/jeongwoncheol_adol/bin/python (numpy 2.2.6, statsmodels 0.15.0; check scipy), PYTHONPATH=src, from
/home/wjeong/adol. Install nothing.
Guardrails: write only src/kyra/analysis/posthoc_rd_v1.py, its test file under test/, result/analysis/phaseA_T1/posthoc_rd_*/**, and
test/logs/posthoc_rd_*; never modify frozen results, other analysis code, the manuscript files or anything in /home/wjeong/crisisref;
never touch GPU 3 or any GPU; no network; no git commands that change the repository.
Receipt (<= 30 lines): the reproduction check; for each labeling the risk and benign k/n at depth 1 and 6, RD_risk, RD_benign and DiD with
intervals; the benign exact and Firth ORs; the random-intercept SDs; files with sha256; anything not done.
