"""Build the KYRA-Bench phase-A item set from authored YAML groups.

Reads research/items/R*_v1.yaml (schema: top-level `group`, `single_turn`,
`multi_turn`), validates the frozen design rules (PREREGISTERED_kyra_v2.yaml,
sha256 87abaae4...) and writes the runner's items JSONL plus a stratification
table.  The gate is fail-closed: when any design rule is violated nothing is
written, every reason is printed and the exit code is 3.

Exit codes: 0 = written, 2 = bad input (unreadable/malformed YAML, bad CLI
argument), 3 = design-gate failure.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from kyra.schema import Item, item_from_dict, load_items

# --- design constants (frozen protocol) -------------------------------------

ALL_GROUPS = ("R1", "R2", "R3", "R4", "R5", "R6")
N_SINGLE_PER_GROUP = 6
N_MULTI_PER_GROUP = 6
N_LEXICAL_CONTRASTS = 4
N_LONG_HORIZON = 4
TURNS_SHORT_MULTI = 3
TURNS_LONG_HORIZON = 6
LENGTH_TOLERANCE = 0.20

# The one place the Korean request endings are configured.  A sentence counts as
# an information request when it ends with "?" or, after trailing punctuation /
# quotes / spaces are stripped, with one of these suffixes.
REQUEST_ENDINGS: Tuple[str, ...] = (
    "줘",
    "줘요",
    "주세요",
    "줄래",
    "줄래요",
    "줄 수 있어",
    "줄 수 있어요",
)

DEFAULT_HF_HOME = "/home/wjeong/adol/models/hf"
DEFAULT_TOKENIZER = "LGAI-EXAONE/EXAONE-4.0-1.2B"

_SENTENCE_RE = re.compile(r"[^.?!\n]+[.?!]*")
_TRAILING = " \t\"'”’)》」』.?!…~"


class BadInput(Exception):
    """Raised for malformed source files or CLI arguments (exit 2)."""


# --- text helpers -----------------------------------------------------------


def split_sentences(text: str) -> List[str]:
    """Split on . ? ! and line breaks, keeping the terminal punctuation."""
    return [s.strip() for s in _SENTENCE_RE.findall(text or "") if s.strip()]


def is_request(sentence: str) -> bool:
    """True when a sentence asks for something (question mark or request ending)."""
    s = sentence.strip()
    if not s:
        return False
    if s.endswith("?"):
        return True
    core = s.rstrip(_TRAILING)
    return any(core.endswith(end) for end in REQUEST_ENDINGS)


def count_requests(text: str) -> int:
    """Number of information requests in one user utterance."""
    return sum(1 for s in split_sentences(text) if is_request(s))


def load_tokenizer(tokenizer_id: str, hf_home: str) -> Tuple[Any, Optional[str]]:
    """Return (tokenize_fn_backend, warn_message).

    On any failure the backend is None and the caller falls back to characters.
    """
    if tokenizer_id.lower() == "none":
        return None, "WARN: tokenizer disabled by --tokenizer none; using character counts"
    try:
        os.environ["HF_HOME"] = hf_home
        os.environ["HF_HUB_OFFLINE"] = "1"
        from transformers import AutoTokenizer  # noqa: PLC0415

        tok = AutoTokenizer.from_pretrained(tokenizer_id, local_files_only=True)
        return tok, None
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, (
            "WARN: tokenizer %r could not be loaded from HF_HOME=%s (%s: %s); "
            "falling back to character counts for the +/-20%% length check"
            % (tokenizer_id, hf_home, type(exc).__name__, exc)
        )


def token_length(text: str, tok: Any) -> int:
    if tok is None:
        return len(text or "")
    return len(tok.encode(text or "", add_special_tokens=False))


# --- source loading ---------------------------------------------------------


def load_group_file(path: Path) -> Dict[str, Any]:
    """Load one authored group YAML; raises BadInput on structural problems."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise BadInput("pyyaml is required to read %s (%s)" % (path, exc)) from exc
    try:
        with path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except Exception as exc:
        raise BadInput("%s: cannot parse YAML (%s)" % (path, exc)) from exc
    if not isinstance(doc, dict):
        raise BadInput("%s: top level must be a mapping" % path)
    for key in ("group", "single_turn", "multi_turn"):
        if key not in doc:
            raise BadInput("%s: missing top-level key %r" % (path, key))
    if not isinstance(doc["group"], str) or not doc["group"].strip():
        raise BadInput("%s: 'group' must be a non-empty string" % path)
    for key in ("single_turn", "multi_turn"):
        if not isinstance(doc[key], list) or not doc[key]:
            raise BadInput("%s: %r must be a non-empty list" % (path, key))
        for i, entry in enumerate(doc[key]):
            if not isinstance(entry, dict):
                raise BadInput("%s: %s[%d] must be a mapping" % (path, key, i))
            if not isinstance(entry.get("item_id"), str) or not entry.get("item_id", "").strip():
                raise BadInput("%s: %s[%d] missing a string 'item_id'" % (path, key, i))
    doc["_path"] = str(path)
    return doc


def _seq(entry: Dict[str, Any], key: str, where: str, reasons: List[str]) -> Optional[List[str]]:
    """Fetch a list-of-strings field, recording a gate reason when unusable."""
    val = entry.get(key)
    if val is None:
        reasons.append("%s: missing %r" % (where, key))
        return None
    if not isinstance(val, list) or not val or not all(
        isinstance(t, str) and t.strip() for t in val
    ):
        reasons.append("%s: %r must be a non-empty list of non-empty strings" % (where, key))
        return None
    return val


def _text(entry: Dict[str, Any], key: str, where: str, reasons: List[str]) -> Optional[str]:
    val = entry.get(key)
    if not isinstance(val, str) or not val.strip():
        reasons.append("%s: %r must be a non-empty string" % (where, key))
        return None
    return val


def _mkitem(reasons: List[str], where: str, **kw: Any) -> Optional[Item]:
    try:
        return item_from_dict(kw, where=where)
    except ValueError as exc:
        reasons.append("%s: schema rejected the generated item (%s)" % (where, exc))
        return None


# --- the gate ---------------------------------------------------------------


def build_group(
    doc: Dict[str, Any],
    tok: Any,
    reasons: List[str],
    origin: Optional[Dict[str, str]] = None,
) -> List[Item]:
    """Validate one group document and return its generated Items.

    `origin` (when given) is filled with item_id -> authoring group so that the
    CTRL contrasts and benign twins can be reported under the group they came
    from as well as under their own risk_group.
    """
    group = doc["group"]
    src = doc.get("_path", "<doc>")
    singles = doc["single_turn"]
    multis = doc["multi_turn"]
    items: List[Item] = []

    if len(singles) != N_SINGLE_PER_GROUP:
        reasons.append(
            "%s [%s]: expected %d single_turn items, found %d"
            % (src, group, N_SINGLE_PER_GROUP, len(singles))
        )
    if len(multis) != N_MULTI_PER_GROUP:
        reasons.append(
            "%s [%s]: expected %d multi_turn items, found %d"
            % (src, group, N_MULTI_PER_GROUP, len(multis))
        )

    n_contrast = sum(1 for e in singles if e.get("lexical_contrast") is not None)
    if n_contrast != N_LEXICAL_CONTRASTS:
        reasons.append(
            "%s [%s]: expected %d singles with lexical_contrast, found %d"
            % (src, group, N_LEXICAL_CONTRASTS, n_contrast)
        )
    n_long = sum(1 for e in multis if bool(e.get("long_horizon")))
    if n_long != N_LONG_HORIZON:
        reasons.append(
            "%s [%s]: expected %d multis with long_horizon true, found %d"
            % (src, group, N_LONG_HORIZON, n_long)
        )

    for entry in singles:
        iid = entry["item_id"]
        where = "%s [%s]" % (src, iid)
        loc = _text(entry, "localized_ko", where, reasons)
        _text(entry, "literal_ko", where, reasons)
        age = entry.get("age_band")
        expl = entry.get("explicitness")
        contrast = entry.get("lexical_contrast")
        if contrast is not None and (not isinstance(contrast, str) or not contrast.strip()):
            reasons.append("%s: lexical_contrast must be a non-empty string" % where)
            contrast = None
        if loc is None:
            continue
        risk = _mkitem(
            reasons,
            where,
            item_id="%s-LOC" % iid,
            risk_group=group,
            turn_type="single",
            turns=[loc],
            age_band=age,
            explicitness=expl,
            localization="localized",
            cue_variant=None,
            twin_id=None,
            control_pair_id=("%s-CTRL" % iid) if contrast else None,
        )
        if risk is not None:
            items.append(risk)
        if contrast:
            ctrl = _mkitem(
                reasons,
                where,
                item_id="%s-CTRL" % iid,
                risk_group="CTRL",
                turn_type="single",
                turns=[contrast],
                age_band=age,
                explicitness=expl,
                localization="localized",
                cue_variant=None,
                twin_id=None,
                control_pair_id="%s-LOC" % iid,
            )
            if ctrl is not None:
                items.append(ctrl)

    for entry in multis:
        iid = entry["item_id"]
        where = "%s [%s]" % (src, iid)
        long_h = bool(entry.get("long_horizon"))
        want = TURNS_LONG_HORIZON if long_h else TURNS_SHORT_MULTI
        age = entry.get("age_band")
        expl = entry.get("explicitness")

        en = _seq(entry, "en_source", where, reasons)
        lit = _seq(entry, "literal_ko", where, reasons)
        loc = _seq(entry, "localized_ko", where, reasons)
        lens = {k: len(v) for k, v in (("en_source", en), ("literal_ko", lit), ("localized_ko", loc)) if v is not None}
        if len(set(lens.values())) > 1:
            reasons.append(
                "%s: en_source/literal_ko/localized_ko lengths differ: %s"
                % (where, ", ".join("%s=%d" % kv for kv in sorted(lens.items())))
            )
        for key, val in sorted(lens.items()):
            if val != want:
                reasons.append(
                    "%s: %s has %d turns, long_horizon=%s requires %d"
                    % (where, key, val, long_h, want)
                )

        twin = entry.get("benign_twin")
        if long_h and twin is None:
            reasons.append("%s: long_horizon item has no benign_twin" % where)
        if not long_h and twin is not None:
            reasons.append("%s: benign_twin present on a non-long-horizon item" % where)
        if twin is not None:
            twin = _seq(entry, "benign_twin", where, reasons)
        if twin is not None and loc is not None:
            if len(twin) != len(loc):
                reasons.append(
                    "%s: benign_twin has %d turns, risk script has %d"
                    % (where, len(twin), len(loc))
                )
            else:
                for i, (b, r) in enumerate(zip(twin, loc), start=1):
                    lb, lr = token_length(b, tok), token_length(r, tok)
                    lo, hi = (1 - LENGTH_TOLERANCE) * lr, (1 + LENGTH_TOLERANCE) * lr
                    if not (lo - 1e-9 <= lb <= hi + 1e-9):
                        reasons.append(
                            "%s: turn %d benign length %d outside +/-20%% of risk length %d "
                            "(allowed %.1f-%.1f, delta %+.1f%%)"
                            % (where, i, lb, lr, lo, hi, 100.0 * (lb - lr) / lr if lr else 0.0)
                        )
                    rb, rr = count_requests(b), count_requests(r)
                    if rb != rr:
                        reasons.append(
                            "%s: turn %d information requests differ: benign %d vs risk %d"
                            % (where, i, rb, rr)
                        )

        if lit is not None:
            lit_item = _mkitem(
                reasons,
                where,
                item_id="%s-LIT" % iid,
                risk_group=group,
                turn_type="multi",
                turns=lit,
                age_band=age,
                explicitness=expl,
                localization="literal",
                cue_variant=None,
                twin_id="%s-LOC" % iid,
                control_pair_id=("%s-BEN" % iid) if long_h else None,
            )
            if lit_item is not None:
                items.append(lit_item)
        if loc is not None:
            loc_item = _mkitem(
                reasons,
                where,
                item_id="%s-LOC" % iid,
                risk_group=group,
                turn_type="multi",
                turns=loc,
                age_band=age,
                explicitness=expl,
                localization="localized",
                cue_variant=None,
                twin_id="%s-LIT" % iid,
                control_pair_id=("%s-BEN" % iid) if long_h else None,
            )
            if loc_item is not None:
                items.append(loc_item)
        if twin is not None:
            ben = _mkitem(
                reasons,
                where,
                item_id="%s-BEN" % iid,
                risk_group="CTRL",
                turn_type="multi",
                turns=twin,
                age_band=age,
                explicitness=expl,
                localization="localized",
                cue_variant=None,
                twin_id=None,
                control_pair_id="%s-LOC" % iid,
            )
            if ben is not None:
                items.append(ben)

    if origin is not None:
        for it in items:
            origin[it.item_id] = group

    return items


def build(
    docs: Sequence[Dict[str, Any]],
    expect_groups: Sequence[str],
    tok: Any,
    origin: Optional[Dict[str, str]] = None,
) -> Tuple[List[Item], List[str]]:
    """Validate every group document; return (items, reasons)."""
    reasons: List[str] = []
    items: List[Item] = []

    seen_groups: Dict[str, str] = {}
    for doc in docs:
        g = doc["group"]
        if g in seen_groups:
            reasons.append(
                "group %s appears in both %s and %s" % (g, seen_groups[g], doc.get("_path"))
            )
        seen_groups[g] = doc.get("_path", "<doc>")

    for g in expect_groups:
        if g not in seen_groups:
            reasons.append("expected group %s is missing from the source files" % g)
    for g in sorted(seen_groups):
        if g not in expect_groups:
            reasons.append(
                "group %s (%s) was found but not listed in --expect-groups" % (g, seen_groups[g])
            )

    src_ids = Counter()
    for doc in docs:
        for key in ("single_turn", "multi_turn"):
            for entry in doc[key]:
                src_ids[entry["item_id"]] += 1
    for iid, n in sorted(src_ids.items()):
        if n > 1:
            reasons.append("duplicate source item_id %r appears %d times" % (iid, n))

    for doc in docs:
        items.extend(build_group(doc, tok, reasons, origin))

    out_ids = Counter(it.item_id for it in items)
    for iid, n in sorted(out_ids.items()):
        if n > 1:
            reasons.append("duplicate generated item_id %r appears %d times" % (iid, n))

    return items, reasons


# --- output -----------------------------------------------------------------


def item_to_dict(item: Item) -> Dict[str, Any]:
    return {
        "item_id": item.item_id,
        "risk_group": item.risk_group,
        "turn_type": item.turn_type,
        "turns": list(item.turns),
        "age_band": item.age_band,
        "explicitness": item.explicitness,
        "localization": item.localization,
        "cue_variant": item.cue_variant,
        "twin_id": item.twin_id,
        "control_pair_id": item.control_pair_id,
    }


STRATA_HEADER = (
    "source_group", "group", "age_band", "explicitness", "turn_type", "localization", "n",
)


def strata_rows(
    items: Sequence[Item], origin: Optional[Dict[str, str]] = None
) -> List[Tuple[str, str, str, str, str, str, int]]:
    """One row per (source_group, group, age_band, explicitness, turn_type, localization).

    `source_group` is the group file the item was authored in, so CTRL contrasts
    and benign twins also appear under their origin group; `group` stays the
    item's own risk_group.
    """
    origin = origin or {}
    counts = Counter(
        (
            origin.get(it.item_id, it.risk_group),
            it.risk_group,
            it.age_band,
            it.explicitness,
            it.turn_type,
            it.localization,
        )
        for it in items
    )
    return [tuple(list(k) + [counts[k]]) for k in sorted(counts)]


def write_outputs(
    items: Sequence[Item],
    out: Path,
    strata: Path,
    origin: Optional[Dict[str, str]] = None,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    strata.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item_to_dict(item), ensure_ascii=False, sort_keys=False) + "\n")
    with strata.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(STRATA_HEADER)
        for row in strata_rows(items, origin):
            w.writerow(row)


def format_strata(items: Sequence[Item], origin: Optional[Dict[str, str]] = None) -> str:
    rows = strata_rows(items, origin)
    lines = ["  " + " | ".join("%-11s" % h for h in STRATA_HEADER)]
    for r in rows:
        lines.append("  " + " | ".join("%-11s" % str(c) for c in r))
    lines.append("  total: %d items" % len(items))
    return "\n".join(lines)


# --- CLI --------------------------------------------------------------------


def _cmd_build(args: argparse.Namespace) -> int:
    for g in args.expect_groups:
        if g not in ALL_GROUPS:
            print("ERROR: --expect-groups value %r is not one of %s" % (g, list(ALL_GROUPS)), file=sys.stderr)
            return 2
    paths = sorted(Path(p) for p in glob.glob(args.src))
    if not paths:
        print("ERROR: no source files match --src %r" % args.src, file=sys.stderr)
        return 2
    try:
        docs = [load_group_file(p) for p in paths]
    except BadInput as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    tok, warn = load_tokenizer(args.tokenizer, args.hf_home)
    if warn:
        print(warn)

    origin: Dict[str, str] = {}
    items, reasons = build(docs, args.expect_groups, tok, origin)
    if reasons:
        print("GATE FAILED: %d design violation(s); nothing written" % len(reasons))
        for r in reasons:
            print("  FAIL %s" % r)
        return 3

    out, strata = Path(args.out), Path(args.strata)
    write_outputs(items, out, strata, origin)
    try:
        loaded = load_items(out)
    except ValueError as exc:
        out.unlink(missing_ok=True)
        strata.unlink(missing_ok=True)
        print("GATE FAILED: written items do not load under schema.load_items: %s" % exc)
        return 3
    if len(loaded) != len(items):
        out.unlink(missing_ok=True)
        strata.unlink(missing_ok=True)
        print("GATE FAILED: wrote %d items but reloaded %d" % (len(items), len(loaded)))
        return 3

    print("OK: %d items -> %s" % (len(items), out))
    print("OK: stratification -> %s" % strata)
    print(format_strata(items, origin))
    return 0


def _cmd_diagnose(args: argparse.Namespace) -> int:
    """Print per-turn risk/twin token lengths, allowed windows and request counts."""
    paths = sorted(Path(p) for p in glob.glob(args.src))
    if not paths:
        print("ERROR: no source files match --src %r" % args.src, file=sys.stderr)
        return 2
    try:
        docs = [load_group_file(p) for p in paths]
    except BadInput as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    tok, warn = load_tokenizer(args.tokenizer, args.hf_home)
    print("tokenizer: %s%s" % (args.tokenizer, " (local files only)" if tok is not None else ""))
    if warn:
        print(warn)
    print(
        "tolerance: benign token length must be within +/-%d%% of the localized risk turn"
        % int(round(100 * LENGTH_TOLERANCE))
    )

    n_bad = 0
    for doc in docs:
        print("\n### group %s (%s)" % (doc["group"], doc.get("_path")))
        for entry in doc["multi_turn"]:
            twin = entry.get("benign_twin")
            loc = entry.get("localized_ko")
            if not isinstance(twin, list) or not isinstance(loc, list):
                continue
            print("\n== %s" % entry["item_id"])
            if len(twin) != len(loc):
                print("  benign_twin has %d turns, risk script has %d" % (len(twin), len(loc)))
                n_bad += 1
                continue
            for i, (b, r) in enumerate(zip(twin, loc), start=1):
                lb, lr = token_length(b, tok), token_length(r, tok)
                lo, hi = (1 - LENGTH_TOLERANCE) * lr, (1 + LENGTH_TOLERANCE) * lr
                len_ok = lo - 1e-9 <= lb <= hi + 1e-9
                rb, rr = count_requests(b), count_requests(r)
                req_ok = rb == rr
                if not (len_ok and req_ok):
                    n_bad += 1
                print(
                    "  turn %d  tok risk=%-3d benign=%-3d allowed=%.1f-%.1f %-4s | req risk=%d "
                    "benign=%d %s"
                    % (i, lr, lb, lo, hi, "OK" if len_ok else "FAIL", rr, rb,
                       "OK" if req_ok else "FAIL")
                )
                if not (len_ok and req_ok):
                    print("      risk  : %s" % r)
                    print("      benign: %s" % b)
    print("\n%d turn(s) fail the twin rules" % n_bad)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kyra.items", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the phase-A item set from authored YAML groups")
    b.add_argument("--src", required=True, help="glob of authored group YAML files (quote it)")
    b.add_argument("--out", required=True, help="output items JSONL path")
    b.add_argument("--strata", required=True, help="output stratification CSV path")
    b.add_argument(
        "--expect-groups",
        nargs="+",
        default=list(ALL_GROUPS),
        help="groups that must be present (default: %s)" % " ".join(ALL_GROUPS),
    )
    b.add_argument("--tokenizer", default=DEFAULT_TOKENIZER, help="HF tokenizer id, or 'none' for character counts")
    b.add_argument("--hf-home", default=DEFAULT_HF_HOME, help="HF_HOME for the local tokenizer")
    b.set_defaults(func=_cmd_build)

    d = sub.add_parser("diagnose", help="print per-turn benign-twin length/request diagnostics")
    d.add_argument("--src", required=True, help="glob of authored group YAML files (quote it)")
    d.add_argument("--tokenizer", default=DEFAULT_TOKENIZER, help="HF tokenizer id, or 'none'")
    d.add_argument("--hf-home", default=DEFAULT_HF_HOME, help="HF_HOME for the local tokenizer")
    d.set_defaults(func=_cmd_diagnose)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse uses 2 for usage errors already
        return int(exc.code or 0)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
