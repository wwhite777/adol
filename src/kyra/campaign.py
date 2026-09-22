"""Campaign orchestrator: run the phase-A item set against a list of models.

One model at a time, guarded. For each model, in the order given by models.json:

  1. pre-flight   disk free >= 20 GB at the output root; a GPU chosen from
                  0/1/2 (first with < 4 GiB used) - GPU 3 is another user's job
                  and is never selected; the frozen protocol hash verified via
                  gates.verify_freeze (skipped only for --class smoke).
  2. main run     the full item set at temperature 0, one run directory.
  3. repeats      the 20 % stratified repeat subset (strata = source group x
                  turn_type, i.e. risk_group x turn_type; seed 20260922), three
                  times at temperature 0.7, one run directory each, condition
                  tag repeat_1 / repeat_2 / repeat_3.
  Every run must leave a MARKER before the next one starts; each run appends one
  row to EXPERIMENTS.csv. On any failed run the campaign stops and reports - it
  never continues silently.

CLI (from the repo root) - generation:
    PYTHONPATH=src python -m kyra.campaign \
        --items research/items/items_phaseA_v1.jsonl \
        --models models.json --cohort phaseA_T1 \
        --class confirmatory|smoke [--dry-run] \
        [--out-root result/raw] [--experiments-csv research/EXPERIMENTS.csv] \
        [--prereg PREREGISTERED_kyra_v2.yaml] [--sha PREREGISTERED_kyra_v2.yaml.sha256]

Exit codes: 0 ok (or a dry-run whose pre-flight passed) | 2 bad input (missing
or malformed items/models/CSV) | 6 freeze mismatch | 7 pre-flight refusal |
8 a run failed (no MARKER, validation failure or provider error).

models.json: a list (or {"models": [...]}) of
    {"model_id": "LGAI-EXAONE/EXAONE-4.0-1.2B",   # or "model_path"
     "model_path": "/local/or/cached/path",        # optional, defaults to model_id
     "family": "lg",
     "provider": "vllm",                           # "mock" only for --class smoke
     "gpu_memory_utilization": 0.85,               # optional, provider default 0.85
     "notes": "free text"}
No model downloading happens here: the path must already be local or cached.

CLI - scoring (a sub-command that cannot forget the item file):
    PYTHONPATH=src python -m kyra.campaign score \
        --items research/items/items_phaseA_v1.jsonl --models models.json \
        --judges judges.json --cohort phaseA_T1 --runs <dirs or globs> \
        [--anchors research/judge_anchors_v1.json] [--dry-run] \
        [--class confirmatory|smoke] [--out-root ...] [--experiments-csv ...]
For every run directory that carries a MARKER: each judge in judges.json is run
as a child process (kyra.judge --views prefix --items <items>, so control ids
come from risk_group CTRL and are never omitted), one judge model loaded at a
time, writing judge_<judge_id>.jsonl into the run dir; an existing judge file is
refused, never overwritten. Then kyra.panel aggregates that run's judge files
with the family map built from models.json + judges.json and --evaluated-family
= the run's model family, writing panel.jsonl. One EXPERIMENTS row per judge run
and per panel (class inherited from the run's EXPERIMENTS row, or --class); the
freeze hash is verified before any confirmatory scoring. Record:
campaign_<cohort>_scoring.json. Any failure stops the batch.

Runs go through runner.execute_run() in-process, with the condition tag (base /
repeat_1..3) and the requested temperature passed as runner parameters, so the
manifest's own `condition` field carries the real tag. The provider is built at
the requested temperature/seed (and the model's gpu_memory_utilization, which
the runner CLI does not expose), and the manifest's sampling fields still record
what the provider reports it actually applied.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from gates.verify_freeze import FreezeMismatch, verify
from kyra import manifest as mf
from kyra import runner as kyra_runner
from kyra.providers import get_provider
from kyra.schema import load_items

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_FREEZE_MISMATCH = 6
EXIT_PREFLIGHT = 7
EXIT_RUN_FAILED = 8

MIN_FREE_GB = 20.0
ALLOWED_GPUS: Tuple[int, ...] = (0, 1, 2)
FORBIDDEN_GPU = 3
GPU_FREE_MAX_USED_MIB = 4096  # "< 4 GB used" counts as free
SAMPLING_SEED = 20260922
REPEAT_FRACTION = 0.20
REPEAT_COUNT = 3
MAIN_TEMPERATURE = 0.0
REPEAT_TEMPERATURE = 0.7
MAIN_CONDITION = "base"  # the frozen condition tag for the deterministic run
DEFAULT_OUT_ROOT = "result/raw"
STRATUM_FIELDS = ("risk_group", "turn_type")  # source group x turn type
EXPERIMENTS_HEADER = (
    "run",
    "class",
    "config",
    "seed",
    "command",
    "raw",
    "log",
    "marker",
    "status",
    "failure",
)
RUN_CLASSES = ("confirmatory", "smoke")


class CampaignError(Exception):
    """A refusal with an exit code; nothing is run after it is raised."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-") or "model"


# --------------------------------------------------------------------------
# models.json
# --------------------------------------------------------------------------
def load_models(path, run_class: str) -> List[Dict[str, Any]]:
    """Read and validate models.json. Any problem is a hard refusal."""
    p = Path(path)
    if not p.is_file():
        raise CampaignError("models file not found: %s" % p, EXIT_BAD_INPUT)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError("models file unreadable: %s (%s)" % (p, exc), EXIT_BAD_INPUT)
    if isinstance(doc, dict):
        doc = doc.get("models")
    if not isinstance(doc, list) or not doc:
        raise CampaignError(
            "models file must hold a non-empty list of model objects: %s" % p,
            EXIT_BAD_INPUT,
        )

    models: List[Dict[str, Any]] = []
    seen = set()
    for index, entry in enumerate(doc):
        where = "%s[%d]" % (p.name, index)
        if not isinstance(entry, dict):
            raise CampaignError("%s is not an object" % where, EXIT_BAD_INPUT)
        model_id = entry.get("model_id") or entry.get("model_path")
        model_path = entry.get("model_path") or entry.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise CampaignError("%s has no model_id/model_path" % where, EXIT_BAD_INPUT)
        family = entry.get("family")
        if not isinstance(family, str) or not family.strip():
            raise CampaignError("%s has no family" % where, EXIT_BAD_INPUT)
        provider = entry.get("provider")
        if provider not in ("vllm", "mock"):
            raise CampaignError(
                "%s has provider %r (expected 'vllm', or 'mock' for smoke runs)"
                % (where, provider),
                EXIT_BAD_INPUT,
            )
        if provider == "mock" and run_class == "confirmatory":
            raise CampaignError(
                "%s uses the mock provider; a mock run is never evidence and is "
                "refused for --class confirmatory" % where,
                EXIT_BAD_INPUT,
            )
        gpu_util = entry.get("gpu_memory_utilization")
        if gpu_util is not None and (
            isinstance(gpu_util, bool) or not isinstance(gpu_util, (int, float))
        ):
            raise CampaignError(
                "%s gpu_memory_utilization must be a number" % where, EXIT_BAD_INPUT
            )
        if model_id in seen:
            raise CampaignError("%s duplicates model_id %r" % (where, model_id), EXIT_BAD_INPUT)
        seen.add(model_id)
        models.append(
            {
                "model_id": model_id,
                "model_path": model_path,
                "family": family,
                "provider": provider,
                "gpu_memory_utilization": float(gpu_util) if gpu_util is not None else None,
                "notes": entry.get("notes", ""),
                "slug": slug(model_id),
            }
        )
    return models


# --------------------------------------------------------------------------
# 20 % stratified repeat subset
# --------------------------------------------------------------------------
def strata_of(items) -> "OrderedDict[Tuple[str, str], List[str]]":
    buckets: Dict[Tuple[str, str], List[str]] = {}
    for item in items:
        key = tuple(getattr(item, f) for f in STRATUM_FIELDS)
        buckets.setdefault(key, []).append(item.item_id)
    out: "OrderedDict[Tuple[str, str], List[str]]" = OrderedDict()
    for key in sorted(buckets):
        out[key] = sorted(buckets[key])
    return out


def allocate(sizes: "OrderedDict[Tuple[str, str], int]", target: int) -> Dict[Tuple[str, str], int]:
    """Largest-remainder allocation of `target` draws over strata, >= 1 each.

    Deterministic: remainders descending, stratum key ascending as the tie-break.
    Every non-empty stratum gets at least one draw as long as the target allows.
    """
    keys = list(sizes)
    total = sum(sizes.values())
    if total == 0 or target <= 0:
        return {k: 0 for k in keys}
    target = min(target, total)
    quotas = {k: sizes[k] * target / float(total) for k in keys}
    alloc = {k: int(math.floor(quotas[k])) for k in keys}
    left = target - sum(alloc.values())
    order = sorted(keys, key=lambda k: (-(quotas[k] - math.floor(quotas[k])), k))
    i = 0
    while left > 0 and order:
        k = order[i % len(order)]
        if alloc[k] < sizes[k]:
            alloc[k] += 1
            left -= 1
        i += 1
        if i > 4 * len(order) + target:  # every stratum saturated
            break
    # Guarantee representation: move a draw from the largest stratum to any
    # stratum that would otherwise be unrepresented.
    for k in keys:
        if alloc[k] == 0 and sizes[k] > 0:
            donors = sorted(keys, key=lambda d: (-alloc[d], d))
            for donor in donors:
                if alloc[donor] >= 2:
                    alloc[donor] -= 1
                    alloc[k] = 1
                    break
    return alloc


def stratified_subset(
    items, fraction: float = REPEAT_FRACTION, seed: int = SAMPLING_SEED
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Return (item_ids, per-stratum plan) for the fixed-seed repeat subset."""
    buckets = strata_of(items)
    sizes: "OrderedDict[Tuple[str, str], int]" = OrderedDict(
        (k, len(v)) for k, v in buckets.items()
    )
    total = sum(sizes.values())
    target = int(total * fraction + 0.5)
    alloc = allocate(sizes, target)

    chosen: List[str] = []
    plan: List[Dict[str, Any]] = []
    for key, ids in buckets.items():
        k = alloc[key]
        rng = random.Random("%d|%s" % (seed, "|".join(key)))
        picked = sorted(rng.sample(ids, k)) if k else []
        chosen.extend(picked)
        plan.append(
            {
                "stratum": dict(zip(STRATUM_FIELDS, key)),
                "n_items": len(ids),
                "n_selected": k,
                "item_ids": picked,
            }
        )
    return sorted(chosen), plan


# --------------------------------------------------------------------------
# pre-flight
# --------------------------------------------------------------------------
def free_gb(path) -> float:
    target = Path(path)
    while not target.exists() and target != target.parent:
        target = target.parent
    return shutil.disk_usage(str(target)).free / (1024.0 ** 3)


def query_gpus() -> Tuple[Optional[List[Dict[str, int]]], Optional[str]]:
    """Return (gpu list, error). Each entry: {"index": i, "used_mib": m}."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "nvidia-smi unavailable (%s: %s)" % (type(exc).__name__, exc)
    if out.returncode != 0:
        return None, "nvidia-smi exit %d: %s" % (out.returncode, out.stderr.strip())
    gpus: List[Dict[str, int]] = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            return None, "unparseable nvidia-smi line: %r" % line
        try:
            gpus.append({"index": int(parts[0]), "used_mib": int(float(parts[1]))})
        except ValueError:
            return None, "unparseable nvidia-smi line: %r" % line
    if not gpus:
        return None, "nvidia-smi reported no GPUs"
    return gpus, None


def parse_visible_devices(value: Optional[str]) -> Optional[List[int]]:
    """Parse an inherited CUDA_VISIBLE_DEVICES into physical indices.

    None means "not set" (all GPUs are candidates). An empty or unparseable
    value means "no device": an empty list, which the caller reports as a
    refusal rather than silently falling back to every GPU.
    """
    if value is None:
        return None
    tokens = [t.strip() for t in str(value).split(",") if t.strip() != ""]
    indices: List[int] = []
    for token in tokens:
        try:
            indices.append(int(token))
        except ValueError:
            continue  # UUID form: not a physical index we can reason about
    return indices


def gpu_candidates(inherited: Optional[List[int]]) -> List[int]:
    """Candidate physical indices: GPUs 0-2, intersected with any inherited set."""
    candidates = [i for i in ALLOWED_GPUS if i != FORBIDDEN_GPU]
    if inherited is not None:
        candidates = [i for i in candidates if i in inherited]
    return candidates


def choose_gpu(
    gpus: Sequence[Dict[str, int]], candidates: Optional[Sequence[int]] = None
) -> Optional[int]:
    """First candidate GPU with < 4 GiB used. GPU 3 is never a candidate."""
    used = {g["index"]: g["used_mib"] for g in gpus}
    for index in (candidates if candidates is not None else gpu_candidates(None)):
        if index == FORBIDDEN_GPU:
            continue
        if index in used and used[index] < GPU_FREE_MAX_USED_MIB:
            return index
    return None


def pin_gpu(index: Optional[int]) -> Optional[str]:
    """Restrict THIS process to one physical GPU, before any engine is built.

    CUDA reads CUDA_VISIBLE_DEVICES once, when the driver is initialised, so
    this must happen before a provider (and therefore a vLLM engine) is
    constructed. Returns the value set, or None when no GPU was chosen.
    """
    if index is None:
        return None
    value = str(index)
    os.environ["CUDA_VISIBLE_DEVICES"] = value
    return value


def select_gpu(
    needs_gpu: bool,
    gpu_probe=query_gpus,
    override: Optional[int] = None,
    env_value: Optional[str] = None,
) -> Dict[str, Any]:
    """Choose the physical GPU for this step and explain the choice.

    Honours an inherited CUDA_VISIBLE_DEVICES (candidates are restricted to it),
    applies the < 4 GiB-used rule and never selects GPU 3. `override` (--gpu) is
    refused if it is GPU 3, outside 0-2, outside the inherited set, unknown to
    nvidia-smi, or already carrying >= 4 GiB.
    """
    inherited = parse_visible_devices(env_value)
    candidates = gpu_candidates(inherited)
    record: Dict[str, Any] = {
        "required": needs_gpu,
        "visible": None,
        "error": None,
        "chosen": None,
        "allowed": list(ALLOWED_GPUS),
        "never": FORBIDDEN_GPU,
        "candidates": candidates,
        "inherited_cuda_visible_devices": env_value,
        "inherited": inherited is not None,
        "override": override,
        "source": None,
        "pinned_cuda_visible_devices": None,
        "criterion": "first candidate GPU with < %d MiB used" % GPU_FREE_MAX_USED_MIB,
        "ok": not needs_gpu,
    }
    if not needs_gpu:
        record["error"] = "not required for this step"
        return record

    gpus, gpu_error = gpu_probe()
    record["visible"] = gpus
    if gpus is None:
        record["error"] = gpu_error
        return record
    used = {g["index"]: g["used_mib"] for g in gpus}

    if override is not None:
        if override == FORBIDDEN_GPU or override not in gpu_candidates(None):
            record["error"] = (
                "--gpu %d refused: allowed GPUs are %s and GPU %d is another user's job"
                % (override, list(ALLOWED_GPUS), FORBIDDEN_GPU)
            )
            return record
        if inherited is not None and override not in candidates:
            record["error"] = (
                "--gpu %d refused: CUDA_VISIBLE_DEVICES=%s does not expose it"
                % (override, env_value)
            )
            return record
        if override not in used:
            record["error"] = "--gpu %d refused: nvidia-smi does not report it" % override
            return record
        if used[override] >= GPU_FREE_MAX_USED_MIB:
            record["error"] = (
                "--gpu %d refused: %d MiB already in use (>= %d MiB)"
                % (override, used[override], GPU_FREE_MAX_USED_MIB)
            )
            return record
        record.update({"chosen": override, "source": "--gpu flag", "ok": True})
        return record

    if not candidates:
        record["error"] = (
            "no candidate GPU: CUDA_VISIBLE_DEVICES=%s leaves none of %s"
            % (env_value, [i for i in ALLOWED_GPUS if i != FORBIDDEN_GPU])
        )
        return record
    chosen = choose_gpu(gpus, candidates)
    if chosen is None:
        record["error"] = "no free GPU among %s (< %d MiB used)" % (
            candidates,
            GPU_FREE_MAX_USED_MIB,
        )
        return record
    record.update({"chosen": chosen, "source": "first free candidate", "ok": True})
    return record


def preflight(
    out_root: Path,
    model: Dict[str, Any],
    run_class: str,
    prereg: Path,
    sha: Path,
    gpu_probe=query_gpus,
    gpu_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Disk, GPU and freeze checks for one model. Returns a record with ok flags."""
    free = free_gb(out_root)
    disk = {
        "path": str(out_root),
        "free_gb": round(free, 2),
        "required_gb": MIN_FREE_GB,
        "ok": free >= MIN_FREE_GB,
        "enforced": run_class == "confirmatory",
    }

    needs_gpu = model["provider"] == "vllm"
    gpu = select_gpu(
        needs_gpu,
        gpu_probe=gpu_probe,
        override=gpu_override,
        env_value=os.environ.get("CUDA_VISIBLE_DEVICES"),
    )
    if not needs_gpu:
        gpu["error"] = "not required (provider=%s)" % model["provider"]

    freeze: Dict[str, Any] = {
        "required": run_class == "confirmatory",
        "prereg": str(prereg),
        "sha": str(sha),
        "sha256": None,
        "ok": True,
        "error": None,
    }
    if freeze["required"]:
        try:
            freeze["sha256"] = verify(prereg, sha)
        except FileNotFoundError as exc:
            freeze["ok"] = False
            freeze["error"] = "MISSING_FILE: %s" % exc
        except FreezeMismatch as exc:
            freeze["ok"] = False
            freeze["error"] = "FREEZE_MISMATCH: %s" % exc
    else:
        freeze["error"] = "skipped (--class smoke; a smoke run is never evidence)"

    disk_ok = disk["ok"] or run_class == "smoke"
    record = {
        "model_id": model["model_id"],
        "disk": disk,
        "gpu": gpu,
        "freeze": freeze,
        "ok": bool(disk_ok and gpu["ok"] and freeze["ok"]),
        "checked_utc": utc_stamp(),
    }
    if not disk["ok"] and run_class == "smoke":
        disk["note"] = (
            "below %.0f GB but not enforced for a smoke run (never evidence)" % MIN_FREE_GB
        )
    return record


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------
def build_plan(
    items,
    items_path: Path,
    models: List[Dict[str, Any]],
    cohort: str,
    run_class: str,
    out_root: Path,
) -> Dict[str, Any]:
    subset_ids, strata_plan = stratified_subset(items)
    runs_per_model = [
        {
            "tag": "main",
            "condition_tag": MAIN_CONDITION,
            "temperature": MAIN_TEMPERATURE,
            "seed": SAMPLING_SEED,
            "n_items": len(items),
            "item_scope": "full item set",
        }
    ]
    for k in range(1, REPEAT_COUNT + 1):
        runs_per_model.append(
            {
                "tag": "repeat_%d" % k,
                "condition_tag": "repeat_%d" % k,
                "temperature": REPEAT_TEMPERATURE,
                "seed": SAMPLING_SEED + k,
                "n_items": len(subset_ids),
                "item_scope": "20%% stratified repeat subset (seed %d)" % SAMPLING_SEED,
            }
        )
    return {
        "cohort": cohort,
        "class": run_class,
        "created_utc": utc_stamp(),
        "items_path": str(items_path),
        "items_sha256": sha256_file(items_path),
        "n_items": len(items),
        "subset": {
            "fraction": REPEAT_FRACTION,
            "seed": SAMPLING_SEED,
            "stratify_by": list(STRATUM_FIELDS),
            "n_selected": len(subset_ids),
            "item_ids": subset_ids,
            "strata": strata_plan,
        },
        "main_condition": MAIN_CONDITION,
        "out_root": str(out_root),
        "models": [
            {
                "model_id": m["model_id"],
                "model_path": m["model_path"],
                "family": m["family"],
                "provider": m["provider"],
                "gpu_memory_utilization": m["gpu_memory_utilization"],
                "notes": m["notes"],
                "runs": [dict(r) for r in runs_per_model],
            }
            for m in models
        ],
        "n_runs_total": len(models) * len(runs_per_model),
    }


def print_plan(plan: Dict[str, Any], preflights: List[Dict[str, Any]], stream=None) -> None:
    # Resolved at call time so a redirected stdout is honoured.
    w = (stream or sys.stdout).write
    w("CAMPAIGN PLAN cohort=%s class=%s\n" % (plan["cohort"], plan["class"]))
    w("items: %s (n=%d, sha256=%s)\n" % (plan["items_path"], plan["n_items"], plan["items_sha256"]))
    sub = plan["subset"]
    w(
        "repeat subset: %d item(s) = %.1f%% of %d, stratified by %s, seed %d\n"
        % (
            sub["n_selected"],
            100.0 * sub["n_selected"] / max(plan["n_items"], 1),
            plan["n_items"],
            " x ".join(sub["stratify_by"]),
            sub["seed"],
        )
    )
    for s in sub["strata"]:
        w(
            "  stratum %s: %d of %d\n"
            % (
                "/".join(str(s["stratum"][f]) for f in STRATUM_FIELDS),
                s["n_selected"],
                s["n_items"],
            )
        )
    w("out-root: %s\n" % plan["out_root"])
    w("runs: %d (%d model(s) x %d run(s))\n" % (plan["n_runs_total"], len(plan["models"]), len(plan["models"][0]["runs"]) if plan["models"] else 0))
    for model, pre in zip(plan["models"], preflights):
        w(
            "MODEL %s (family=%s provider=%s gpu_util=%s)\n"
            % (model["model_id"], model["family"], model["provider"], model["gpu_memory_utilization"])
        )
        w("  path: %s\n" % model["model_path"])
        for r in model["runs"]:
            w(
                "  run %-9s temperature=%.1f seed=%d items=%d (%s)\n"
                % (r["tag"], r["temperature"], r["seed"], r["n_items"], r["item_scope"])
            )
        d = pre["disk"]
        w(
            "  preflight disk: free %.2f GB / required %.0f GB -> %s%s\n"
            % (d["free_gb"], d["required_gb"], "OK" if d["ok"] else "FAIL",
               "" if d["ok"] or d["enforced"] else " (not enforced for smoke)")
        )
        g = pre["gpu"]
        if not g["required"]:
            w("  preflight gpu : not required (provider=%s)\n" % model["provider"])
        elif g["chosen"] is not None:
            w(
                "  preflight gpu : GPU %d via %s (%s; candidates %s%s; GPU %d never "
                "used) -> CUDA_VISIBLE_DEVICES=%d\n"
                % (g["chosen"], g["source"], g["criterion"], g["candidates"],
                   "; inherited CUDA_VISIBLE_DEVICES=%s" % g["inherited_cuda_visible_devices"]
                   if g["inherited"] else "",
                   FORBIDDEN_GPU, g["chosen"])
            )
        else:
            w("  preflight gpu : FAIL (%s)\n" % (g["error"] or "no free GPU among 0-2"))
        f = pre["freeze"]
        if not f["required"]:
            w("  preflight freeze: %s\n" % f["error"])
        elif f["ok"]:
            w("  preflight freeze: OK sha256=%s\n" % f["sha256"])
        else:
            w("  preflight freeze: FAIL %s\n" % f["error"])
        w("  preflight: %s\n" % ("OK" if pre["ok"] else "REFUSED"))


# --------------------------------------------------------------------------
# EXPERIMENTS.csv
# --------------------------------------------------------------------------
def append_experiment_row(csv_path: Path, row: Dict[str, str]) -> None:
    """Append one row, creating the file with the frozen header if it is absent."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.is_file():
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh), None)
        if header is None:
            raise CampaignError("empty EXPERIMENTS csv: %s" % csv_path, EXIT_BAD_INPUT)
        if tuple(header) != EXPERIMENTS_HEADER:
            raise CampaignError(
                "EXPERIMENTS csv header %s does not match the expected %s"
                % (header, list(EXPERIMENTS_HEADER)),
                EXIT_BAD_INPUT,
            )
    else:
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow(EXPERIMENTS_HEADER)
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow([row.get(k, "") for k in EXPERIMENTS_HEADER])


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------
def make_provider(model: Dict[str, Any], temperature: float, seed: int, gpu_index: Optional[int]):
    """Build the provider for one run, applying temperature/seed at construction."""
    if model["provider"] == "vllm":
        if gpu_index is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        opts: Dict[str, Any] = {
            "model_path": model["model_path"],
            "temperature": float(temperature),
            "seed": int(seed),
        }
        if model["gpu_memory_utilization"] is not None:
            opts["gpu_memory_utilization"] = model["gpu_memory_utilization"]
        return get_provider("vllm", **opts)
    return get_provider(model["provider"])


def execute_one_run(
    model: Dict[str, Any],
    spec: Dict[str, Any],
    items,
    cohort: str,
    run_class: str,
    out_root: Path,
    log_dir: Path,
    gpu_index: Optional[int],
    command: str,
    experiments_csv: Path,
) -> Dict[str, Any]:
    """Run one (model, tag) unit, require its MARKER, append its EXPERIMENTS row."""
    tag = spec["tag"]
    run_id = kyra_runner.make_run_id("%s|%s|%s" % (cohort, model["slug"], tag), str(spec["items_path"]))
    run_dir = out_root / cohort / model["slug"] / tag / run_id
    run_key = "%s__%s__%s__%s" % (cohort, model["slug"], tag, run_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / ("%s.log" % run_key)

    record: Dict[str, Any] = {
        "run_key": run_key,
        "run_id": run_id,
        "model_id": model["model_id"],
        "family": model["family"],
        "provider": model["provider"],
        "tag": tag,
        "condition_tag": spec["condition_tag"],
        "temperature_requested": spec["temperature"],
        "seed": spec["seed"],
        "n_items": len(items),
        "gpu": gpu_index,
        "run_dir": str(run_dir),
        "log": str(log_path),
        "marker_sha256": None,
        "status": "failed",
        "failure": None,
        "started_utc": utc_stamp(),
        "finished_utc": None,
    }

    lines: List[str] = [
        "run_key=%s" % run_key,
        "started_utc=%s" % record["started_utc"],
        "model_id=%s family=%s provider=%s path=%s"
        % (model["model_id"], model["family"], model["provider"], model["model_path"]),
        "tag=%s condition=%s temperature=%s seed=%s"
        % (tag, spec["condition_tag"], spec["temperature"], spec["seed"]),
        "items=%d gpu=%s run_dir=%s" % (len(items), gpu_index, run_dir),
    ]

    try:
        provider = make_provider(model, spec["temperature"], spec["seed"], gpu_index)
        lines.append(
            "provider_ready model_id=%s api_version=%s"
            % (getattr(provider, "model_id", "?"), getattr(provider, "api_version", "?"))
        )
        ok, reasons = kyra_runner.execute_run(
            items,
            provider,
            [spec["condition_tag"]],
            run_dir,
            temperature=spec["temperature"],
        )
    except Exception as exc:  # provider/engine failure is a failed run, never a score
        ok, reasons = False, ["%s: %s" % (type(exc).__name__, exc)]
        lines.append("exception: %s: %s" % (type(exc).__name__, exc))

    marker_path = run_dir / mf.MARKER_NAME
    if ok and marker_path.is_file():
        record["status"] = "completed"
        record["marker_sha256"] = sha256_file(marker_path)
        lines.append("MARKER sha256=%s" % record["marker_sha256"])
    else:
        record["status"] = "failed"
        record["failure"] = "; ".join(reasons) if reasons else "MARKER not written"
        lines.append("FAILED: %s" % record["failure"])
    record["finished_utc"] = utc_stamp()
    lines.append("finished_utc=%s" % record["finished_utc"])
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    config = (
        "model=%s; family=%s; provider=%s; temperature=%s; seed=%s; condition=%s; "
        "items=%d; gpu=%s; cohort=%s; item_scope=%s"
        % (
            model["model_id"],
            model["family"],
            model["provider"],
            spec["temperature"],
            spec["seed"],
            spec["condition_tag"],
            len(items),
            gpu_index,
            cohort,
            spec["item_scope"],
        )
    )
    failure = record["failure"] or (
        "none (smoke: never evidence)" if run_class == "smoke" else "none"
    )
    append_experiment_row(
        experiments_csv,
        {
            "run": run_key,
            "class": run_class,
            "config": config,
            "seed": str(spec["seed"]),
            "command": command,
            "raw": str(run_dir) + "/",
            "log": str(log_path),
            "marker": (
                "MARKER sha256 %s" % record["marker_sha256"]
                if record["marker_sha256"]
                else "n/a (no MARKER)"
            ),
            "status": record["status"],
            "failure": failure,
        },
    )
    return record


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kyra.campaign",
        description="Run the phase-A item set against a list of models, one model "
        "at a time, with disk/GPU guards, MARKERs, repeats and EXPERIMENTS rows.",
    )
    p.add_argument("--items", required=True, help="items JSONL path")
    p.add_argument("--models", required=True, help="models.json path")
    p.add_argument("--cohort", required=True, help="cohort name (run directory level)")
    p.add_argument(
        "--class",
        dest="run_class",
        required=True,
        choices=list(RUN_CLASSES),
        help="confirmatory (freeze verified) or smoke (never evidence)",
    )
    p.add_argument("--dry-run", action="store_true", help="print the plan and pre-flight only")
    p.add_argument(
        "--out-root",
        default=None,
        help="root for <out-root>/<cohort>/... (default result/raw); a --dry-run "
        "writes its plan JSON only when this is given explicitly, so a dry run "
        "never leaves an artifact in result/raw",
    )
    p.add_argument(
        "--experiments-csv", default="research/EXPERIMENTS.csv", help="EXPERIMENTS.csv to append to"
    )
    p.add_argument(
        "--gpu",
        type=int,
        default=None,
        help="pin this physical GPU instead of choosing the first free one; "
        "refused if it is GPU %d or already carries >= %d MiB"
        % (FORBIDDEN_GPU, GPU_FREE_MAX_USED_MIB),
    )
    p.add_argument("--prereg", default="PREREGISTERED_kyra_v2.yaml", help="frozen preregistration")
    p.add_argument("--sha", default="PREREGISTERED_kyra_v2.yaml.sha256", help="freeze receipt")
    return p


def command_string(argv: Optional[List[str]]) -> str:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    return "PYTHONPATH=src python -m kyra.campaign " + " ".join(args)


def record_campaign_json(
    out_root: Path,
    cohort: str,
    payload: Dict[str, Any],
    dry_run: bool,
    out_root_explicit: bool,
    suffix: str = "",
):
    """Write the campaign record, except for a dry run with no explicit out-root.

    A dry run executes nothing, so it must not leave a file in the default data
    root (result/raw). Returns the path written, or None.
    """
    if dry_run and not out_root_explicit:
        return None
    return write_campaign_json(out_root, cohort, payload, suffix=suffix)


def write_campaign_json(
    out_root: Path, cohort: str, payload: Dict[str, Any], suffix: str = ""
) -> Path:
    path = out_root / cohort / ("campaign_%s%s.json" % (cohort, suffix))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# scoring sub-command: judges + panel over finished run directories
# --------------------------------------------------------------------------
JUDGE_VIEWS = "prefix"  # frozen: one record per (item_id, condition, depth)
PANEL_NAME = "panel.jsonl"


def load_judges(path) -> List[Dict[str, Any]]:
    """Read and validate judges.json. Any problem is a hard refusal."""
    p = Path(path)
    if not p.is_file():
        raise CampaignError("judges file not found: %s" % p, EXIT_BAD_INPUT)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError("judges file unreadable: %s (%s)" % (p, exc), EXIT_BAD_INPUT)
    if isinstance(doc, dict):
        doc = doc.get("judges")
    if not isinstance(doc, list) or not doc:
        raise CampaignError(
            "judges file must hold a non-empty list of judge objects: %s" % p, EXIT_BAD_INPUT
        )

    judges: List[Dict[str, Any]] = []
    seen = set()
    for index, entry in enumerate(doc):
        where = "%s[%d]" % (p.name, index)
        if not isinstance(entry, dict):
            raise CampaignError("%s is not an object" % where, EXIT_BAD_INPUT)
        judge_id = entry.get("judge_id")
        if not isinstance(judge_id, str) or not judge_id.strip():
            raise CampaignError("%s has no judge_id" % where, EXIT_BAD_INPUT)
        if judge_id in seen:
            raise CampaignError("%s duplicates judge_id %r" % (where, judge_id), EXIT_BAD_INPUT)
        seen.add(judge_id)
        family = entry.get("family")
        if not isinstance(family, str) or not family.strip():
            raise CampaignError("%s has no family" % where, EXIT_BAD_INPUT)
        provider = entry.get("provider")
        if provider not in ("vllm", "mock", "fake"):
            raise CampaignError(
                "%s has provider %r (expected 'vllm', or 'mock'/'fake' for smoke runs)"
                % (where, provider),
                EXIT_BAD_INPUT,
            )
        model_id = entry.get("model_id") or entry.get("model_path")
        model_path = entry.get("model_path") or entry.get("model_id")
        if provider == "vllm" and (not isinstance(model_path, str) or not model_path.strip()):
            raise CampaignError(
                "%s uses provider vllm but has no model_id/model_path" % where, EXIT_BAD_INPUT
            )
        gpu_util = entry.get("gpu_memory_utilization")
        if gpu_util is not None and (
            isinstance(gpu_util, bool) or not isinstance(gpu_util, (int, float))
        ):
            raise CampaignError(
                "%s gpu_memory_utilization must be a number" % where, EXIT_BAD_INPUT
            )
        judges.append(
            {
                "judge_id": judge_id,
                "model_id": model_id or judge_id,
                "model_path": model_path,
                "family": family,
                "provider": provider,
                "gpu_memory_utilization": float(gpu_util) if gpu_util is not None else None,
                "fake_outputs": entry.get("fake_outputs"),
                "notes": entry.get("notes", ""),
            }
        )
    return judges


def expand_runs(patterns: Sequence[str]) -> List[Path]:
    """Resolve run-dir arguments: literal directories and/or globs."""
    found: List[Path] = []
    for pattern in patterns:
        p = Path(pattern)
        if p.is_dir():
            found.append(p)
            continue
        matches = sorted(Path(m) for m in glob.glob(pattern))
        matches = [m for m in matches if m.is_dir()]
        if not matches:
            raise CampaignError(
                "no run directory matches %r (a missing run is never scored silently)"
                % pattern,
                EXIT_BAD_INPUT,
            )
        found.extend(matches)
    unique: List[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    if not unique:
        raise CampaignError("no run directories to score", EXIT_BAD_INPUT)
    return unique


def class_for_run(csv_path: Path, run_dir: Path, override: Optional[str]) -> Tuple[str, str]:
    """Return (class, source). The run's own EXPERIMENTS row decides, else --class."""
    if override:
        return override, "--class flag"
    target = str(run_dir).rstrip("/")
    if Path(csv_path).is_file():
        with Path(csv_path).open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                raw = str(row.get("raw", "")).rstrip("/")
                if raw and raw == target:
                    return str(row.get("class", "")).strip(), "EXPERIMENTS row %s" % row.get("run")
    raise CampaignError(
        "no EXPERIMENTS row has raw=%s and no --class was given: refusing to guess "
        "whether this run is confirmatory" % target,
        EXIT_BAD_INPUT,
    )


def model_for_run(run_dir: Path, models: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
    """Find the evaluated model (hence its family) for a run directory.

    1. the manifest's model_id matches a models.json model_id;
    2. else a path component matches a model's slug (campaign layout);
    otherwise it is an error - the leave-one-family-out rule may not run on a
    guessed family.
    """
    manifest_ids: List[str] = []
    manifest_path = Path(run_dir) / mf.MANIFEST_NAME
    if manifest_path.is_file():
        with manifest_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mid = rec.get("model_id")
                if isinstance(mid, str) and mid not in manifest_ids:
                    manifest_ids.append(mid)
    for model in models:
        if model["model_id"] in manifest_ids:
            return model, "manifest model_id=%s" % model["model_id"]
    parts = set(Path(run_dir).resolve().parts)
    for model in models:
        if model["slug"] in parts:
            return model, "run path component %s" % model["slug"]
    raise CampaignError(
        "cannot tell which model produced %s (manifest model_id(s): %s; models.json: %s) - "
        "refusing to guess the evaluated family for leave-one-family-out"
        % (run_dir, manifest_ids or "none", [m["model_id"] for m in models]),
        EXIT_BAD_INPUT,
    )


def run_item_ids(run_dir: Path) -> List[str]:
    """The item_ids a run actually produced, in first-seen order."""
    path = Path(run_dir) / mf.RESPONSES_NAME
    if not path.is_file():
        raise CampaignError(
            "refusing to score %s: no %s" % (run_dir, mf.RESPONSES_NAME), EXIT_PREFLIGHT
        )
    ids: List[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CampaignError(
                    "%s:%d is not valid JSON (%s)" % (path, lineno, exc), EXIT_PREFLIGHT
                )
            item_id = rec.get("item_id") if isinstance(rec, dict) else None
            if not isinstance(item_id, str):
                raise CampaignError(
                    "%s:%d has no item_id" % (path, lineno), EXIT_PREFLIGHT
                )
            if item_id not in ids:
                ids.append(item_id)
    if not ids:
        raise CampaignError(
            "refusing to score %s: %s carries no records" % (run_dir, mf.RESPONSES_NAME),
            EXIT_PREFLIGHT,
        )
    return ids


def judge_command(
    judge: Dict[str, Any],
    run_dir: Path,
    items_path: Path,
    out_path: Path,
    anchors: Optional[Path],
) -> List[str]:
    """The kyra.judge argv for one judge on one run (views=prefix, items given)."""
    cmd = [
        sys.executable,
        "-m",
        "kyra.judge",
        "--run-dir",
        str(run_dir),
        "--provider",
        judge["provider"],
        "--judge-id",
        judge["judge_id"],
        "--family",
        judge["family"],
        "--views",
        JUDGE_VIEWS,
        "--items",
        str(items_path),
        "--out",
        str(out_path),
    ]
    if judge["provider"] == "vllm":
        cmd += ["--model-path", str(judge["model_path"])]
        if judge["gpu_memory_utilization"] is not None:
            cmd += ["--gpu-memory-utilization", str(judge["gpu_memory_utilization"])]
    if judge["provider"] == "fake" and judge.get("fake_outputs"):
        cmd += ["--fake-outputs", str(judge["fake_outputs"])]
    if anchors is not None:
        cmd += ["--anchors", str(anchors)]
    return cmd


def panel_command(
    judge_files: List[Path], family_map_path: Path, evaluated_family: str, out_path: Path
) -> List[str]:
    return (
        [sys.executable, "-m", "kyra.panel", "--judges"]
        + [str(p) for p in judge_files]
        + [
            "--family-map",
            str(family_map_path),
            "--evaluated-family",
            evaluated_family,
            "--out",
            str(out_path),
        ]
    )


def shell_repr(cmd: Sequence[str]) -> str:
    return "PYTHONPATH=src " + " ".join(shlex.quote(str(c)) for c in cmd)


def run_subprocess(cmd: Sequence[str], log_path: Path, repo_root: Path, gpu: Optional[int]):
    """Run one child process, tee its output to a log, return (returncode, text)."""
    env = dict(os.environ)
    src = str(repo_root / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu)
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "command: %s\nexit=%d\n--- stdout ---\n%s\n--- stderr ---\n%s\n"
        % (shell_repr(cmd), proc.returncode, proc.stdout, proc.stderr),
        encoding="utf-8",
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def score_main(argv: List[str], gpu_probe=query_gpus) -> int:
    """`kyra.campaign score ...`: judges then panel over finished run dirs."""
    parser = build_score_parser()
    args = parser.parse_args(argv)
    command = "PYTHONPATH=src python -m kyra.campaign score " + " ".join(
        shlex.quote(a) for a in argv
    )
    repo_root = Path(__file__).resolve().parents[2]
    out_root = Path(args.out_root) if args.out_root else Path(DEFAULT_OUT_ROOT)
    out_root_explicit = args.out_root is not None
    items_path = Path(args.items)
    experiments_csv = Path(args.experiments_csv)
    prereg, sha = Path(args.prereg), Path(args.sha)
    anchors_path = Path(args.anchors) if args.anchors else None

    try:
        models = load_models(args.models, "smoke")  # provider rules apply to runs, not scoring
        judges = load_judges(args.judges)
        if not items_path.is_file():
            raise CampaignError("items file not found: %s" % items_path, EXIT_BAD_INPUT)
        if anchors_path is not None and not anchors_path.is_file():
            raise CampaignError("anchors file not found: %s" % anchors_path, EXIT_BAD_INPUT)
        run_dirs = expand_runs(args.runs)
    except CampaignError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return exc.code

    anchors_sha = sha256_file(anchors_path) if anchors_path is not None else None
    try:
        scored_items = load_items(items_path)
    except ValueError as exc:
        sys.stderr.write("ERROR: could not load items: %s\n" % exc)
        return EXIT_BAD_INPUT
    known_item_ids = {it.item_id for it in scored_items}
    control_item_ids = {it.item_id for it in scored_items if it.risk_group == "CTRL"}
    family_map = {j["judge_id"]: j["family"] for j in judges}
    model_families = {m["model_id"]: m["family"] for m in models}

    plan: Dict[str, Any] = {
        "cohort": args.cohort,
        "created_utc": utc_stamp(),
        "allow_panel_overwrite": bool(args.allow_panel_overwrite),
        "items_path": str(items_path),
        "items_sha256": sha256_file(items_path),
        "views": JUDGE_VIEWS,
        "anchors_path": str(anchors_path) if anchors_path else None,
        "anchors_sha256": anchors_sha,
        "judges": [
            {k: j[k] for k in ("judge_id", "family", "provider", "model_id", "notes")}
            for j in judges
        ],
        "family_map": family_map,
        "model_families": model_families,
        "out_root": str(out_root),
        "runs": [],
    }

    # Per-run bookkeeping: MARKER, class, evaluated family, judge output paths.
    try:
        for run_dir in run_dirs:
            marker = Path(run_dir) / mf.MARKER_NAME
            if not marker.is_file():
                raise CampaignError(
                    "refusing to score %s: no MARKER (an unvalidated run is not data)"
                    % run_dir,
                    EXIT_PREFLIGHT,
                )
            run_class, class_source = class_for_run(experiments_csv, Path(run_dir), args.run_class)
            if run_class not in RUN_CLASSES:
                raise CampaignError(
                    "run %s has class %r (expected one of %s)"
                    % (run_dir, run_class, ", ".join(RUN_CLASSES)),
                    EXIT_BAD_INPUT,
                )
            model, model_source = model_for_run(Path(run_dir), models)
            run_ids = run_item_ids(Path(run_dir))
            missing = [i for i in run_ids if i not in known_item_ids]
            if missing:
                raise CampaignError(
                    "refusing to score %s: %d item_id(s) in responses.jsonl are absent "
                    "from %s, so their risk_group (and therefore which views are "
                    "CTRL controls) is unknown: %s"
                    % (run_dir, len(missing), items_path, ", ".join(missing[:20])
                       + (" ..." if len(missing) > 20 else "")),
                    EXIT_PREFLIGHT,
                )
            judge_files = [
                Path(run_dir) / ("judge_%s.jsonl" % j["judge_id"]) for j in judges
            ]
            existing = [str(p) for p in judge_files if p.exists()]
            panel_file = Path(run_dir) / PANEL_NAME
            plan["runs"].append(
                {
                    "run_dir": str(run_dir),
                    "marker_sha256": sha256_file(marker),
                    "class": run_class,
                    "class_source": class_source,
                    "model_id": model["model_id"],
                    "evaluated_family": model["family"],
                    "model_source": model_source,
                    "n_items": len(run_ids),
                    "n_control_items": sum(1 for i in run_ids if i in control_item_ids),
                    "judge_files": [str(p) for p in judge_files],
                    "existing_judge_files": existing,
                    "panel_file": str(panel_file),
                    "panel_exists": panel_file.exists(),
                }
            )
    except CampaignError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return exc.code

    confirmatory = [r for r in plan["runs"] if r["class"] == "confirmatory"]
    freeze: Dict[str, Any] = {
        "required": bool(confirmatory),
        "prereg": str(prereg),
        "sha": str(sha),
        "sha256": None,
        "ok": True,
        "error": None,
    }
    if freeze["required"]:
        try:
            freeze["sha256"] = verify(prereg, sha)
        except FileNotFoundError as exc:
            freeze["ok"], freeze["error"] = False, "MISSING_FILE: %s" % exc
        except FreezeMismatch as exc:
            freeze["ok"], freeze["error"] = False, "FREEZE_MISMATCH: %s" % exc
    else:
        freeze["error"] = "skipped (no confirmatory run in this scoring batch)"

    needs_gpu = any(j["provider"] == "vllm" for j in judges)
    gpu = select_gpu(
        needs_gpu,
        gpu_probe=gpu_probe,
        override=args.gpu,
        env_value=os.environ.get("CUDA_VISIBLE_DEVICES"),
    )
    if not needs_gpu:
        gpu["error"] = "not required (no vllm judge)"

    payload: Dict[str, Any] = {
        "plan": plan,
        "command": command,
        "dry_run": bool(args.dry_run),
        "allow_panel_overwrite": bool(args.allow_panel_overwrite),
        "experiments_csv": str(experiments_csv),
        "freeze": freeze,
        "gpu": gpu,
        "judge_runs": [],
        "panel_runs": [],
        "status": "planned",
        "stopped_because": None,
        "note": "judges run one model at a time as child processes (kyra.judge "
        "--views prefix --items <items>, so control ids come from risk_group "
        "CTRL); the panel is kyra.panel over this run's judge files",
    }

    print_score_plan(plan, freeze, gpu)

    if not freeze["ok"] or not gpu["ok"]:
        reason = "scoring pre-flight refused: %s" % (freeze["error"] or gpu["error"] or "no GPU")
        payload["status"] = "refused"
        payload["stopped_because"] = reason
        path = record_campaign_json(
            out_root, args.cohort, payload, args.dry_run, out_root_explicit, suffix="_scoring"
        )
        sys.stderr.write("ERROR: %s\ncampaign record: %s\n" % (reason, path))
        return EXIT_FREEZE_MISMATCH if not freeze["ok"] else EXIT_PREFLIGHT

    blocked = [r for r in plan["runs"] if r["existing_judge_files"]]
    panel_blocked = [
        r for r in plan["runs"] if r["panel_exists"] and not args.allow_panel_overwrite
    ]
    if blocked or panel_blocked:
        if blocked:
            reason = "judge output already exists, refusing to overwrite: %s" % ", ".join(
                blocked[0]["existing_judge_files"]
            )
        else:
            reason = (
                "panel output already exists, refusing to overwrite: %s "
                "(pass --allow-panel-overwrite to replace it)" % panel_blocked[0]["panel_file"]
            )
        payload["status"] = "refused"
        payload["stopped_because"] = reason
        path = record_campaign_json(
            out_root, args.cohort, payload, args.dry_run, out_root_explicit, suffix="_scoring"
        )
        sys.stderr.write("ERROR: %s\ncampaign record: %s\n" % (reason, path))
        return EXIT_PREFLIGHT

    if args.dry_run:
        payload["status"] = "dry-run"
        path = record_campaign_json(
            out_root, args.cohort, payload, True, out_root_explicit, suffix="_scoring"
        )
        sys.stdout.write(
            "DRY RUN: nothing scored. campaign record: %s\n"
            % (path if path else "not written (pass --out-root to record the plan)")
        )
        return EXIT_OK

    # Pin before the first judge child process starts; the chosen physical index
    # is also passed into each child's environment explicitly.
    gpu["pinned_cuda_visible_devices"] = pin_gpu(gpu["chosen"])
    if gpu["chosen"] is not None:
        sys.stdout.write(
            "GPU: pinned CUDA_VISIBLE_DEVICES=%s (physical GPU %d)\n"
            % (gpu["pinned_cuda_visible_devices"], gpu["chosen"])
        )

    log_dir = out_root / args.cohort / "scoring_logs"
    family_map_path = out_root / args.cohort / ("family_map_%s.json" % args.cohort)
    family_map_path.parent.mkdir(parents=True, exist_ok=True)
    family_map_path.write_text(
        json.dumps(family_map, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def stop(reason: str, code: int) -> int:
        payload["status"] = "failed"
        payload["stopped_because"] = reason
        path = write_campaign_json(out_root, args.cohort, payload, suffix="_scoring")
        sys.stderr.write("ERROR: %s\ncampaign record: %s\n" % (reason, path))
        return code

    for run in plan["runs"]:
        run_dir = Path(run["run_dir"])
        run_key = "%s__%s" % (args.cohort, run_dir.name)
        judge_files: List[Path] = []
        for judge in judges:  # one judge model loaded at a time
            out_path = run_dir / ("judge_%s.jsonl" % judge["judge_id"])
            key = "%s__judge_%s" % (run_key, judge["judge_id"])
            cmd = judge_command(judge, run_dir, items_path, out_path, anchors_path)
            log_path = log_dir / ("%s.log" % key)
            sys.stdout.write("JUDGE %s on %s\n" % (judge["judge_id"], run_dir))
            code, output = run_subprocess(cmd, log_path, repo_root, gpu["chosen"])
            ok = code == 0 and out_path.is_file()
            record = {
                "run_key": key,
                "run_dir": str(run_dir),
                "judge_id": judge["judge_id"],
                "family": judge["family"],
                "provider": judge["provider"],
                "class": run["class"],
                "out": str(out_path),
                "log": str(log_path),
                "exit_code": code,
                "sha256": sha256_file(out_path) if out_path.is_file() else None,
                "status": "completed" if ok else "failed",
                "failure": None if ok else (output[-800:] or "kyra.judge exit %d" % code),
                "anchors_sha256": anchors_sha,
            }
            payload["judge_runs"].append(record)
            append_experiment_row(
                experiments_csv,
                {
                    "run": key,
                    "class": run["class"],
                    "config": "judge=%s; family=%s; provider=%s; model=%s; views=%s; "
                    "items=%s; anchors=%s; anchors_sha256=%s; evaluated_family=%s; "
                    "gpu=%s; run_dir=%s"
                    % (
                        judge["judge_id"],
                        judge["family"],
                        judge["provider"],
                        judge["model_id"],
                        JUDGE_VIEWS,
                        items_path,
                        anchors_path if anchors_path else "none",
                        anchors_sha or "n/a",
                        run["evaluated_family"],
                        gpu["chosen"],
                        run_dir,
                    ),
                    "seed": "n/a (judge)",
                    "command": shell_repr(cmd),
                    "raw": str(out_path),
                    "log": str(log_path),
                    "marker": (
                        "judge_file sha256 %s" % record["sha256"]
                        if record["sha256"]
                        else "n/a (no judge file)"
                    ),
                    "status": record["status"],
                    "failure": record["failure"]
                    or ("none (smoke: never evidence)" if run["class"] == "smoke" else "none"),
                },
            )
            if not ok:
                return stop(
                    "judge %s failed on %s (exit %d); see %s"
                    % (judge["judge_id"], run_dir, code, log_path),
                    EXIT_RUN_FAILED,
                )
            judge_files.append(out_path)
            sys.stdout.write("  OK %s\n" % out_path)

        panel_out = run_dir / PANEL_NAME
        key = "%s__panel" % run_key
        cmd = panel_command(judge_files, family_map_path, run["evaluated_family"], panel_out)
        log_path = log_dir / ("%s.log" % key)
        code, output = run_subprocess(cmd, log_path, repo_root, None)
        ok = code == 0 and panel_out.is_file()
        record = {
            "run_key": key,
            "run_dir": str(run_dir),
            "class": run["class"],
            "evaluated_family": run["evaluated_family"],
            "judges": [j["judge_id"] for j in judges],
            "out": str(panel_out),
            "log": str(log_path),
            "exit_code": code,
            "sha256": sha256_file(panel_out) if panel_out.is_file() else None,
            "status": "completed" if ok else "failed",
            "failure": None if ok else (output[-800:] or "kyra.panel exit %d" % code),
        }
        payload["panel_runs"].append(record)
        append_experiment_row(
            experiments_csv,
            {
                "run": key,
                "class": run["class"],
                "config": "panel over %s; family_map=%s; evaluated_family=%s; "
                "anchors_sha256=%s; gpu=%s; run_dir=%s"
                % (
                    ",".join(j["judge_id"] for j in judges),
                    family_map_path,
                    run["evaluated_family"],
                    anchors_sha or "n/a",
                    gpu["chosen"],
                    run_dir,
                ),
                "seed": "n/a (panel)",
                "command": shell_repr(cmd),
                "raw": str(panel_out),
                "log": str(log_path),
                "marker": (
                    "panel sha256 %s" % record["sha256"]
                    if record["sha256"]
                    else "n/a (no panel file)"
                ),
                "status": record["status"],
                "failure": record["failure"]
                or ("none (smoke: never evidence)" if run["class"] == "smoke" else "none"),
            },
        )
        if not ok:
            return stop(
                "panel failed on %s (exit %d); see %s" % (run_dir, code, log_path),
                EXIT_RUN_FAILED,
            )
        sys.stdout.write("  PANEL %s\n" % panel_out)

    payload["status"] = "completed"
    path = write_campaign_json(out_root, args.cohort, payload, suffix="_scoring")
    sys.stdout.write(
        "SCORING %s completed: %d judge run(s), %d panel(s); record: %s\n"
        % (args.cohort, len(payload["judge_runs"]), len(payload["panel_runs"]), path)
    )
    return EXIT_OK


def print_score_plan(plan: Dict[str, Any], freeze: Dict[str, Any], gpu: Dict[str, Any], stream=None):
    w = (stream or sys.stdout).write
    w("SCORING PLAN cohort=%s\n" % plan["cohort"])
    w("items: %s (sha256=%s)\n" % (plan["items_path"], plan["items_sha256"]))
    w("views: %s (control ids = risk_group CTRL from the items file)\n" % plan["views"])
    w(
        "anchors: %s (sha256=%s)\n"
        % (plan["anchors_path"] or "none", plan["anchors_sha256"] or "n/a")
    )
    w(
        "judges: %s\n"
        % ", ".join("%s/%s (%s)" % (j["judge_id"], j["family"], j["provider"]) for j in plan["judges"])
    )
    for run in plan["runs"]:
        w(
            "RUN %s class=%s (%s) model=%s evaluated_family=%s\n"
            % (run["run_dir"], run["class"], run["class_source"], run["model_id"],
               run["evaluated_family"])
        )
        w("  MARKER sha256=%s\n" % run["marker_sha256"])
        for path in run["judge_files"]:
            w("  judge -> %s%s\n" % (path, "  [EXISTS - refused]" if path in run["existing_judge_files"] else ""))
        w(
            "  items: %d (%d control) - every id present in the items file\n"
            % (run["n_items"], run["n_control_items"])
        )
        w(
            "  panel -> %s%s\n"
            % (run["panel_file"], "  [EXISTS]" if run["panel_exists"] else "")
        )
    if freeze["required"]:
        w("freeze: %s\n" % ("OK sha256=%s" % freeze["sha256"] if freeze["ok"] else "FAIL %s" % freeze["error"]))
    else:
        w("freeze: %s\n" % freeze["error"])
    if not gpu["required"]:
        w("gpu: not required (no vllm judge)\n")
    elif gpu["chosen"] is not None:
        w(
            "gpu: GPU %d via %s (candidates %s%s; GPU %d never used) -> "
            "CUDA_VISIBLE_DEVICES=%d\n"
            % (gpu["chosen"], gpu["source"], gpu["candidates"],
               "; inherited CUDA_VISIBLE_DEVICES=%s" % gpu["inherited_cuda_visible_devices"]
               if gpu["inherited"] else "",
               FORBIDDEN_GPU, gpu["chosen"])
        )
    else:
        w("gpu: FAIL (%s)\n" % (gpu["error"] or "no free GPU among 0-2"))


def build_score_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kyra.campaign score",
        description="Score finished run directories: one judge model at a time, "
        "then the panel; the item file is required so control ids are never lost.",
    )
    p.add_argument("--items", required=True, help="items JSONL (risk_group CTRL = controls)")
    p.add_argument("--models", required=True, help="models.json (evaluated families)")
    p.add_argument("--judges", required=True, help="judges.json")
    p.add_argument("--cohort", required=True, help="cohort name for the scoring record")
    p.add_argument("--runs", nargs="+", required=True, help="run directories or globs")
    p.add_argument("--anchors", default=None, help="judge calibration anchors JSON")
    p.add_argument("--dry-run", action="store_true", help="print the plan only")
    p.add_argument(
        "--allow-panel-overwrite",
        action="store_true",
        help="replace an existing panel.jsonl in a run directory (refused by default)",
    )
    p.add_argument(
        "--class",
        dest="run_class",
        default=None,
        choices=list(RUN_CLASSES),
        help="override the class; default: inherited from each run's EXPERIMENTS row",
    )
    p.add_argument("--out-root", default=None, help="root for the scoring record and logs")
    p.add_argument(
        "--experiments-csv", default="research/EXPERIMENTS.csv", help="EXPERIMENTS.csv to append to"
    )
    p.add_argument(
        "--gpu",
        type=int,
        default=None,
        help="pin this physical GPU instead of choosing the first free one; "
        "refused if it is GPU %d or already carries >= %d MiB"
        % (FORBIDDEN_GPU, GPU_FREE_MAX_USED_MIB),
    )
    p.add_argument("--prereg", default="PREREGISTERED_kyra_v2.yaml", help="frozen preregistration")
    p.add_argument("--sha", default="PREREGISTERED_kyra_v2.yaml.sha256", help="freeze receipt")
    return p


def main(argv: Optional[List[str]] = None, gpu_probe=query_gpus) -> int:
    argv = list(argv) if argv is not None else list(sys.argv[1:])
    if argv and argv[0] == "score":
        return score_main(argv[1:], gpu_probe=gpu_probe)
    args = build_parser().parse_args(argv)
    command = command_string(argv)
    out_root = Path(args.out_root) if args.out_root else Path(DEFAULT_OUT_ROOT)
    out_root_explicit = args.out_root is not None
    items_path = Path(args.items)
    experiments_csv = Path(args.experiments_csv)
    prereg, sha = Path(args.prereg), Path(args.sha)

    try:
        models = load_models(args.models, args.run_class)
        try:
            items = load_items(items_path)
        except ValueError as exc:
            raise CampaignError("could not load items: %s" % exc, EXIT_BAD_INPUT)
        if not items:
            raise CampaignError(
                "zero items loaded from %s - refusing to plan an empty campaign" % items_path,
                EXIT_BAD_INPUT,
            )
    except CampaignError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return exc.code

    plan = build_plan(items, items_path, models, args.cohort, args.run_class, out_root)
    subset_ids = set(plan["subset"]["item_ids"])
    subset_items = [it for it in items if it.item_id in subset_ids]

    preflights = [
        preflight(
            out_root,
            m,
            args.run_class,
            prereg,
            sha,
            gpu_probe=gpu_probe,
            gpu_override=args.gpu,
        )
        for m in models
    ]
    print_plan(plan, preflights)

    payload: Dict[str, Any] = {
        "plan": plan,
        "command": command,
        "dry_run": bool(args.dry_run),
        "experiments_csv": str(experiments_csv),
        "preflight": preflights,
        "runs": [],
        "status": "planned",
        "stopped_because": None,
        "runner_note": (
            "runner.execute_run is called with the run's condition tag (base / "
            "repeat_1..3) and requested temperature, so the manifest carries the "
            "real tag; seed and gpu_memory_utilization are applied when the "
            "provider is constructed, and the manifest's sampling fields report "
            "what the provider says it actually used"
        ),
    }

    refused = [p for p in preflights if not p["ok"]]
    if refused:
        first = refused[0]
        reason = "pre-flight refused for %s" % first["model_id"]
        payload["status"] = "refused"
        payload["stopped_because"] = reason
        path = record_campaign_json(
            out_root, args.cohort, payload, args.dry_run, out_root_explicit
        )
        sys.stderr.write("ERROR: %s\n" % reason)
        for key in ("disk", "gpu", "freeze"):
            if not first[key].get("ok", True):
                sys.stderr.write("  %s: %s\n" % (key, first[key].get("error") or first[key]))
        sys.stderr.write("campaign record: %s\n" % path)
        code = EXIT_FREEZE_MISMATCH if not first["freeze"]["ok"] else EXIT_PREFLIGHT
        return code

    if args.dry_run:
        payload["status"] = "dry-run"
        path = record_campaign_json(
            out_root, args.cohort, payload, True, out_root_explicit
        )
        sys.stdout.write(
            "DRY RUN: nothing executed. campaign record: %s\n"
            % (path if path else "not written (pass --out-root to record the plan; "
               "a dry run never writes into %s)" % DEFAULT_OUT_ROOT)
        )
        return EXIT_OK

    log_dir = out_root / args.cohort / "logs"
    for model, pre in zip(models, preflights):
        gpu_index = pre["gpu"]["chosen"]
        # Pin BEFORE the provider (and therefore any vLLM engine) is built:
        # CUDA reads CUDA_VISIBLE_DEVICES once, at driver initialisation.
        pinned = pin_gpu(gpu_index)
        pre["gpu"]["pinned_cuda_visible_devices"] = pinned
        if pinned is not None:
            sys.stdout.write(
                "GPU: pinned CUDA_VISIBLE_DEVICES=%s (physical GPU %d) for %s\n"
                % (pinned, gpu_index, model["model_id"])
            )
        for spec in next(m for m in plan["models"] if m["model_id"] == model["model_id"])["runs"]:
            spec = dict(spec)
            spec["items_path"] = items_path
            run_items = items if spec["tag"] == "main" else subset_items
            sys.stdout.write(
                "RUN %s / %s: %d item(s) at temperature %.1f (seed %d)\n"
                % (model["model_id"], spec["tag"], len(run_items), spec["temperature"], spec["seed"])
            )
            try:
                record = execute_one_run(
                    model,
                    spec,
                    run_items,
                    args.cohort,
                    args.run_class,
                    out_root,
                    log_dir,
                    gpu_index,
                    command,
                    experiments_csv,
                )
            except CampaignError as exc:
                payload["status"] = "failed"
                payload["stopped_because"] = str(exc)
                path = write_campaign_json(out_root, args.cohort, payload)
                sys.stderr.write("ERROR: %s\ncampaign record: %s\n" % (exc, path))
                return exc.code
            payload["runs"].append(record)
            if record["status"] != "completed":
                payload["status"] = "failed"
                payload["stopped_because"] = "run %s failed: %s" % (
                    record["run_key"],
                    record["failure"],
                )
                path = write_campaign_json(out_root, args.cohort, payload)
                sys.stderr.write(
                    "ERROR: run %s failed (%s); stopping the campaign - no later "
                    "model is started.\n" % (record["run_key"], record["failure"])
                )
                sys.stderr.write("log: %s\ncampaign record: %s\n" % (record["log"], path))
                return EXIT_RUN_FAILED
            sys.stdout.write(
                "  OK MARKER sha256=%s dir=%s\n" % (record["marker_sha256"], record["run_dir"])
            )

    payload["status"] = "completed"
    path = write_campaign_json(out_root, args.cohort, payload)
    sys.stdout.write(
        "CAMPAIGN %s completed: %d run(s); record: %s\n"
        % (args.cohort, len(payload["runs"]), path)
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
