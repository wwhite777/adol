#!/bin/bash
# Check (2) + (4) of the analysis card: run every CLI on its fixture and on an
# empty input, recording the exact command and the shell's exit code.
# Usage: bash test/logs/run_analysis_clis.sh <UTC-stamp>
set -u
cd /home/wjeong/adol || exit 9
PY=$HOME/envs/jeongwoncheol_adol/bin/python
STAMP="$1"
OUT="test/logs/cli_outputs_${STAMP}"
mkdir -p "$OUT"
export PYTHONPATH=src

run() {   # run <label> <args...>
  label="$1"; shift
  echo "### $label"
  echo "\$ PYTHONPATH=src $PY $*"
  "$PY" "$@"
  echo "exit=$?"
  echo
}

F=test/fixtures/analysis

run n1_effect  -m kyra.analysis.n1_escalation  --fixture $F/n1_effect.csv  --bootstrap 200 --out "$OUT/n1_effect.json"
run n1_null    -m kyra.analysis.n1_escalation  --fixture $F/n1_null.csv    --bootstrap 200 --out "$OUT/n1_null.json"
run n1_interaction -m kyra.analysis.n1_escalation --fixture $F/n1_interaction.csv --bootstrap 200 --out "$OUT/n1_interaction.json"
run n2_effect  -m kyra.analysis.n2_localization --fixture $F/n2_effect.csv --bootstrap 200 --out "$OUT/n2_effect.json"
run n2_null    -m kyra.analysis.n2_localization --fixture $F/n2_null.csv   --bootstrap 200 --out "$OUT/n2_null.json"
run n3_sim     -m kyra.analysis.n3_reliability  --fixture $F/n3_sim.csv    --bootstrap 200 --out "$OUT/n3_sim.json"
run n3_hand    -m kyra.analysis.n3_reliability  --fixture $F/n3_hand.csv   --bootstrap 200 --out "$OUT/n3_hand.json"
run transitions -m kyra.analysis.transitions    --fixture $F/transitions_small.csv --out "$OUT/transitions.json"
run pareto     -m kyra.analysis.pareto          --fixture $F/pareto_small.csv --bootstrap 200 --out "$OUT/pareto.json"
run pareto_proxy -m kyra.analysis.pareto        --fixture $F/pareto_small.csv --bootstrap 200 --proxy-d3d4 --out "$OUT/pareto_proxy_d3d4.json"
run prefix_run_transitions -m kyra.analysis.transitions --items $F/prefix_run/items.jsonl --runs $F/prefix_run/run --panels $F/prefix_run/run/panel.jsonl --out "$OUT/transitions_prefix_run.json"

echo "=== empty-input checks (every one must exit non-zero) ==="
run empty_n1   -m kyra.analysis.n1_escalation   --fixture $F/empty_tidy.csv --out "$OUT/empty_n1.json"
run empty_n2   -m kyra.analysis.n2_localization --fixture $F/empty_tidy.csv --out "$OUT/empty_n2.json"
run empty_n3   -m kyra.analysis.n3_reliability  --fixture $F/empty_judges.csv --out "$OUT/empty_n3.json"
run empty_tr   -m kyra.analysis.transitions     --fixture $F/empty_tidy.csv --out "$OUT/empty_transitions.json"
run empty_pa   -m kyra.analysis.pareto          --fixture $F/empty_tidy.csv --out "$OUT/empty_pareto.json"

echo "=== files written ==="
ls -la "$OUT"
