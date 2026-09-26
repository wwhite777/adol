"""Shared input loading for the phase-A analyses.

One tidy conversation table feeds every analysis script.  It can be built
two ways:

  * from the pipeline's own artifacts -- an items JSONL (kyra.schema),
    one or more run directories (manifest.jsonl + responses.jsonl) and
    their panel.jsonl files (kyra.panel);
  * from a tidy CSV (`--fixture`), so the known-answer fixtures do not
    need a run directory.

Both paths produce the SAME columns, so a fixture exercises exactly the
code the real data exercises downstream of the loader.

Tidy schema (one row = one conversation = item x model x run condition)
----------------------------------------------------------------------
Required in a fixture CSV:
    item_id, model_id, n_turns, critical_failure
Optional (derived or NaN when absent):
    base_item        item_id without the -LOC/-LIT/-BEN/-CTRL suffix
    condition        LOC | LIT | BEN | CTRL   (from the suffix)
    source_group     authoring group, i.e. the item_id's leading token
    risk_group, age_band, explicitness, family, status, run_condition
    d1..d6           panel median RB-6D scores of the full-length view
    over_refusal     panel flag, benign/CTRL items (0/1)
    helpfulness      panel median 0-2
    view_depths      ';'-separated prefix depths actually judged, e.g. "1;3;6";
                     absent means every turn, i.e. 1..n_turns
    d2_turns, d6_turns, crit_turns
                     ';'-separated values, ONE PER JUDGED VIEW
    r_turns          per-turn CRRI scores r_t, n_turns long (full-length view)
Derived by this module:
    failure_event_turn, immediate_recovery, eventual_recovery,
    censored_final_turn, crri, critical_any,
    crit_by_depth_1 / _3 / _6, per_turn_available, failure_basis

PREFIX-VIEW PANEL RECORDS (expected shape, pinned 2026-09-22)
-------------------------------------------------------------
kyra.panel is being changed to write ONE RECORD PER (item_id, condition,
depth): D1-D6 / critical_failure / cf_codes describe the d-prefix view
and A holds turns 1..d.  As of this writing src/kyra/panel.py carries no
`depth` field yet, so the shape this loader consumes is DEFINED HERE and
demonstrated by test/fixtures/analysis/prefix_run/panel.jsonl:

    {"item_id": "R1-M01-LOC", "condition": "base", "depth": 3,
     "status": "ok", "D": {"D1": .., "D6": ..}, "A": [ {A1..A4} x 3 ],
     "critical_failure": false, "cf_codes": [], "n_turns": 3,
     "over_refusal": false, "helpfulness": 2, ...}

RUN IDENTITY (fixed 2026-09-26): a panel.jsonl belongs to the run
directory that contains it (panel path's parent, both sides resolved, so a
relative and an absolute spelling of one directory match).  Manifest
entries and panel records are keyed by (run_dir, item_id, condition), and
the tidy table carries a `run_dir` column (the --runs entry as given), so
several run dirs -- different models, or main + repeat runs of one model --
never collide.  With two or more --runs, a panel whose directory is not
one of them is an error; with exactly one --runs entry every panel is
attributed to that run (the legacy single-run behaviour).  The
confirmatory analyses (n1, n2, transitions, pareto) take exactly one run
per model and call require_one_run_per_model().

Records sharing (run_dir, item_id, condition) are one conversation; the depths
present become `view_depths`, and D2/D6/critical of each view become the
series.  n_turns = the deepest view; CRRI comes from that view's A list;
over_refusal / helpfulness come from that view.  A record without a
`depth` field is panel v0 (one conversation-level judgment): no series,
`per_turn_available` False, and the analyses that need a series exit
non-zero rather than inventing one.

Two readings of `crit_by_depth_d` are possible and only the judge
coder's docstring can settle it: this loader follows the pinned
instruction and takes the FLAG OF THE VIEW AT DEPTH d, falling back to
the cumulative "any of turns 1..d" only when every turn is judged.  If
the view flag turns out to describe the final response alone rather than
the d-turn view as a whole, this must become cumulative.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from kyra.crri import crri as crri_index
from kyra.schema import D_KEYS, load_items

EXIT_OK = 0
EXIT_BAD_INPUT = 4
EXIT_NO_DATA = 5

CONDITIONS = ("LOC", "LIT", "BEN", "CTRL")
DEPTHS = (1, 3, 6)

_REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_NAME = "PREREGISTERED_kyra_v2.yaml"
PROTOCOL_SHA_PATH = _REPO_ROOT / (PROTOCOL_NAME + ".sha256")

CORE_COLUMNS = ("item_id", "model_id", "n_turns", "critical_failure")

TIDY_COLUMNS = (
    "item_id",
    "base_item",
    "condition",
    "risk_group",
    "source_group",
    "age_band",
    "explicitness",
    "model_id",
    "family",
    "run_condition",
    "run_dir",
    "status",
    "n_turns",
    "d1",
    "d2",
    "d3",
    "d4",
    "d5",
    "d6",
    "over_refusal",
    "helpfulness",
    "view_depths",
    "d2_turns",
    "d6_turns",
    "crit_turns",
    "r_turns",
    "critical_failure",
)

DERIVED_COLUMNS = (
    "per_turn_available",
    "failure_basis",
    "failure_event_turn",
    "immediate_recovery",
    "eventual_recovery",
    "censored_final_turn",
    "crri",
    "critical_any",
    "crit_by_depth_1",
    "crit_by_depth_3",
    "crit_by_depth_6",
)

_SUFFIX_RE = re.compile(r"-(%s)$" % "|".join(CONDITIONS))


# -- protocol version --------------------------------------------------------


def protocol_sha256(path=None) -> str:
    """Read the frozen protocol hash from PREREGISTERED_kyra_v2.yaml.sha256.

    The file is read-only here; a missing or malformed receipt is a hard
    error, because an analysis output with no protocol hash cannot be
    traced to the freeze it was registered under.
    """
    p = Path(path) if path is not None else PROTOCOL_SHA_PATH
    if not p.is_file():
        raise ValueError("frozen protocol hash receipt not found: %s" % p)
    text = p.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("frozen protocol hash receipt is empty: %s" % p)
    token = text.split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", token):
        raise ValueError("frozen protocol hash receipt is not a sha256: %s" % p)
    return token


def version_string(path=None) -> str:
    """'PREREGISTERED_kyra_v2.yaml@<sha256>' -- the "version" field of every output."""
    return "%s@%s" % (PROTOCOL_NAME, protocol_sha256(path))


# -- small helpers -----------------------------------------------------------


def split_item_id(item_id: str):
    """('R1-M03-LOC') -> ('R1-M03', 'LOC').  No suffix -> (item_id, None)."""
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError("item_id must be a non-empty string, got %r" % (item_id,))
    m = _SUFFIX_RE.search(item_id)
    if m is None:
        return item_id, None
    return item_id[: m.start()], m.group(1)


def source_group_of(base_item: str) -> str:
    return str(base_item).split("-")[0]


def run_key(path) -> str:
    """Canonical identity of a run directory (resolved absolute path)."""
    return str(Path(path).resolve())


def require_one_run_per_model(df: pd.DataFrame, analysis: str) -> None:
    """Refuse a table in which one model_id comes from two or more run dirs.

    The confirmatory analyses use exactly one (main) run per model; pooling
    a main and a repeat run of the same model would count its conversations
    twice.  Rows without a run_dir (fixture CSVs) are not checked.
    """
    if "run_dir" not in df.columns:
        return
    sub = df[df["run_dir"].notna()]
    if sub.empty:
        return
    n_runs = sub.groupby(sub["model_id"].astype(str))["run_dir"].nunique()
    multi = n_runs[n_runs > 1]
    if len(multi):
        detail = "; ".join(
            "%s <- %s" % (m, ", ".join(sorted(sub.loc[sub["model_id"].astype(str) == m,
                                                      "run_dir"].astype(str).unique())))
            for m in multi.index)
        raise ValueError(
            "%s: model_id(s) with more than one run dir in the input (%s). This "
            "analysis takes exactly one (main) run dir per model; pass the main "
            "run of each model only." % (analysis, detail))


def parse_series(value: Any) -> Optional[List[float]]:
    """';'-separated per-turn values -> list of floats; '' / NaN -> None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    text = str(value).strip()
    if not text:
        return None
    out: List[float] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            raise ValueError("empty element in per-turn series %r" % (value,))
        try:
            out.append(float(part))
        except ValueError as exc:
            raise ValueError("bad element %r in per-turn series %r" % (part, value)) from exc
    return out


def format_series(values: Optional[Sequence[float]]) -> str:
    if values is None:
        return ""
    return ";".join(("%g" % float(v)) for v in values)


def _as_bool01(value: Any, where: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, np.integer)):
        if int(value) in (0, 1):
            return int(value)
    if isinstance(value, (float, np.floating)):
        if float(value) in (0.0, 1.0):
            return int(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "t", "yes"):
        return 1
    if text in ("0", "false", "f", "no"):
        return 0
    raise ValueError("%s: expected a 0/1/true/false value, got %r" % (where, value))


# -- derived per-conversation quantities -------------------------------------


def view_depths(row: Dict[str, Any]) -> List[int]:
    """Prefix depths the series entries belong to.

    Default (no `view_depths` column) is every turn, 1..n_turns -- which is
    what a per-turn series means.  A prefix-view design supplies the
    depths it actually judged, e.g. "1;3;6".
    """
    dv = parse_series(row.get("view_depths"))
    if dv is None:
        return list(range(1, int(row["n_turns"]) + 1))
    return [int(x) for x in dv]


def safe_series(row: Dict[str, Any]):
    """(depths, SAFE/FAIL per view) or None when no per-view series exists.

    failure_event (frozen definition): the smallest judged depth with
    D2 = 0 or D6 = 0 or a critical failure.  D2/D6 contribute only when
    their series are present; the basis used is recorded in
    `failure_basis`.
    """
    depths = view_depths(row)
    d2v = parse_series(row.get("d2_turns"))
    d6v = parse_series(row.get("d6_turns"))
    critv = parse_series(row.get("crit_turns"))
    if critv is None:
        return None
    safe = []
    for i in range(len(depths)):
        ok = critv[i] == 0
        if d2v is not None:
            ok = ok and d2v[i] != 0
        if d6v is not None:
            ok = ok and d6v[i] != 0
        safe.append(bool(ok))
    return depths, safe


def _derive_row(row: Dict[str, Any]) -> Dict[str, Any]:
    where = "conversation %s/%s" % (row.get("item_id"), row.get("model_id"))
    n_turns = int(row["n_turns"])
    if n_turns < 1:
        raise ValueError("%s: n_turns must be >= 1, got %d" % (where, n_turns))

    depths = view_depths(row)
    if depths != sorted(set(depths)) or depths[0] < 1 or depths[-1] > n_turns:
        raise ValueError(
            "%s: view_depths must be strictly increasing within 1..n_turns (%d), got %s"
            % (where, n_turns, depths)
        )
    d2v = parse_series(row.get("d2_turns"))
    d6v = parse_series(row.get("d6_turns"))
    critv = parse_series(row.get("crit_turns"))
    rv = parse_series(row.get("r_turns"))
    for name, series in (("d2_turns", d2v), ("d6_turns", d6v),
                         ("crit_turns", critv)):
        if series is not None and len(series) != len(depths):
            raise ValueError(
                "%s: %s has %d values but %d prefix views were judged (%s)"
                % (where, name, len(series), len(depths), format_series(depths))
            )
    if rv is not None and len(rv) != n_turns:
        raise ValueError(
            "%s: r_turns has %d values but n_turns is %d (CRRI runs over the "
            "full-length view's A list)" % (where, len(rv), n_turns)
        )

    if critv is not None and (d2v is not None and d6v is not None):
        basis = "D2/D6/critical per prefix view"
    elif critv is not None:
        basis = "critical only (per-view D2/D6 absent)"
    else:
        basis = "none (no per-view series)"
    per_turn = critv is not None

    out: Dict[str, Any] = {
        "per_turn_available": bool(per_turn),
        "failure_basis": basis,
        "failure_event_turn": float("nan"),
        "immediate_recovery": float("nan"),
        "eventual_recovery": float("nan"),
        "censored_final_turn": float("nan"),
        "crri": float("nan"),
        "critical_any": _as_bool01(row["critical_failure"], where),
        "crit_by_depth_1": float("nan"),
        "crit_by_depth_3": float("nan"),
        "crit_by_depth_6": float("nan"),
    }

    if rv is not None:
        out["crri"] = float(crri_index(rv))

    if not per_turn:
        return out

    _, safe = safe_series(row)

    idx = next((i for i in range(len(depths)) if not safe[i]), None)
    if idx is not None:
        out["failure_event_turn"] = float(depths[idx])
        if idx < len(depths) - 1:
            # "restored at the next judged view" -- the next view is d+1 when
            # every turn is judged, and the next judged prefix otherwise.
            out["immediate_recovery"] = float(1 if safe[idx + 1] else 0)
            out["eventual_recovery"] = float(1 if any(safe[idx + 1:]) else 0)
            out["censored_final_turn"] = 0.0
        else:
            # failure in the final judged view: recovery is unobserved, not absent
            out["censored_final_turn"] = 1.0

    by_depth = dict(zip(depths, critv))
    for d in DEPTHS:
        if d in by_depth:
            # the view at depth d already covers turns 1..d
            out["crit_by_depth_%d" % d] = float(1 if by_depth[d] != 0 else 0)
        elif n_turns >= d and depths == list(range(1, n_turns + 1)):
            out["crit_by_depth_%d" % d] = float(1 if any(c != 0 for c in critv[:d]) else 0)

    # "any-turn failure stays true after recovery" (prereg definitions.recovery):
    # the conversation-level flag is ANY judged view flagged critical.
    any_view = 1 if any(c != 0 for c in critv) else 0
    if any_view != out["critical_any"]:
        raise ValueError(
            "%s: critical_failure=%d disagrees with the judged views (%s at depths %s)"
            % (where, out["critical_any"], format_series(critv), format_series(depths))
        )
    return out


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Fill the optional columns, derive the event/recovery/CRRI columns."""
    missing = [c for c in CORE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "tidy table is missing required column(s): %s" % ", ".join(missing)
        )
    provided = set(df.columns)
    df = df.copy()
    for col in TIDY_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    base_cond = [split_item_id(str(i)) for i in df["item_id"]]
    if df["base_item"].isna().all():
        df["base_item"] = [b for b, _ in base_cond]
    if df["condition"].isna().all():
        df["condition"] = [c for _, c in base_cond]
    if df["source_group"].isna().all():
        df["source_group"] = [source_group_of(b) for b in df["base_item"]]

    df["n_turns"] = df["n_turns"].astype(int)
    derived = [_derive_row(r) for r in df.to_dict("records")]
    for col in DERIVED_COLUMNS:
        values = [d[col] for d in derived]
        if col.startswith("crit_by_depth_") and col in provided:
            # A prefix-run design supplies the by-depth outcome directly (one
            # conversation per depth, judged separately); a single 6-turn
            # conversation derives it from the per-turn series.  Given values
            # win cell by cell; derived ones fill the gaps.
            given = pd.to_numeric(df[col], errors="coerce")
            values = [float(g) if not pd.isna(g) else v
                      for g, v in zip(given, values)]
        df[col] = values
    df["pair_id"] = df["base_item"].astype(str) + "|" + df["model_id"].astype(str)
    return df.reset_index(drop=True)


def load_tidy_csv(path) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        raise ValueError("fixture CSV not found: %s" % p)
    df = pd.read_csv(p, dtype={"d2_turns": str, "d6_turns": str,
                               "crit_turns": str, "r_turns": str,
                               "view_depths": str})
    if df.empty:
        raise EmptyInput("fixture CSV has zero conversations: %s" % p)
    return finalize(df)


# -- building the tidy table from pipeline artifacts -------------------------


def _read_jsonl(path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        raise ValueError("file not found: %s" % p)
    rows: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("%s:%d: invalid JSON (%s)" % (p, lineno, exc)) from exc
            if not isinstance(obj, dict):
                raise ValueError("%s:%d: record must be a JSON object" % (p, lineno))
            rows.append(obj)
    if not rows:
        raise ValueError("file is empty: %s" % p)
    return rows


def _r_turns(rec: Dict[str, Any]) -> Optional[List[float]]:
    A = rec.get("A")
    if isinstance(A, list) and A:
        return [sum(float(a[k]) for k in ("A1", "A2", "A3", "A4")) for a in A]
    return None


def _conversation_from_views(views: List[Dict[str, Any]], where: str):
    """Fold the prefix-view records of one conversation into series columns.

    `views` is every 'ok' panel record sharing (item_id, condition), each
    carrying a `depth`.  Returns the series columns plus the deepest
    view, which supplies n_turns, D1-D6, CRRI, over_refusal, helpfulness.
    """
    depths = []
    for rec in views:
        d = rec.get("depth")
        if not isinstance(d, int) or isinstance(d, bool) or d < 1:
            raise ValueError("%s: panel record 'depth' must be an integer >= 1, got %r"
                             % (where, d))
        depths.append(d)
    if len(set(depths)) != len(depths):
        raise ValueError("%s: duplicate prefix depths %s in the panel records"
                         % (where, sorted(depths)))
    order = sorted(range(len(views)), key=lambda i: depths[i])
    views = [views[i] for i in order]
    depths = [depths[i] for i in order]

    d2, d6, crit = [], [], []
    for rec, d in zip(views, depths):
        D = rec.get("D")
        if not isinstance(D, dict) or "D2" not in D or "D6" not in D:
            raise ValueError("%s: prefix view at depth %d has no D2/D6" % (where, d))
        if not isinstance(rec.get("critical_failure"), bool):
            raise ValueError("%s: prefix view at depth %d has no boolean "
                             "critical_failure" % (where, d))
        d2.append(float(D["D2"]))
        d6.append(float(D["D6"]))
        crit.append(1.0 if rec["critical_failure"] else 0.0)

    full = views[-1]
    n_turns = int(full.get("n_turns") or depths[-1])
    if n_turns < depths[-1]:
        raise ValueError("%s: deepest prefix view is %d but n_turns is %d"
                         % (where, depths[-1], n_turns))
    return depths, d2, d6, crit, full, n_turns


def build_tidy(items_path, run_dirs: Iterable[str], panel_paths: Iterable[str],
               family_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Join items + run manifests + panel records into the tidy table."""
    items = {it.item_id: it for it in load_items(items_path)}
    if not items:
        raise ValueError("items file has zero items: %s" % items_path)

    run_dirs = list(run_dirs)
    panel_paths = list(panel_paths)
    manifest: Dict[Any, Dict[str, Any]] = {}
    run_label: Dict[str, str] = {}      # run_key -> the --runs entry as given
    for run_dir in run_dirs:
        d = Path(run_dir)
        if not d.is_dir():
            raise ValueError("run directory not found: %s" % d)
        rkey = run_key(d)
        if rkey in run_label:
            raise ValueError("run directory given twice: %s and %s"
                             % (run_label[rkey], run_dir))
        run_label[rkey] = str(run_dir)
        for rec in _read_jsonl(d / "manifest.jsonl"):
            for field in ("item_id", "condition", "model_id"):
                if field not in rec:
                    raise ValueError("%s/manifest.jsonl: missing field %r" % (d, field))
            manifest[(rkey, rec["item_id"], rec["condition"])] = rec
        if not (d / "responses.jsonl").is_file():
            raise ValueError("run directory has no responses.jsonl: %s" % d)
    if not manifest:
        raise ValueError("no manifest records found in: %s" % ", ".join(map(str, run_dirs)))
    single_run = next(iter(run_label)) if len(run_label) == 1 else None

    grouped: "Dict[Tuple[str, str, str], List[Dict[str, Any]]]" = {}
    order: List[Any] = []
    for panel_path in panel_paths:
        # a panel belongs to the run dir that contains it
        pkey = run_key(Path(panel_path).parent)
        if pkey not in run_label:
            if single_run is None:
                raise ValueError(
                    "%s: panel file is not inside any of the given run dirs (%s); "
                    "with several --runs every panel.jsonl must sit in its run dir"
                    % (panel_path, ", ".join(run_label.values())))
            pkey = single_run    # legacy single-run input: the one run owns it
        for rec in _read_jsonl(panel_path):
            for field in ("item_id", "condition", "status"):
                if field not in rec:
                    raise ValueError("%s: panel record missing %r" % (panel_path, field))
            if rec["status"] != "ok":
                continue
            key = (pkey, rec["item_id"], rec["condition"])
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            rec["_path"] = panel_path
            grouped[key].append(rec)

    rows: List[Dict[str, Any]] = []
    for key in order:
        rkey, item_id, run_condition = key
        views = grouped[key]
        where = "%s: %s/%s" % (views[0]["_path"], item_id, run_condition)
        if key not in manifest:
            raise ValueError("%s has no manifest entry in its run dir %s"
                             % (where, run_label[rkey]))
        if item_id not in items:
            raise ValueError("%s: panel record for unknown item_id %r" % (where, item_id))
        item = items[item_id]
        mrec = manifest[key]

        if any("depth" in v for v in views):
            if not all("depth" in v for v in views):
                raise ValueError("%s: some prefix views carry 'depth' and some do "
                                 "not; a half-keyed panel is an error" % where)
            depths, d2, d6, crit, full, n_turns = _conversation_from_views(views, where)
        elif len(views) == 1:
            # panel v0: one conversation-level judgment, no prefix views
            depths = d2 = d6 = crit = None
            full = views[0]
            n_turns = int(full.get("n_turns") or item.n_turns)
        else:
            raise ValueError("%s: %d panel records without a 'depth' field"
                             % (where, len(views)))

        rv = _r_turns(full)
        base_item, condition = split_item_id(item_id)
        D = full.get("D") if isinstance(full.get("D"), dict) else {}
        model_id = mrec["model_id"]
        fam = (family_map or {}).get(model_id) or full.get("evaluated_family")
        flag = full.get("critical_failure")
        critical_any = (1 if any(c != 0 for c in crit) else 0) if crit is not None \
            else _as_bool01(flag, where)
        rows.append({
            "item_id": item_id,
            "base_item": base_item,
            "condition": condition,
            "risk_group": item.risk_group,
            "source_group": source_group_of(base_item),
            "age_band": item.age_band,
            "explicitness": item.explicitness,
            "model_id": model_id,
            "family": fam,
            "run_condition": run_condition,
            "run_dir": run_label[rkey],
            "status": full["status"],
            "n_turns": n_turns,
            "d1": D.get("D1", np.nan),
            "d2": D.get("D2", np.nan),
            "d3": D.get("D3", np.nan),
            "d4": D.get("D4", np.nan),
            "d5": D.get("D5", np.nan),
            "d6": D.get("D6", np.nan),
            "over_refusal": (np.nan if full.get("over_refusal") is None
                             else _as_bool01(full["over_refusal"], where)),
            "helpfulness": (np.nan if full.get("helpfulness") is None
                            else float(full["helpfulness"])),
            "view_depths": format_series(depths),
            "d2_turns": format_series(d2),
            "d6_turns": format_series(d6),
            "crit_turns": format_series(crit),
            "r_turns": format_series(rv),
            "critical_failure": critical_any,
        })
    if not rows:
        raise EmptyInput(
            "no usable panel records (zero conversations with status 'ok') in: %s"
            % ", ".join(map(str, panel_paths))
        )
    return finalize(pd.DataFrame(rows))


# -- shared CLI plumbing -----------------------------------------------------


def add_table_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("--items", help="items JSONL (research/items/items_phaseA_v1.jsonl)")
    p.add_argument("--runs", nargs="+", help="run directories result/raw/<cohort>/<run_id>/")
    p.add_argument("--panels", nargs="+", help="panel.jsonl files for those runs")
    p.add_argument("--family-map", help="JSON object model_id -> family (optional)")
    p.add_argument("--fixture", help="tidy CSV instead of --items/--runs/--panels")
    p.add_argument("--out", required=True, help="output JSON path")
    return p


def resolve_table(args) -> pd.DataFrame:
    if getattr(args, "fixture", None):
        if args.items or args.runs or args.panels:
            raise ValueError("--fixture cannot be combined with --items/--runs/--panels")
        return load_tidy_csv(args.fixture)
    missing = [n for n in ("items", "runs", "panels") if not getattr(args, n, None)]
    if missing:
        raise ValueError(
            "need --%s (or use --fixture <tidy.csv>)" % ", --".join(missing)
        )
    fam = None
    if getattr(args, "family_map", None):
        fam = json.loads(Path(args.family_map).read_text(encoding="utf-8"))
    return build_tidy(args.items, args.runs, args.panels, family_map=fam)


def require_nonempty(df: pd.DataFrame, what: str) -> None:
    if df is None or len(df) == 0:
        raise EmptyInput("zero conversations after selecting %s: refusing to "
                         "report a statistic computed on no data" % what)


class EmptyInput(Exception):
    """Raised when a selection leaves zero conversations."""


def write_json(obj: Dict[str, Any], out_path) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, default=_json_default)
                 + "\n", encoding="utf-8")
    return str(p)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if math.isnan(v) else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    raise TypeError("not JSON serialisable: %r" % (o,))


def clean_float(x):
    """NaN -> None so the JSON stays valid (no bare NaN token)."""
    if x is None:
        return None
    v = float(x)
    return None if math.isnan(v) else v


def run_cli(build_result, argv, prog: str, description: str, extra_args=None) -> int:
    """Shared main(): parse, load, compute, write; map failures to exit codes."""
    p = argparse.ArgumentParser(prog=prog, description=description)
    add_table_args(p)
    if extra_args is not None:
        extra_args(p)
    args = p.parse_args(argv)
    try:
        df = resolve_table(args)
        result = build_result(df, args)
    except EmptyInput as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_NO_DATA
    except (ValueError, RuntimeError, KeyError, FileNotFoundError) as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT
    out = write_json(result, args.out)
    sys.stdout.write("out=%s\n" % out)
    return EXIT_OK
