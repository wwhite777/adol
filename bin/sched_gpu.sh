#!/usr/bin/env bash
# Phase-A scoring scheduler for ONE GPU - run DETACHED (setsid nohup ... &) so it survives the conductor session.
#   bin/sched_gpu.sh <gpu> <wait_pid|0> <label>:<models.json>:<runs-glob-or-dirs> [<label>:<models.json>:<runs> ...]
# Waits until <wait_pid> (the launcher of a pass already running on this GPU) has exited, then for each pass in
# order: skips it when complete (4 MARKER dirs, each with judge_J1/J2/J3.jsonl + .meta.json + panel.jsonl);
# otherwise waits until the GPU is free (< 4096 MiB) and runs the pinned launcher from the frozen snapshot with
# --resume (finished judges are reused only when their provenance matches the plan; nothing is overwritten).
# Never kills anything. One clock-named log per scheduler under snapshots/sched/. Written 2026-09-24 (OPS-7).
set -u
GPU="$1"; WAITPID="$2"; shift 2
ROOT=/home/wjeong/adol
SNAP=$ROOT/snapshots/phaseA_scoring_d6e7507
mkdir -p "$ROOT/snapshots/sched"
LOG="$ROOT/snapshots/sched/sched_gpu${GPU}_$(date -u +%Y%m%dT%H%MZ).log"
cd "$ROOT" || exit 9
log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$LOG"; }
complete() {  # $1 = glob or space-separated run dirs; true when exactly 4 marked dirs exist and all are fully scored
  local n=0 ok=0 d
  for d in $1; do
    [ -f "$d/MARKER" ] || continue
    n=$((n + 1))
    [ -s "$d/judge_J1.jsonl" ] && [ -s "$d/judge_J1.meta.json" ] && [ -s "$d/judge_J2.jsonl" ] && [ -s "$d/judge_J2.meta.json" ] \
      && [ -s "$d/judge_J3.jsonl" ] && [ -s "$d/judge_J3.meta.json" ] && [ -s "$d/panel.jsonl" ] && ok=$((ok + 1))
  done
  [ "$n" -eq 4 ] && [ "$ok" -eq 4 ]
}
gpu_free() { [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i "$GPU")" -lt 4096 ]; }
log "start gpu=$GPU wait_pid=$WAITPID snapshot=$SNAP passes: $*"
if ! { [ -x "$SNAP/bin/score_phaseA.sh" ] && [ -d "$SNAP/src/kyra" ] && [ -d "$SNAP/manual" ]; }; then
  log "ABORT: snapshot incomplete at $SNAP"; exit 8
fi
if [ "$WAITPID" != "0" ]; then
  while kill -0 "$WAITPID" 2>/dev/null; do sleep 60; done
  log "launcher pid $WAITPID has exited"
fi
for spec in "$@"; do
  label="${spec%%:*}"; rest="${spec#*:}"; models="${rest%%:*}"; runs="${rest#*:}"
  if complete "$runs"; then log "$label: complete - skipped"; continue; fi
  if [ "${SCHED_DRYRUN:-0}" = "1" ]; then log "$label: DRYRUN - would launch (models=$models runs=$runs)"; continue; fi
  until gpu_free; do sleep 30; done
  log "$label: gpu $GPU free - launching (models=$models runs=$runs)"
  bash "$SNAP/bin/score_phaseA.sh" "$models" "$runs" "$GPU" "$label" "$SNAP/src" --resume < /dev/null
  rc=$?
  log "$label: launcher exit=$rc marker='$(cat "result/raw/phaseA_T1_score_${label}.DONE" 2>/dev/null)'"
  sleep 30
done
log "end"
