"""Campaign orchestrator: run the phase-A item set against a list of models.

One model at a time, guarded. For each model, in the order given by models.json:

  1. pre-flight   disk free >= 20 GB at the output root (--min-free-gb lowers or
                  raises that floor, and the override is logged and recorded);
                  the torch.compile/Triton caches pinned inside the project
                  (never /tmp, which cleanup passes delete); a GPU chosen from
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

CLI (from the repo root) - generation (the leading `run` word is optional):
    PYTHONPATH=src python -m kyra.campaign [run] \
        --items research/items/items_phaseA_v1.jsonl \
        --models models.json --cohort phaseA_T1 \
        --class confirmatory|smoke [--dry-run] [--min-free-gb 20] \
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
        [--anchors research/judge_anchors_v1.json] [--dry-run] [--resume] \
        [--allow-panel-overwrite] \
        [--class confirmatory|smoke] [--out-root ...] [--experiments-csv ...]
For every run directory that carries a MARKER: each judge in judges.json is run
as a child process (kyra.judge --views prefix --items <items>, so control ids
come from risk_group CTRL and are never omitted), one judge model loaded at a
time, writing judge_<judge_id>.jsonl into the run dir; an existing judge file is
refused, never overwritten. A judge entry may carry "batch_size": <int >= 1>,
which is passed through as kyra.judge --batch-size (view prompts per provider
call); undeclared, no flag is passed and kyra.judge's own default applies.
A judge entry may also carry "shards": <int >= 1> (default 1). With N > 1 that
judge's pass over a run directory is split across N kyra.judge child processes
started at the same time on the same pinned GPU (--shard k/N, one engine each,
writing judge_<id>.shard<k>of<N>.jsonl), with their ENGINE starts staggered by
--start-delay-s (k-1)*SHARD_START_STAGGER_S so two engines do not probe free GPU
memory in the same second; when all N have finished,
`kyra.judge merge` interleaves them into the single judge_<id>.jsonl, which is
byte-identical to what one engine would have written, and the shard files (with
their sidecars) are moved into <run_dir>/shards/ so that only the merged judge
file is left where the analyses look. A failing shard or a failing merge stops
the batch with the shard files left in place for diagnosis, and a left-over shard
file - in the run directory root or in shards/ - is refused exactly like an
existing judge file.
--resume (a scoring pass that stopped part-way, e.g. one judge's engines failed):
per run directory and judge, an existing judge_<id>.jsonl is REUSED - no
subprocess at all - only when its sidecar judge_<id>.meta.json says it was
produced by exactly this plan: n_views (and the record count) equal to the views
the run has, prompt_template_sha256 = the current kyra.judge template, anchors
and items sha256, batch_size/decode_mode, model_path, and - when this process
exports them - the engine_kwargs / vllm_env in provider_effective_params. Any
difference refuses the whole pass naming the run, the judge and the first field
that differs; nothing is re-run and nothing is overwritten. A judge with no
merged file runs exactly as usual, and the shard files of a failed earlier
attempt are moved to <run_dir>/shards/failed_<stamp>/ first (kept for diagnosis,
never merged); an unmerged shard file lying in the run directory root NEXT TO a
reusable merged file is instead refused by name - nobody can tell whether it is
inside that file, and the analyses would count it as an extra judge. An existing panel.jsonl is reused only when every judge of that
run was reused and it holds one record per view; otherwise the old rule stands
(--allow-panel-overwrite). Without --resume nothing changes: any existing judge
file, shard file or panel is refused as before. The record carries
"resume": true and per-judge "status": "reused"|"completed"|"failed".
Then kyra.panel aggregates that run's judge files
with the family map built from models.json + judges.json and --evaluated-family
= the run's model family, writing panel.jsonl. One EXPERIMENTS row per judge run
and per panel (class inherited from the run's EXPERIMENTS row, or --class); the
freeze hash is verified before any confirmatory scoring. Record:
campaign_<cohort>__<launch_stamp>_scoring.json. Any failure stops the batch.

Every invocation writes its own record file,
campaign_<cohort>__<launch_stamp>[_scoring].json (launch_stamp = UTC
%Y%m%dT%H%MZ plus 6 hex chars, fixed once per process), so two campaigns on the
same cohort can no longer overwrite each other's record.

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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from gates.verify_freeze import FreezeMismatch, verify
from kyra import manifest as mf
from kyra import runner as kyra_runner
from kyra.providers import (
    ENGINE_KWARGS_ENV,
    VLLM_ENV_KEYS,
    get_provider,
    parse_engine_kwargs,
    read_vllm_env,
    validate_chat_template_kwargs,
    validate_stop_token_ids,
)
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


def compact_json(value: Any) -> str:
    """Single-line JSON, stable key order (for plan lines and EXPERIMENTS rows)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def generation_options_suffix(model: Dict[str, Any]) -> str:
    """'; chat_template_kwargs=...; stop_token_ids=...' for the declared ones only.

    Empty string when a model declares neither, so every existing EXPERIMENTS
    row keeps the exact config format it had before these options existed.
    """
    parts = []
    if model.get("chat_template_kwargs") is not None:
        parts.append("chat_template_kwargs=%s" % compact_json(model["chat_template_kwargs"]))
    if model.get("stop_token_ids") is not None:
        parts.append("stop_token_ids=%s" % compact_json(model["stop_token_ids"]))
    return "".join("; " + p for p in parts)


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
        # Optional per-model generation options (hybrid-thinking switch, extra
        # end-of-turn ids). Validated by the provider's own validators, so the
        # model list cannot declare something the provider would refuse later.
        raw_ctk = entry.get("chat_template_kwargs")
        raw_stop = entry.get("stop_token_ids")
        try:
            validate_chat_template_kwargs(raw_ctk)
            validate_stop_token_ids(raw_stop)
        except ValueError as exc:
            raise CampaignError(
                "%s model_id %r: %s" % (where, model_id, exc), EXIT_BAD_INPUT
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
                "chat_template_kwargs": dict(raw_ctk) if raw_ctk is not None else None,
                "stop_token_ids": list(raw_stop) if raw_stop is not None else None,
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


def pin_compile_caches(project_root: Path, environ=os.environ) -> Dict[str, Any]:
    """Point the torch.compile / Triton caches inside the project, not /tmp.

    Reason: the defaults are /tmp/torchinductor_<user> and ~/.triton, which
    cleanup passes delete as "regenerable". Deleting them while an engine is
    compiling kills that engine mid-build (seen 2026-09-22: InductorError /
    FileNotFoundError on .../triton/0/<hash>/triton_.source, the cache directory
    having been re-created in the same second). The values set here never point
    under /tmp; a value already set in the environment is left alone and
    reported as inherited.

    Returns {"TORCHINDUCTOR_CACHE_DIR": v, "TRITON_CACHE_DIR": v,
             "inherited": [names that were already set]}.
    """
    root = Path(project_root)
    defaults = OrderedDict(
        (
            ("TORCHINDUCTOR_CACHE_DIR", root / ".cache" / "torchinductor"),
            ("TRITON_CACHE_DIR", root / ".cache" / "triton"),
        )
    )
    out: Dict[str, Any] = {}
    inherited: List[str] = []
    for name, default in defaults.items():
        current = environ.get(name)
        if current is not None and str(current).strip() != "":
            inherited.append(name)
            out[name] = str(current)
            continue
        default.mkdir(parents=True, exist_ok=True)
        environ[name] = str(default)
        out[name] = str(default)
    out["inherited"] = inherited
    return out


def compile_caches_line(caches: Dict[str, Any]) -> str:
    return "compile caches: TORCHINDUCTOR_CACHE_DIR=%s TRITON_CACHE_DIR=%s (inherited: %s)\n" % (
        caches["TORCHINDUCTOR_CACHE_DIR"],
        caches["TRITON_CACHE_DIR"],
        ",".join(caches["inherited"]) if caches["inherited"] else "none",
    )


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
    min_free_gb: float = MIN_FREE_GB,
) -> Dict[str, Any]:
    """Disk, GPU and freeze checks for one model. Returns a record with ok flags.

    `min_free_gb` is the floor actually applied (--min-free-gb); an override of
    the MIN_FREE_GB default is recorded, never silent.
    """
    free = free_gb(out_root)
    required = float(min_free_gb)
    disk = {
        "path": str(out_root),
        "free_gb": round(free, 2),
        "required_gb": required,
        "min_free_gb_overridden": required != MIN_FREE_GB,
        "default_required_gb": MIN_FREE_GB,
        "ok": free >= required,
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
            "below %.2f GB but not enforced for a smoke run (never evidence)" % required
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
                "chat_template_kwargs": m.get("chat_template_kwargs"),
                "stop_token_ids": m.get("stop_token_ids"),
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
        if model.get("chat_template_kwargs") is not None:
            w("  chat_template_kwargs: %s\n" % compact_json(model["chat_template_kwargs"]))
        if model.get("stop_token_ids") is not None:
            w("  stop_token_ids: %s\n" % compact_json(model["stop_token_ids"]))
        for r in model["runs"]:
            w(
                "  run %-9s temperature=%.1f seed=%d items=%d (%s)\n"
                % (r["tag"], r["temperature"], r["seed"], r["n_items"], r["item_scope"])
            )
        d = pre["disk"]
        w(
            "  preflight disk: free %.2f GB / required %.2f GB -> %s%s%s\n"
            % (d["free_gb"], d["required_gb"], "OK" if d["ok"] else "FAIL",
               "" if d["ok"] or d["enforced"] else " (not enforced for smoke)",
               " [min_free_gb_overridden=True: --min-free-gb %.2f replaces the "
               "%.2f GB default]" % (d["required_gb"], d.get("default_required_gb", MIN_FREE_GB))
               if d.get("min_free_gb_overridden") else "")
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
        if model.get("chat_template_kwargs") is not None:
            opts["chat_template_kwargs"] = model["chat_template_kwargs"]
        if model.get("stop_token_ids") is not None:
            opts["stop_token_ids"] = model["stop_token_ids"]
        return get_provider("vllm", **opts)
    if model.get("chat_template_kwargs") is not None or model.get("stop_token_ids") is not None:
        sys.stderr.write(
            "WARNING: %s declares chat_template_kwargs/stop_token_ids, which the "
            "%r provider ignores\n" % (model["model_id"], model["provider"])
        )
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
        + generation_options_suffix(model)
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
    p.add_argument(
        "--min-free-gb",
        type=float,
        default=MIN_FREE_GB,
        help="disk floor for the pre-flight in GB (default %.0f); a different "
        "value is recorded as min_free_gb_overridden in the record and the plan"
        % MIN_FREE_GB,
    )
    p.add_argument("--prereg", default="PREREGISTERED_kyra_v2.yaml", help="frozen preregistration")
    p.add_argument("--sha", default="PREREGISTERED_kyra_v2.yaml.sha256", help="freeze receipt")
    return p


def command_string(argv: Optional[List[str]]) -> str:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    return "PYTHONPATH=src python -m kyra.campaign " + " ".join(args)


_LAUNCH_STAMP: Optional[str] = None


def new_launch_stamp() -> str:
    """A stamp in the run-id style: UTC %Y%m%dT%H%MZ + '-' + 6 hex chars."""
    return kyra_runner.make_run_id("campaign-launch", "pid-%d" % os.getpid())


def set_launch_stamp(value: Optional[str] = None) -> str:
    """Fix this process's launch stamp (called once at CLI entry)."""
    global _LAUNCH_STAMP
    _LAUNCH_STAMP = value or new_launch_stamp()
    return _LAUNCH_STAMP


def launch_stamp() -> str:
    """The launch stamp of this invocation; generated on first use if unset."""
    return _LAUNCH_STAMP or set_launch_stamp()


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
    """Write this invocation's record: campaign_<cohort>__<launch_stamp><suffix>.json.

    The stamp is fixed per process, so every call of one invocation rewrites the
    same file while two concurrent campaigns on the same cohort can no longer
    overwrite each other's record.
    """
    stamp = launch_stamp()
    path = out_root / cohort / ("campaign_%s__%s%s.json" % (cohort, stamp, suffix))
    payload["launch_stamp"] = stamp
    payload["record_path"] = str(path)
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
        # Optional batched judge decoding. Undeclared -> the flag is not passed
        # at all and kyra.judge's own default applies, so an existing judges.json
        # keeps the exact command it had before this option existed.
        batch_size = entry.get("batch_size")
        if batch_size is not None and (
            isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1
        ):
            raise CampaignError(
                "%s batch_size must be an int >= 1" % where, EXIT_BAD_INPUT
            )
        # Optional sharded judging: N concurrent engines for this judge on one
        # GPU, merged back into one judge file. Undeclared (or 1) -> exactly the
        # single child process, argv and records this judge had before.
        shards = entry.get("shards")
        if shards is not None and (
            isinstance(shards, bool) or not isinstance(shards, int) or shards < 1
        ):
            raise CampaignError("%s shards must be an int >= 1" % where, EXIT_BAD_INPUT)
        judges.append(
            {
                "judge_id": judge_id,
                "model_id": model_id or judge_id,
                "model_path": model_path,
                "family": family,
                "provider": provider,
                "gpu_memory_utilization": float(gpu_util) if gpu_util is not None else None,
                "batch_size": int(batch_size) if batch_size is not None else None,
                "shards": int(shards) if shards is not None else 1,
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


SHARDS_DIR_NAME = "shards"
# Seconds between the starts of two shards of one judge (2026-09-23). Shard k
# gets --start-delay-s (k-1)*STAGGER, so the engines do not probe free GPU memory
# in the same second - the collision that recorded the first views of two shards
# as ProviderError. The children still run concurrently; only their starts are
# spread.
SHARD_START_STAGGER_S = 45


def shard_out_path(run_dir: Path, judge_id: str, k: int, n: int) -> Path:
    """Where shard k of n writes: judge_<id>.shard<k>of<n>.jsonl in the run dir."""
    return Path(run_dir) / ("judge_%s.shard%dof%d.jsonl" % (judge_id, k, n))


def shards_dir(run_dir: Path) -> Path:
    """<run_dir>/shards: where a judge's shard files go once they are merged."""
    return Path(run_dir) / SHARDS_DIR_NAME


def existing_shard_artifacts(run_dir: Path, judge_id: str) -> List[Path]:
    """Every shard file of this judge already on disk - run dir root and shards/.

    A left-over shard, merged or not, is refused like a left-over judge file: the
    merge must never mix a record from an earlier attempt into a new judge file.
    """
    root = sorted(Path(run_dir).glob("judge_%s.shard*.jsonl" % judge_id))
    stored = sorted(shards_dir(run_dir).glob("judge_%s.shard*.jsonl" % judge_id))
    return root + stored


def archive_shard_files(run_dir: Path, shard_files: Sequence[Path]) -> List[Path]:
    """Move merged shard files and their sidecars into <run_dir>/shards/.

    Called only after the merge succeeded: the run directory root then holds one
    judge_<id>.jsonl per judge and nothing that looks like one (kyra.panel is
    given explicit paths, but kyra.analysis.n3_reliability globs the root and a
    shard file there would count as an extra judge). A failed merge leaves every
    shard where it is, for diagnosis. Returns the new paths, in input order.
    """
    from kyra.judge import meta_path_for  # one source of truth for the sidecar name

    target = shards_dir(run_dir)
    target.mkdir(parents=True, exist_ok=True)
    moved: List[Path] = []
    for shard in shard_files:
        shard = Path(shard)
        for path in (shard, meta_path_for(shard)):
            if path.is_file():
                shutil.move(str(path), str(target / path.name))
        moved.append(target / shard.name)
    return moved


# --------------------------------------------------------------------------
# resume: reuse a judge output only when its provenance IS the current plan
# --------------------------------------------------------------------------
FAILED_SHARDS_PREFIX = "failed_"


def failed_shards_dir(run_dir: Path, stamp: Optional[str] = None) -> Path:
    """<run_dir>/shards/failed_<stamp>: where a failed attempt's shards are kept."""
    value = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return shards_dir(run_dir) / (FAILED_SHARDS_PREFIX + value)


def archive_failed_shard_files(
    run_dir: Path, shard_files: Sequence[Path], stamp: Optional[str] = None
) -> Tuple[Path, List[Path]]:
    """Move the shards of a FAILED attempt (no merged judge file) out of the way.

    --resume must not merge a record from a crashed attempt into a new judge
    file, and deleting the evidence would make the crash undiagnosable, so the
    stray shard files (and their sidecars) are moved to
    <run_dir>/shards/failed_<stamp>/ and the judge is then run normally. The
    directory is nested one level below shards/, which existing_shard_artifacts
    does not glob, so a later pass never sees them again.
    Returns (target_dir, new paths in input order).
    """
    from kyra.judge import meta_path_for  # one source of truth for the sidecar name

    target = failed_shards_dir(run_dir, stamp)
    target.mkdir(parents=True, exist_ok=True)
    moved: List[Path] = []
    for shard in shard_files:
        shard = Path(shard)
        for path in (shard, meta_path_for(shard)):
            if path.is_file():
                shutil.move(str(path), str(target / path.name))
        moved.append(target / shard.name)
    return target, moved


def expected_view_count(run_dir, views: str = JUDGE_VIEWS) -> int:
    """How many views a judge must have written for this run directory.

    Built by kyra.judge.ordered_view_keys, i.e. the very task list judge_run and
    `kyra.judge merge` build from responses.jsonl and the view mode - never a
    second definition of "how many records should be there".
    """
    from kyra.judge import ordered_view_keys

    try:
        return len(ordered_view_keys(run_dir, views))
    except (OSError, ValueError) as exc:
        raise CampaignError(
            "refusing to resume %s: cannot count its views (%s)" % (run_dir, exc),
            EXIT_PREFLIGHT,
        )


def count_jsonl_records(path) -> int:
    """Non-empty lines of a JSONL file (0 when it does not exist)."""
    p = Path(path)
    if not p.is_file():
        return 0
    with p.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def current_engine_env(environ=None) -> Dict[str, Any]:
    """The engine knobs this process exports, parsed as providers.py parses them.

    {"engine_kwargs": {...} | None, "vllm_env": {...} | None}; None means "this
    process does not export it", and --resume then does not compare that field -
    an unset variable says nothing about how the existing output was decoded.
    """
    env = os.environ if environ is None else environ
    out: Dict[str, Any] = {"engine_kwargs": None, "vllm_env": None}
    if env.get(ENGINE_KWARGS_ENV) is not None:
        out["engine_kwargs"] = parse_engine_kwargs(env.get(ENGINE_KWARGS_ENV))
    if any(env.get(name) is not None for name in VLLM_ENV_KEYS):
        out["vllm_env"] = read_vllm_env(env)
    return out


def judge_batch_size(judge: Dict[str, Any]) -> int:
    """The batch size this judge is configured with (undeclared -> judge default)."""
    from kyra.judge import DEFAULT_BATCH_SIZE

    declared = judge.get("batch_size")
    return int(declared) if declared is not None else int(DEFAULT_BATCH_SIZE)


def judge_decode_mode(batch_size: int) -> str:
    from kyra.judge import DECODE_BATCHED, DECODE_SEQUENTIAL

    return DECODE_SEQUENTIAL if int(batch_size) == 1 else DECODE_BATCHED


def judge_model_path(judge: Dict[str, Any]) -> Optional[str]:
    """What kyra.judge records as model_path for this judge.

    judge_command passes --model-path only for provider vllm, and the sidecar
    records exactly the flag's value, so a fake/mock judge's sidecar says null.
    """
    return str(judge["model_path"]) if judge["provider"] == "vllm" else None


def prompt_template_sha256() -> str:
    """sha256 of the judge prompt template kyra.judge would use right now."""
    from kyra.judge import PROMPT_PATH

    if not Path(PROMPT_PATH).is_file():
        raise CampaignError(
            "judge prompt template not found: %s" % PROMPT_PATH, EXIT_BAD_INPUT
        )
    return sha256_file(PROMPT_PATH)


def judge_provenance_mismatch(
    judge: Dict[str, Any],
    meta: Dict[str, Any],
    n_views_expected: int,
    n_records: int,
    template_sha: str,
    anchors_sha: Optional[str],
    items_sha: Optional[str],
    engine_env: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """The FIRST field in which an existing judge output differs from this plan.

    Returns None only when the existing file was produced by the same protocol
    this pass would run: the same prompt template, anchors, item file, model,
    batch size / decode mode and engine knobs, and it holds every view of the
    run. Otherwise {"field", "expected", "found"} - reusing such a file would
    mix two protocols inside one panel with nothing downstream able to see it.
    """
    checks: List[Tuple[str, Any, Any]] = [
        ("n_views", n_views_expected, meta.get("n_views")),
        ("records", n_views_expected, n_records),
        ("prompt_template_sha256", template_sha, meta.get("prompt_template_sha256")),
        ("anchors_sha256", anchors_sha, meta.get("anchors_sha256")),
    ]
    # items_sha256 is compared only when the sidecar recorded one: a judge run
    # without --items has null there and that is not a disagreement.
    if meta.get("items_sha256") is not None:
        checks.append(("items_sha256", items_sha, meta.get("items_sha256")))
    batch_size = judge_batch_size(judge)
    checks.append(("batch_size", batch_size, meta.get("batch_size")))
    checks.append(("decode_mode", judge_decode_mode(batch_size), meta.get("decode_mode")))
    checks.append(("model_path", judge_model_path(judge), meta.get("model_path")))
    params = meta.get("provider_effective_params") or {}
    for field in ("engine_kwargs", "vllm_env"):
        if engine_env.get(field) is not None:
            checks.append(
                ("provider_effective_params.%s" % field, engine_env[field], params.get(field))
            )
    for field, expected, found in checks:
        if found != expected:
            return {"field": field, "expected": expected, "found": found}
    return None


def root_shard_artifacts(run_dir: Path, judge_id: str) -> List[Path]:
    """Shard files of this judge in the run directory ROOT (not in shards/).

    Both the records and the sidecars: judge_<id>.shard<k>of<n>.jsonl matches the
    judge_*.jsonl glob kyra.analysis.n3_reliability uses, so an unmerged shard
    beside a merged judge file would count as an extra judge.
    """
    return sorted(Path(run_dir).glob("judge_%s.shard*.jsonl" % judge_id)) + sorted(
        Path(run_dir).glob("judge_%s.shard*%s" % (judge_id, ".meta.json"))
    )


def plan_judge_resume(
    run_dir: Path,
    judge: Dict[str, Any],
    out_path: Path,
    n_views_expected: int,
    template_sha: str,
    anchors_sha: Optional[str],
    items_sha: Optional[str],
    engine_env: Dict[str, Any],
) -> Dict[str, Any]:
    """What --resume does with one judge on one run: reuse, run, or refuse.

    action "reuse": the merged judge file and its sidecar are there, complete and
    provenance-identical - no subprocess runs. action "run": no merged judge file
    (any stray shard file of a failed attempt is listed for archiving). action
    "refuse": output is there but is NOT this plan's output, or an unmerged shard
    file of the same judge still sits in the run directory root; "mismatch" names
    the first field (or that file), and the whole pass stops.
    """
    from kyra.judge import meta_path_for

    judge_id = judge["judge_id"]
    out_path = Path(out_path)
    meta_path = meta_path_for(out_path)
    decision: Dict[str, Any] = {
        "judge_id": judge_id,
        "judge_file": str(out_path),
        "meta_file": str(meta_path),
        "n_views_expected": n_views_expected,
        "stray_shard_files": [],
        "mismatch": None,
    }
    if not out_path.is_file():
        decision["action"] = "run"
        decision["stray_shard_files"] = [
            str(p) for p in existing_shard_artifacts(run_dir, judge_id)
        ]
        return decision
    # A merged judge file with a shard file of the same judge still lying in the
    # run directory root is an inconsistent state: nobody can tell whether the
    # merged file contains that shard, and kyra.analysis.n3_reliability would
    # count the shard as an extra judge. It is never archived automatically here
    # (that would hide the inconsistency) - the pass stops naming the file.
    # Shard files already archived under <run_dir>/shards/ are fine.
    root_shards = root_shard_artifacts(run_dir, judge_id)
    if root_shards:
        decision["action"] = "refuse"
        decision["root_shard_files"] = [str(p) for p in root_shards]
        decision["mismatch"] = {
            "field": "root_shard_file",
            "expected": "no judge_%s.shard* file in the run directory root "
            "(archived shards live in %s/)" % (judge_id, SHARDS_DIR_NAME),
            "found": str(root_shards[0]),
        }
        return decision
    if not meta_path.is_file():
        decision["action"] = "refuse"
        decision["mismatch"] = {
            "field": "sidecar",
            "expected": "a %s sidecar next to the judge file" % meta_path.name,
            "found": None,
        }
        return decision
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError("sidecar is not a JSON object")
    except (OSError, ValueError) as exc:
        decision["action"] = "refuse"
        decision["mismatch"] = {
            "field": "sidecar",
            "expected": "a readable JSON sidecar",
            "found": str(exc),
        }
        return decision
    n_records = count_jsonl_records(out_path)
    mismatch = judge_provenance_mismatch(
        judge, meta, n_views_expected, n_records, template_sha, anchors_sha,
        items_sha, engine_env,
    )
    if mismatch is not None:
        decision["action"] = "refuse"
        decision["mismatch"] = mismatch
        return decision
    decision["action"] = "reuse"
    decision["n_records"] = n_records
    decision["sha256"] = sha256_file(out_path)
    decision["meta_sha256"] = sha256_file(meta_path)
    return decision


def resume_refusal_message(run: Dict[str, Any], decision: Dict[str, Any]) -> str:
    """The refusal a mismatching --resume prints: run dir, judge, first field."""
    mismatch = decision["mismatch"]
    return (
        "--resume refused: %s judge %s has existing output whose %s does not match "
        "this pass (plan %r, existing %r); nothing was run and nothing was "
        "overwritten" % (
            run["run_dir"], decision["judge_id"], mismatch["field"],
            mismatch["expected"], mismatch["found"],
        )
    )


def judge_command(
    judge: Dict[str, Any],
    run_dir: Path,
    items_path: Path,
    out_path: Path,
    anchors: Optional[Path],
    shard: Optional[Tuple[int, int]] = None,
) -> List[str]:
    """The kyra.judge argv for one judge on one run (views=prefix, items given).

    shard=(k, n) with n > 1 appends --shard k/n and --start-delay-s
    (k-1)*SHARD_START_STAGGER_S: this child judges only that slice of the run's
    views, and waits its turn before building its engine. shard=None (or n == 1)
    is the unsharded argv, which is exactly the argv this function produced before
    sharding existed - no delay flag at all.
    """
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
    if judge.get("batch_size") is not None:
        cmd += ["--batch-size", str(judge["batch_size"])]
    if shard is not None and int(shard[1]) > 1:
        cmd += ["--shard", "%d/%d" % (int(shard[0]), int(shard[1]))]
        cmd += ["--start-delay-s", str((int(shard[0]) - 1) * SHARD_START_STAGGER_S)]
    if judge["provider"] == "fake" and judge.get("fake_outputs"):
        cmd += ["--fake-outputs", str(judge["fake_outputs"])]
    if anchors is not None:
        cmd += ["--anchors", str(anchors)]
    return cmd


def judge_merge_command(
    run_dir: Path, shard_files: Sequence[Path], out_path: Path
) -> List[str]:
    """`kyra.judge merge`: the shard files of one judge back into one judge file."""
    return (
        [
            sys.executable,
            "-m",
            "kyra.judge",
            "merge",
            "--run-dir",
            str(run_dir),
            "--views",
            JUDGE_VIEWS,
            "--shards",
        ]
        + [str(p) for p in shard_files]
        + ["--out", str(out_path)]
    )


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


def run_subprocesses(
    cmds: Sequence[Sequence[str]],
    log_paths: Sequence[Path],
    repo_root: Path,
    gpu: Optional[int],
) -> List[Tuple[int, str]]:
    """Run several child processes at the same time; results keep the input order.

    One thread per child, each blocking in run_subprocess, so every child gets its
    own log file and its own drained pipes. Used for the shards of one judge: they
    share the pinned GPU on purpose (two engines at gpu_memory_utilization ~0.42
    fit on one 46 GB card), and the batch may not continue until all of them have
    finished.
    """
    if len(cmds) != len(log_paths):
        raise ValueError("run_subprocesses needs one log path per command")
    if len(cmds) == 1:
        return [run_subprocess(cmds[0], log_paths[0], repo_root, gpu)]
    with ThreadPoolExecutor(max_workers=len(cmds)) as pool:
        futures = [
            pool.submit(run_subprocess, cmd, log_path, repo_root, gpu)
            for cmd, log_path in zip(cmds, log_paths)
        ]
        return [f.result() for f in futures]


def run_one_judge(
    judge: Dict[str, Any],
    run_dir: Path,
    items_path: Path,
    out_path: Path,
    anchors_path: Optional[Path],
    key: str,
    log_dir: Path,
    repo_root: Path,
    gpu_index: Optional[int],
) -> Dict[str, Any]:
    """Score one run dir with one judge, sharded or not.

    shards == 1: one kyra.judge child, exactly as before.
    shards == N > 1: N kyra.judge children started together (--shard k/N, one
    file each), then `kyra.judge merge` into out_path. A failing shard means the
    merge is not attempted and the shard files stay on disk for diagnosis; a
    successful merge moves them (and their sidecars) into <run_dir>/shards/, so
    the run directory root holds only the merged judge file.

    Returns {code, output, log, shard_files, shard_logs, command_cell}: code 0
    only when every child and the merge succeeded. shard_files are the paths the
    artifacts ended up at (<run_dir>/shards/ after a merge, the run directory
    root otherwise).
    """
    n_shards = int(judge.get("shards") or 1)
    log_path = log_dir / ("%s.log" % key)
    if n_shards == 1:
        cmd = judge_command(judge, run_dir, items_path, out_path, anchors_path)
        code, output = run_subprocess(cmd, log_path, repo_root, gpu_index)
        return {
            "code": code,
            "output": output,
            "log": log_path,
            "shard_files": [],
            "shard_logs": [],
            "command_cell": shell_repr(cmd),
        }

    shard_files = [
        shard_out_path(run_dir, judge["judge_id"], k, n_shards)
        for k in range(1, n_shards + 1)
    ]
    shard_logs = [
        log_dir / ("%s.shard%dof%d.log" % (key, k, n_shards))
        for k in range(1, n_shards + 1)
    ]
    cmds = [
        judge_command(judge, run_dir, items_path, shard_files[k - 1], anchors_path,
                      shard=(k, n_shards))
        for k in range(1, n_shards + 1)
    ]
    merge_cmd = judge_merge_command(run_dir, shard_files, out_path)
    command_cell = "\n".join([shell_repr(c) for c in cmds] + [shell_repr(merge_cmd)])
    results = run_subprocesses(cmds, shard_logs, repo_root, gpu_index)
    failed = [
        (k, results[k - 1], shard_logs[k - 1])
        for k in range(1, n_shards + 1)
        if results[k - 1][0] != 0 or not shard_files[k - 1].is_file()
    ]
    if failed:
        k, (code, output), failed_log = failed[0]
        return {
            "code": code or 1,
            "output": "shard %d/%d failed: %s" % (k, n_shards, output),
            "log": failed_log,
            "shard_files": shard_files,
            "shard_logs": shard_logs,
            "command_cell": command_cell,
        }
    code, output = run_subprocess(merge_cmd, log_path, repo_root, None)
    merged = code == 0 and Path(out_path).is_file()
    return {
        "code": code,
        "output": output,
        "log": log_path,
        # after a successful merge the shards live in <run_dir>/shards/
        "shard_files": archive_shard_files(run_dir, shard_files) if merged else shard_files,
        "shard_logs": shard_logs,
        "command_cell": command_cell,
    }


def score_main(argv: List[str], gpu_probe=query_gpus) -> int:
    """`kyra.campaign score ...`: judges then panel over finished run dirs."""
    parser = build_score_parser()
    args = parser.parse_args(argv)
    command = "PYTHONPATH=src python -m kyra.campaign score " + " ".join(
        shlex.quote(a) for a in argv
    )
    repo_root = Path(__file__).resolve().parents[2]
    # Before any GPU selection/pinning and before any judge engine is built.
    caches = pin_compile_caches(repo_root)
    sys.stdout.write(compile_caches_line(caches))
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

    # --resume compares the existing outputs against THIS plan; the template and
    # the engine knobs are read once, before any run directory is inspected.
    try:
        template_sha = prompt_template_sha256() if args.resume else None
        engine_env = current_engine_env() if args.resume else {}
    except CampaignError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return exc.code
    except ValueError as exc:  # a malformed KYRA_VLLM_ENGINE_KWARGS
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT

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
            dict(
                {k: j[k] for k in ("judge_id", "family", "provider", "model_id", "notes")},
                # only when declared: an undeclared judge entry keeps its old shape
                **({"batch_size": j["batch_size"]} if j.get("batch_size") is not None else {}),
                **({"shards": j["shards"]} if j.get("shards", 1) > 1 else {}),
            )
            for j in judges
        ],
        "family_map": family_map,
        "model_families": model_families,
        "out_root": str(out_root),
        "runs": [],
    }
    # Only when some judge is actually sharded, so an unsharded scoring record
    # keeps the exact shape it had before the stagger existed.
    if any(j["shards"] > 1 for j in judges):
        plan["shard_start_stagger_s"] = SHARD_START_STAGGER_S
    # Only under --resume, so a normal scoring record keeps its exact shape.
    if args.resume:
        plan["resume"] = True
        plan["prompt_template_sha256"] = template_sha
        plan["engine_env"] = engine_env

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
            # A left-over shard file is refused like a left-over judge file: the
            # merge would otherwise pick up records from an earlier attempt. Both
            # the run directory root and <run_dir>/shards/ (where a finished merge
            # moves them) are searched, for every judge that asks for shards.
            shard_files = [
                shard_out_path(Path(run_dir), j["judge_id"], k, j["shards"])
                for j in judges
                if j["shards"] > 1
                for k in range(1, j["shards"] + 1)
            ]
            left_over_shards = [
                p
                for j in judges
                if j["shards"] > 1
                for p in existing_shard_artifacts(Path(run_dir), j["judge_id"])
            ]
            existing = [str(p) for p in judge_files if p.exists()] + [
                str(p) for p in left_over_shards
            ]
            panel_file = Path(run_dir) / PANEL_NAME
            # --resume: per judge, reuse / run / refuse instead of one blanket
            # refusal. Nothing is moved or written here - a --dry-run must stay a
            # dry run; the archiving of a failed attempt's shards happens in the
            # execution phase.
            resume_plan: List[Dict[str, Any]] = []
            panel_reuse = False
            if args.resume:
                n_views_expected = expected_view_count(Path(run_dir))
                resume_plan = [
                    plan_judge_resume(
                        Path(run_dir), judge, out_path, n_views_expected,
                        template_sha, anchors_sha, plan["items_sha256"], engine_env,
                    )
                    for judge, out_path in zip(judges, judge_files)
                ]
                # Existing outputs are no longer a blanket refusal: a reused file
                # is kept, a missing one is run, a mismatching one stops the pass
                # (checked with the other refusals, below).
                existing = []
                panel_reuse = (
                    panel_file.exists()
                    and bool(resume_plan)
                    and all(d["action"] == "reuse" for d in resume_plan)
                    and count_jsonl_records(panel_file) == n_views_expected
                )
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
                    "shard_files": [str(p) for p in shard_files],
                    "existing_judge_files": existing,
                    "panel_file": str(panel_file),
                    "panel_exists": panel_file.exists(),
                    **(
                        {
                            "resume_judges": resume_plan,
                            "reused_judge_files": [
                                d["judge_file"] for d in resume_plan if d["action"] == "reuse"
                            ],
                            "panel_reuse": panel_reuse,
                            "n_views_expected": n_views_expected,
                        }
                        if args.resume
                        else {}
                    ),
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
        "resume": bool(args.resume),
        "experiments_csv": str(experiments_csv),
        "compile_caches": caches,
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
        r
        for r in plan["runs"]
        if r["panel_exists"]
        and not args.allow_panel_overwrite
        and not r.get("panel_reuse")
    ]
    # An existing output that is NOT this plan's output stops everything, naming
    # the run, the judge and the first field that differs.
    resume_blocked = [
        (r, d)
        for r in plan["runs"]
        for d in r.get("resume_judges", [])
        if d["action"] == "refuse"
    ]
    if resume_blocked:
        run, decision = resume_blocked[0]
        reason = resume_refusal_message(run, decision)
        payload["status"] = "refused"
        payload["stopped_because"] = reason
        path = record_campaign_json(
            out_root, args.cohort, payload, args.dry_run, out_root_explicit, suffix="_scoring"
        )
        sys.stderr.write("ERROR: %s\ncampaign record: %s\n" % (reason, path))
        return EXIT_PREFLIGHT
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

    def judge_config_cell(judge: Dict[str, Any], run: Dict[str, Any], run_dir: Path,
                          n_shards: int) -> str:
        """The EXPERIMENTS config cell of one judge on one run.

        The same string whether the judge ran now or is being reused: the config
        IS the protocol, and a reused row must be comparable to the row the
        original pass wrote. What the judge did instead sits in `status`.
        """
        return (
            "judge=%s; family=%s; provider=%s; model=%s; views=%s; "
            "items=%s; anchors=%s; anchors_sha256=%s; evaluated_family=%s; "
            "gpu=%s; run_dir=%s%s%s"
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
                # appended only when the judge declares it, so an undeclared
                # judge keeps the exact previous config string
                "; batch_size=%d" % judge["batch_size"]
                if judge.get("batch_size") is not None
                else "",
                # same rule: a single-engine judge run says nothing new
                "; shards=%d" % n_shards if n_shards > 1 else "",
            )
        )

    for run in plan["runs"]:
        run_dir = Path(run["run_dir"])
        run_key = "%s__%s" % (args.cohort, run_dir.name)
        judge_files: List[Path] = []
        decisions = {d["judge_id"]: d for d in run.get("resume_judges", [])}
        for judge in judges:  # one judge model loaded at a time
            out_path = run_dir / ("judge_%s.jsonl" % judge["judge_id"])
            key = "%s__judge_%s" % (run_key, judge["judge_id"])
            n_shards = judge["shards"]
            decision = decisions.get(judge["judge_id"])
            if decision is not None and decision["action"] == "reuse":
                # Provenance-identical and complete: no engine, no subprocess,
                # no write into the run directory - the existing file IS this
                # pass's output for that judge.
                record = {
                    "run_key": key,
                    "run_dir": str(run_dir),
                    "judge_id": judge["judge_id"],
                    "family": judge["family"],
                    "provider": judge["provider"],
                    "class": run["class"],
                    "out": str(out_path),
                    "log": decision["meta_file"],
                    "shards": n_shards,
                    "shard_files": [],
                    "shard_logs": [],
                    "exit_code": None,
                    "sha256": decision["sha256"],
                    "meta_sha256": decision["meta_sha256"],
                    "n_views": decision["n_views_expected"],
                    "status": "reused",
                    "failure": None,
                    "anchors_sha256": anchors_sha,
                }
                payload["judge_runs"].append(record)
                append_experiment_row(
                    experiments_csv,
                    {
                        "run": key,
                        "class": run["class"],
                        "config": judge_config_cell(judge, run, run_dir, n_shards),
                        "seed": "n/a (judge)",
                        "command": "n/a (--resume: existing judge output reused, "
                        "no subprocess)",
                        "raw": str(out_path),
                        "log": decision["meta_file"],
                        "marker": "judge_file sha256 %s (reused; sidecar sha256 %s)"
                        % (record["sha256"], record["meta_sha256"]),
                        "status": "reused",
                        "failure": "none (reused: sidecar provenance matches this pass)",
                    },
                )
                judge_files.append(out_path)
                sys.stdout.write(
                    "JUDGE %s on %s: REUSED %s (%d views, sha256 %s)\n"
                    % (judge["judge_id"], run_dir, out_path,
                       decision["n_views_expected"], record["sha256"])
                )
                continue
            if decision is not None and decision["stray_shard_files"]:
                # A failed sharded attempt left shard files behind. They are
                # evidence, so they are moved aside rather than deleted, and the
                # judge then runs from scratch.
                target, moved = archive_failed_shard_files(
                    run_dir, [Path(p) for p in decision["stray_shard_files"]]
                )
                decision["archived_shard_files"] = [str(p) for p in moved]
                decision["archived_to"] = str(target)
                sys.stdout.write(
                    "  archived %d stray shard file(s) of judge %s to %s "
                    "(failed earlier attempt, kept for diagnosis)\n"
                    % (len(moved), judge["judge_id"], target)
                )
            sys.stdout.write(
                "JUDGE %s on %s%s\n"
                % (judge["judge_id"], run_dir,
                   "" if n_shards == 1 else " (%d concurrent shards)" % n_shards)
            )
            outcome = run_one_judge(
                judge, run_dir, items_path, out_path, anchors_path, key, log_dir,
                repo_root, gpu["chosen"],
            )
            code, output, log_path = outcome["code"], outcome["output"], outcome["log"]
            cmd = outcome["command_cell"]
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
                "shards": n_shards,
                "shard_files": [str(p) for p in outcome["shard_files"]],
                "shard_logs": [str(p) for p in outcome["shard_logs"]],
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
                    "config": judge_config_cell(judge, run, run_dir, n_shards),
                    "seed": "n/a (judge)",
                    # sharded: the N shard commands and the merge command, one
                    # per line inside the (quoted) CSV cell
                    "command": cmd,
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
        panel_config = "panel over %s; family_map=%s; evaluated_family=%s; " \
            "anchors_sha256=%s; gpu=%s; run_dir=%s" % (
                ",".join(j["judge_id"] for j in judges),
                family_map_path,
                run["evaluated_family"],
                anchors_sha or "n/a",
                gpu["chosen"],
                run_dir,
            )
        if run.get("panel_reuse"):
            # Every judge of this run was reused and the panel already holds one
            # record per view: rebuilding it from the same inputs would only
            # rewrite the same file, so it is reused too.
            record = {
                "run_key": key,
                "run_dir": str(run_dir),
                "class": run["class"],
                "evaluated_family": run["evaluated_family"],
                "judges": [j["judge_id"] for j in judges],
                "out": str(panel_out),
                "log": None,
                "exit_code": None,
                "sha256": sha256_file(panel_out),
                "n_records": count_jsonl_records(panel_out),
                "status": "reused",
                "failure": None,
            }
            payload["panel_runs"].append(record)
            append_experiment_row(
                experiments_csv,
                {
                    "run": key,
                    "class": run["class"],
                    "config": panel_config,
                    "seed": "n/a (panel)",
                    "command": "n/a (--resume: existing panel reused, no subprocess)",
                    "raw": str(panel_out),
                    "log": "n/a (--resume: no subprocess)",
                    "marker": "panel sha256 %s (reused; %d records)"
                    % (record["sha256"], record["n_records"]),
                    "status": "reused",
                    "failure": "none (reused: every judge of this run was reused)",
                },
            )
            sys.stdout.write("  PANEL REUSED %s\n" % panel_out)
            continue
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
                "config": panel_config,
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
    reused = sum(1 for r in payload["judge_runs"] if r["status"] == "reused")
    sys.stdout.write(
        "SCORING %s completed: %d judge run(s)%s, %d panel(s); record: %s\n"
        % (
            args.cohort,
            len(payload["judge_runs"]),
            # only when something was reused, so a normal pass prints the exact
            # line it printed before --resume existed
            " (%d reused)" % reused if reused else "",
            len(payload["panel_runs"]),
            path,
        )
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
        % ", ".join(
            "%s/%s (%s%s)"
            % (j["judge_id"], j["family"], j["provider"],
               ", %d shards" % j["shards"] if j.get("shards", 1) > 1 else "")
            for j in plan["judges"]
        )
    )
    if plan.get("resume"):
        w(
            "resume: on (prompt_template_sha256=%s, engine_kwargs=%s, vllm_env=%s)\n"
            % (
                plan.get("prompt_template_sha256"),
                compact_json(plan["engine_env"]["engine_kwargs"])
                if plan.get("engine_env", {}).get("engine_kwargs") is not None
                else "not exported (not compared)",
                compact_json(plan["engine_env"]["vllm_env"])
                if plan.get("engine_env", {}).get("vllm_env") is not None
                else "not exported (not compared)",
            )
        )
    for run in plan["runs"]:
        w(
            "RUN %s class=%s (%s) model=%s evaluated_family=%s\n"
            % (run["run_dir"], run["class"], run["class_source"], run["model_id"],
               run["evaluated_family"])
        )
        w("  MARKER sha256=%s\n" % run["marker_sha256"])
        resume_by_file = {d["judge_file"]: d for d in run.get("resume_judges", [])}
        for path in run["judge_files"]:
            decision = resume_by_file.get(path)
            if decision is None:
                note = "  [EXISTS - refused]" if path in run["existing_judge_files"] else ""
            elif decision["action"] == "reuse":
                note = "  [EXISTS - reused, %d views]" % decision["n_views_expected"]
            elif decision["action"] == "refuse":
                note = "  [EXISTS - refused: %s differs]" % decision["mismatch"]["field"]
            else:
                note = "  [to run]" + (
                    "  [%d stray shard file(s) will be archived]"
                    % len(decision["stray_shard_files"])
                    if decision["stray_shard_files"]
                    else ""
                )
            w("  judge -> %s%s\n" % (path, note))
        w(
            "  items: %d (%d control) - every id present in the items file\n"
            % (run["n_items"], run["n_control_items"])
        )
        w(
            "  panel -> %s%s\n"
            % (run["panel_file"],
               "  [EXISTS - reused]" if run.get("panel_reuse")
               else ("  [EXISTS]" if run["panel_exists"] else ""))
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
        "--resume",
        action="store_true",
        help="reuse judge outputs that are complete and provenance-identical to "
        "this plan (skipped as 'reused', no subprocess), run only the missing "
        "judges; any provenance difference refuses the whole pass",
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
    set_launch_stamp()  # one stamp per invocation: the record file name carries it
    if argv and argv[0] == "score":
        return score_main(argv[1:], gpu_probe=gpu_probe)
    command = command_string(argv)
    if argv and argv[0] == "run":  # optional sub-command word, mirrors `score`
        argv = argv[1:]
    args = build_parser().parse_args(argv)
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

    # Before any GPU selection/pinning and before any provider engine is built.
    caches = pin_compile_caches(Path(__file__).resolve().parents[2])
    sys.stdout.write(compile_caches_line(caches))

    preflights = [
        preflight(
            out_root,
            m,
            args.run_class,
            prereg,
            sha,
            gpu_probe=gpu_probe,
            gpu_override=args.gpu,
            min_free_gb=args.min_free_gb,
        )
        for m in models
    ]
    print_plan(plan, preflights)

    payload: Dict[str, Any] = {
        "plan": plan,
        "command": command,
        "dry_run": bool(args.dry_run),
        "experiments_csv": str(experiments_csv),
        "compile_caches": caches,
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
