#!/usr/bin/env bash
# Phase-A analysis runner (run ONLY after all 20 run dirs are scored and verified — interim-look rule).
# Runs the five analysis CLIs and the G6 preregistration judge over every run dir that holds a panel.jsonl,
# writing clock-named outputs under result/analysis/phaseA_T1/<STAMP>/ with a log per step. Own command, background.
#   bin/analyze_phaseA.sh [n3-revisions]   (default 1 = the single judge-prompt revision consumed on 2026-09-23)
set -u
REV="${1:-1}"
cd /home/wjeong/adol || exit 9
export PYTHONPATH=src
PY=~/envs/jeongwoncheol_adol/bin/python
STAMP=$(date -u +%Y%m%dT%H%MZ)
OUT="result/analysis/phaseA_T1/${STAMP}"; mkdir -p "$OUT"
FM="result/raw/phaseA_T1/family_map_phaseA_T1.json"
ITEMS="research/items/items_phaseA_v1.jsonl"
mapfile -t PANELS < <(ls result/raw/phaseA_T1/*/*/*/panel.jsonl 2>/dev/null)
RUNS=(); for p in "${PANELS[@]}"; do RUNS+=("$(dirname "$p")"); done
echo "panels: ${#PANELS[@]} (expect 20) | out: $OUT" | tee "$OUT/README.txt"
[ "${#PANELS[@]}" -eq 20 ] || { echo "REFUSING: ${#PANELS[@]} panels, expected 20 (all five models × 4 runs)" | tee -a "$OUT/README.txt"; exit 3; }
for d in "${RUNS[@]}"; do [ -f "$d/MARKER" ] || { echo "REFUSING: $d has a panel but no MARKER" | tee -a "$OUT/README.txt"; exit 3; }; done
JUDGES=(); for d in "${RUNS[@]}"; do for j in J1 J2 J3; do JUDGES+=("$d/judge_$j.jsonl"); done; done
$PY -m kyra.analysis.n1_escalation --items "$ITEMS" --runs "${RUNS[@]}" --panels "${PANELS[@]}" --family-map "$FM" --out "$OUT/n1.json" > "$OUT/n1.log" 2>&1; echo "n1 exit=$?" | tee -a "$OUT/README.txt"
$PY -m kyra.analysis.n2_localization --items "$ITEMS" --runs "${RUNS[@]}" --panels "${PANELS[@]}" --family-map "$FM" --out "$OUT/n2.json" > "$OUT/n2.log" 2>&1; echo "n2 exit=$?" | tee -a "$OUT/README.txt"
$PY -m kyra.analysis.n3_reliability --judges "${JUDGES[@]}" --runs "${RUNS[@]}" --family-map "$FM" --out "$OUT/n3.json" > "$OUT/n3.log" 2>&1; echo "n3 exit=$?" | tee -a "$OUT/README.txt"
$PY -m kyra.analysis.transitions --items "$ITEMS" --runs "${RUNS[@]}" --panels "${PANELS[@]}" --family-map "$FM" --out "$OUT/transitions.json" > "$OUT/transitions.log" 2>&1; echo "transitions exit=$?" | tee -a "$OUT/README.txt"
$PY -m kyra.analysis.pareto --items "$ITEMS" --runs "${RUNS[@]}" --panels "${PANELS[@]}" --family-map "$FM" --out "$OUT/pareto.json" > "$OUT/pareto.log" 2>&1; echo "pareto exit=$?" | tee -a "$OUT/README.txt"
$PY -m kyra.g6 --prereg PREREGISTERED_kyra_v2.yaml --sha PREREGISTERED_kyra_v2.yaml.sha256 --n1 "$OUT/n1.json" --n2 "$OUT/n2.json" --n3 "$OUT/n3.json" --n3-revisions "$REV" --out "$OUT/g6_verdict.json" > "$OUT/g6.log" 2>&1; echo "g6 exit=$?" | tee -a "$OUT/README.txt"
echo "done $(date -u +%Y%m%dT%H%MZ)" | tee -a "$OUT/README.txt"
