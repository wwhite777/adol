#!/usr/bin/env bash
# Pinned phase-A scoring launcher (DECISION_LOG 2026-09-23 ~09:35Z): SEQUENTIAL judging (batch_size 1 in judges.json),
# vLLM batch-invariant mode, FLASH_ATTN attention backend, prefix caching OFF, max_model_len 16384.
# Run from /home/wjeong/adol as its OWN command (background), one log per invocation, marker on exit.
#   bin/score_phaseA.sh <models_runN.json> <run-glob-or-dirs> <gpu> <label> [src-root] [extra-args e.g. --resume]
# e.g. bin/score_phaseA.sh research/models_run1.json 'result/raw/phaseA_T1/Qwen-Qwen2.5-14B-Instruct/*/*' 1 qwen14b
# [src-root]: an optional frozen copy of src/ (git archive) so that code edits during a multi-hour run cannot
# reach its judge subprocesses; default = the working tree's src.
set -u
MODELS="$1"; RUNS="$2"; GPU="$3"; LABEL="$4"; SRC="${5:-src}"; EXTRA="${6:-}"   # EXTRA: e.g. --resume (reuse provenance-identical judge outputs)
cd /home/wjeong/adol || exit 9
export VLLM_BATCH_INVARIANT=1
export KYRA_VLLM_ENGINE_KWARGS='{"attention_backend": "FLASH_ATTN", "enable_prefix_caching": false, "max_model_len": 16384}'
export HF_HUB_OFFLINE=1
export PYTHONPATH="$SRC"
STAMP=$(date -u +%Y%m%dT%H%MZ)
LOG="test/logs/score_phaseA_T1_${LABEL}_${STAMP}.log"
~/envs/jeongwoncheol_adol/bin/python -m kyra.campaign score \
  --items research/items/items_phaseA_v1.jsonl \
  --models "$MODELS" \
  --judges research/judges_phaseA_v1.json \
  --cohort phaseA_T1 \
  --runs $RUNS \
  --anchors research/judge_anchors_v1.json \
  --gpu "$GPU" $EXTRA > "$LOG" 2>&1
EXIT=$?
echo "exit=$EXIT stamp=${STAMP} log=${LOG}" > "result/raw/phaseA_T1_score_${LABEL}.DONE"
exit $EXIT
