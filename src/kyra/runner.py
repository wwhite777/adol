"""Runner: execute items x conditions against a provider and write a run directory.

CLI:
  python -m kyra.runner --items <jsonl> --provider mock --cohort mock \
      --out-root result/raw [--conditions base] [--condition <tag>] \
      [--temperature <float>] [--seed <int>]

--condition writes a free tag (repeat_1..3) to the manifest verbatim while
inheriting the frozen 'base' sampling entry; --temperature/--seed are requests
passed to the provider, and the manifest still records what the provider
reports it actually applied.

Exit codes: 0 ok (MARKER written) | 2 zero items loaded | 3 validation failed
(no MARKER) | 4 bad arguments / unreadable items file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from kyra import manifest as mf
from kyra.providers import get_provider
from kyra.schema import Item, load_items

EXIT_OK = 0
EXIT_ZERO_ITEMS = 2
EXIT_VALIDATION_FAILED = 3
EXIT_BAD_INPUT = 4

# Condition -> (system_prompt_id, sampling parameters). 'base' is the only
# condition implemented in v0; Arm B (escalation state machine) is out of scope.
DEFAULT_CONDITION = "base"
CONDITIONS: Dict[str, Dict[str, object]] = {
    "base": {
        "system_prompt_id": "base_v0",
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 512,
    }
}


# Manifest fields a provider is allowed to overwrite with what it actually used.
# chat_template_kwargs / stop_token_ids are per-model generation options: a
# provider that declares them reports them here, so the manifest says what was
# applied. engine_kwargs / vllm_env are engine provenance (what the vllm engine
# was built with, and the vllm environment in force): the frozen protocol
# requires each run manifest to carry them, so they travel the same path.
PROVIDER_PARAM_KEYS = (
    "max_tokens",
    "temperature",
    "top_p",
    "chat_template_kwargs",
    "stop_token_ids",
    "engine_kwargs",
    "vllm_env",
)
# Optional provenance fields, copied only when the provider exposes them.
PROVIDER_PROVENANCE_KEYS = ("chat_template_source", "chat_template_sha256")


def provider_effective_params(provider) -> Dict[str, object]:
    """Generation parameters the provider reports as actually applied.

    The condition table is a request; the provider is the authority on what was
    sent to the model. Only known manifest keys are accepted, so a provider
    cannot inject arbitrary fields into the manifest. A provider without
    effective_params() (or one returning a non-dict) contributes nothing and the
    condition's values stand.
    """
    fn = getattr(provider, "effective_params", None)
    if not callable(fn):
        return {}
    params = fn()
    if not isinstance(params, dict):
        return {}
    return {k: v for k, v in params.items() if k in PROVIDER_PARAM_KEYS}


def provider_provenance(provider) -> Dict[str, object]:
    """Prompt-format provenance (chat template source + sha256), when exposed.

    These are only known after the provider has loaded its tokenizer, so this is
    read at the end of an item rather than at record creation. Absent values are
    omitted entirely: a missing key is honest, a null is noise.
    """
    out: Dict[str, object] = {}
    for key in PROVIDER_PROVENANCE_KEYS:
        value = getattr(provider, key, None)
        if value is not None:
            out[key] = value
    return out


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def make_run_id(cohort: str, items_path: str, now: datetime = None) -> str:
    """run_id = UTC YYYYmmddTHHMMZ + short deterministic-per-invocation suffix."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%MZ")
    seed = "%s|%s|%s|%d" % (cohort, items_path, now.isoformat(), os.getpid())
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]
    return "%s-%s" % (stamp, suffix)


def condition_config(condition: str, temperature: float = None) -> Dict[str, object]:
    """Sampling config for a condition tag.

    A tag in the CONDITIONS table uses its frozen entry. A free tag (the
    campaign's repeat_1..3) inherits the 'base' entry, so an unnamed condition
    can never invent a different system prompt or token cap - only its label and
    (optionally) the requested temperature differ. The provider still overrides
    the sampling fields with what it actually applied.
    """
    cfg = dict(CONDITIONS.get(condition, CONDITIONS[DEFAULT_CONDITION]))
    if temperature is not None:
        cfg["temperature"] = float(temperature)
    return cfg


def run_item(
    provider,
    item: Item,
    condition: str,
    run_id: str,
    temperature: float = None,
) -> Tuple[Dict, List[Dict]]:
    """Execute one item under one condition, turn by turn with the context so far.

    Returns (manifest_record, response_records). On provider failure the manifest
    record carries status='error' and the error text; turns already completed are
    still returned. Errors are never converted into content.

    `condition` is written to the manifest verbatim, so a repeat cohort is
    labelled repeat_1..3 rather than 'base'. Sampling fields record what the
    provider actually used (its effective_params()), not what the condition table
    or `temperature` asked for.
    """
    cfg = condition_config(condition, temperature)
    provider_name = getattr(provider, "provider_name", "unknown")
    record = {
        "run_id": run_id,
        "item_id": item.item_id,
        "condition": condition,
        "model_id": getattr(provider, "model_id", "unknown"),
        "provider": provider_name,
        "api_version": getattr(provider, "api_version", "unknown"),
        "system_prompt_id": cfg["system_prompt_id"],
        "temperature": cfg["temperature"],
        "top_p": cfg["top_p"],
        "max_tokens": cfg["max_tokens"],
        "started_utc": utc_now_iso(),
        "finished_utc": None,
        "status": "ok",
        "error_text": None,
        "n_turns": item.n_turns,
    }
    record.update(provider_effective_params(provider))
    messages: List[Dict[str, str]] = []
    responses: List[Dict] = []
    for turn_index, user_text in enumerate(item.turns):
        messages.append({"role": "user", "content": user_text})
        try:
            model_text = provider.generate(list(messages))
        except Exception as exc:  # provider failure -> ERROR label, never a score
            record["status"] = "error"
            record["error_text"] = "%s: %s" % (type(exc).__name__, exc)
            record["finished_utc"] = utc_now_iso()
            record.update(provider_provenance(provider))
            return record, responses
        if not isinstance(model_text, str) or not model_text.strip():
            record["status"] = "error"
            record["error_text"] = "provider returned empty response at turn %d" % turn_index
            record["finished_utc"] = utc_now_iso()
            record.update(provider_provenance(provider))
            return record, responses
        messages.append({"role": "assistant", "content": model_text})
        responses.append(
            {
                "item_id": item.item_id,
                "condition": condition,
                "turn_index": turn_index,
                "user_text": user_text,
                "model_text": model_text,
            }
        )
    record["finished_utc"] = utc_now_iso()
    record.update(provider_provenance(provider))
    return record, responses


def execute_run(
    items: List[Item],
    provider,
    conditions: List[str],
    run_dir: Path,
    temperature: float = None,
) -> Tuple[bool, List[str]]:
    """Write manifest/responses for every item x condition, then validate + MARKER.

    `temperature` is the requested value for the manifest record; it is only a
    request, the provider's effective_params() still has the last word.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    manifest_path = run_dir / mf.MANIFEST_NAME
    responses_path = run_dir / mf.RESPONSES_NAME
    for condition in conditions:
        for item in items:
            rec, resps = run_item(provider, item, condition, run_id, temperature=temperature)
            mf.write_manifest_record(manifest_path, rec)
            for r in resps:
                mf.write_response_record(responses_path, r)
    item_ids = [it.item_id for it in items]
    ok, reasons = mf.validate_run(run_dir, len(items), len(conditions), item_ids=item_ids)
    if ok:
        mf.write_marker(run_dir, len(items), len(conditions), item_ids=item_ids)
    return ok, reasons


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kyra.runner", description="KYRA-Bench runner v0")
    p.add_argument("--items", required=True, help="items JSONL path")
    p.add_argument("--provider", default="mock", help="provider name (v0: mock)")
    p.add_argument("--cohort", default="mock", help="cohort directory name")
    p.add_argument("--out-root", default="result/raw", help="root for result/raw/<cohort>/<run_id>")
    p.add_argument(
        "--conditions",
        nargs="+",
        default=None,
        help="conditions from the frozen table to run (v0: base)",
    )
    p.add_argument(
        "--condition",
        default=None,
        help="single free condition TAG written verbatim to the manifest "
        "(e.g. repeat_1); inherits the 'base' sampling entry. Not combinable "
        "with --conditions.",
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="requested sampling temperature: passed to the provider and "
        "recorded in the manifest (the provider still reports what it applied)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="generation seed passed to the provider (vllm default: 20260922)",
    )
    p.add_argument(
        "--model-path",
        default=None,
        help="local weights dir or HF repo id (required by --provider vllm)",
    )
    p.add_argument(
        "--max-new-tokens",
        type=int,
        default=None,
        help="generation cap passed to the provider (vllm default: 350)",
    )
    p.add_argument(
        "--chat-template-kwargs",
        default=None,
        help="JSON object of extra kwargs for the model's chat template "
        '(e.g. \'{"skip_reasoning": true}\'); vllm provider only',
    )
    p.add_argument(
        "--stop-token-ids",
        default=None,
        help="comma-separated token ids that end a turn, added to SamplingParams "
        "(e.g. 100273,100275); vllm provider only",
    )
    return p


CONDITION_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def provider_opts_from_args(args) -> Dict[str, object]:
    """Only pass options the user actually gave, so provider defaults stand."""
    opts: Dict[str, object] = {}
    if getattr(args, "model_path", None) is not None:
        opts["model_path"] = args.model_path
    if getattr(args, "max_new_tokens", None) is not None:
        opts["max_new_tokens"] = args.max_new_tokens
    if getattr(args, "temperature", None) is not None:
        opts["temperature"] = args.temperature
    if getattr(args, "seed", None) is not None:
        opts["seed"] = args.seed
    if getattr(args, "chat_template_kwargs", None) is not None:
        opts["chat_template_kwargs"] = parse_chat_template_kwargs_arg(
            args.chat_template_kwargs
        )
    if getattr(args, "stop_token_ids", None) is not None:
        opts["stop_token_ids"] = parse_stop_token_ids_arg(args.stop_token_ids)
    return opts


def parse_chat_template_kwargs_arg(text: str) -> Dict[str, object]:
    """--chat-template-kwargs '<JSON object>' -> dict. Raises ValueError."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("--chat-template-kwargs is not valid JSON: %s" % exc)
    if not isinstance(value, dict):
        raise ValueError(
            "--chat-template-kwargs must be a JSON object, got %s" % type(value).__name__
        )
    return value


def parse_stop_token_ids_arg(text: str) -> List[int]:
    """--stop-token-ids '1,2,3' -> [1, 2, 3]. Raises ValueError."""
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    ids: List[int] = []
    for part in parts:
        try:
            ids.append(int(part))
        except ValueError:
            raise ValueError("--stop-token-ids entry %r is not an int" % part)
    return ids


def resolve_conditions(args) -> List[str]:
    """[tag] for --condition, else the validated --conditions list. Raises ValueError."""
    if args.condition is not None and args.conditions is not None:
        raise ValueError("--condition and --conditions are mutually exclusive")
    if args.condition is not None:
        if not CONDITION_TAG_RE.match(args.condition):
            raise ValueError(
                "bad condition tag %r (allowed: letters, digits, . _ -)" % args.condition
            )
        return [args.condition]
    conditions = args.conditions if args.conditions is not None else [DEFAULT_CONDITION]
    for c in conditions:
        if c not in CONDITIONS:
            raise ValueError(
                "unknown condition %r (available: %s)" % (c, ", ".join(sorted(CONDITIONS)))
            )
    return list(conditions)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        conditions = resolve_conditions(args)
    except ValueError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT
    try:
        provider = get_provider(args.provider, **provider_opts_from_args(args))
    except ValueError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT
    try:
        items = load_items(args.items)
    except ValueError as exc:
        sys.stderr.write("ERROR: could not load items: %s\n" % exc)
        return EXIT_BAD_INPUT

    if not items:
        sys.stderr.write(
            "ERROR: zero items loaded from %s - refusing to write an empty run "
            "(a 0-item run is an abnormal termination, not a success)\n" % args.items
        )
        return EXIT_ZERO_ITEMS

    run_id = make_run_id(args.cohort, args.items)
    run_dir = Path(args.out_root) / args.cohort / run_id
    if run_dir.exists():
        sys.stderr.write("ERROR: run directory already exists: %s\n" % run_dir)
        return EXIT_BAD_INPUT

    sys.stdout.write(
        "run_id=%s cohort=%s provider=%s model_id=%s items=%d conditions=%s\n"
        % (run_id, args.cohort, args.provider, provider.model_id, len(items),
           ",".join(conditions))
    )
    sys.stdout.write("run_dir=%s\n" % run_dir)

    ok, reasons = execute_run(
        items, provider, list(conditions), run_dir, temperature=args.temperature
    )
    if not ok:
        sys.stderr.write("ERROR: run validation FAILED - MARKER not written:\n")
        for r in reasons:
            sys.stderr.write("  - %s\n" % r)
        return EXIT_VALIDATION_FAILED

    sys.stdout.write(
        "OK: validated %d item(s) x %d condition(s); MARKER written at %s\n"
        % (len(items), len(conditions), run_dir / mf.MARKER_NAME)
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
