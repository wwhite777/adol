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

CLI (from the repo root):
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
import hashlib
import json
import math
import os
import random
import re
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


def choose_gpu(gpus: Sequence[Dict[str, int]]) -> Optional[int]:
    """First of GPUs 0-2 with < 4 GiB used. GPU 3 is never a candidate."""
    used = {g["index"]: g["used_mib"] for g in gpus}
    for index in ALLOWED_GPUS:
        if index == FORBIDDEN_GPU:
            continue
        if index in used and used[index] < GPU_FREE_MAX_USED_MIB:
            return index
    return None


def preflight(
    out_root: Path,
    model: Dict[str, Any],
    run_class: str,
    prereg: Path,
    sha: Path,
    gpu_probe=query_gpus,
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
    gpus, gpu_error = (None, "not required (provider=%s)" % model["provider"])
    if needs_gpu:
        gpus, gpu_error = gpu_probe()
    chosen = choose_gpu(gpus) if gpus else None
    gpu = {
        "required": needs_gpu,
        "visible": gpus,
        "error": gpu_error if gpus is None else None,
        "chosen": chosen,
        "allowed": list(ALLOWED_GPUS),
        "never": FORBIDDEN_GPU,
        "criterion": "first of GPUs 0-2 with < %d MiB used" % GPU_FREE_MAX_USED_MIB,
        "ok": (not needs_gpu) or chosen is not None,
    }

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
                "  preflight gpu : chose GPU %d (%s; GPU %d never used)\n"
                % (g["chosen"], g["criterion"], FORBIDDEN_GPU)
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
):
    """Write the campaign record, except for a dry run with no explicit out-root.

    A dry run executes nothing, so it must not leave a file in the default data
    root (result/raw). Returns the path written, or None.
    """
    if dry_run and not out_root_explicit:
        return None
    return write_campaign_json(out_root, cohort, payload)


def write_campaign_json(out_root: Path, cohort: str, payload: Dict[str, Any]) -> Path:
    path = out_root / cohort / ("campaign_%s.json" % cohort)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: Optional[List[str]] = None, gpu_probe=query_gpus) -> int:
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
        preflight(out_root, m, args.run_class, prereg, sha, gpu_probe=gpu_probe) for m in models
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
