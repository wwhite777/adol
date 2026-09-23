#!/usr/bin/env bash
# Pinned phase-A scoring launcher (DECISION_LOG 2026-09-23 ~05:15Z): batched judges (batch_size in judges.json),
# vLLM batch-invariant mode, FLASH_ATTN attention backend. Run from /home/wjeong/adol as its OWN command
# (background), one log per invocation, marker on exit.
#   bin/score_phaseA.sh <models_runN.json> <run-glob-or-dirs> <gpu> <label>
# e.g. bin/score_phaseA.sh research/models_run1.json 'result/raw/phaseA_T1/Qwen-Qwen2.5-14B-Instruct/*/*' 2 qwen14b
set -u
MODELS="$1"; RUNS="$2"; GPU="$3"; LABEL="$4"
cd /home/wjeong/adol || exit 9
export VLLM_BATCH_INVARIANT=1
export KYRA_VLLM_ENGINE_KWARGS='{"attention_backend": "FLASH_ATTN"}'
export HF_HUB_OFFLINE=1
export PYTHONPATH=src
STAMP=$(date -u +%Y%m%dT%H%MZ)
LOG="test/logs/score_phaseA_T1_${LABEL}_${STAMP}.log"
~/envs/jeongwoncheol_adol/bin/python -m kyra.campaign score \
  --items research/items/items_phaseA_v1.jsonl \
  --models "$MODELS" \
  --judges research/judges_phaseA_v1.json \
  --cohort phaseA_T1 \
  --runs $RUNS \
  --anchors research/judge_anchors_v1.json \
  --gpu "$GPU" > "$LOG" 2>&1
EXIT=$?
echo "exit=$EXIT stamp=${STAMP} log=${LOG}" > "result/raw/phaseA_T1_score_${LABEL}.DONE"
exit $EXIT
