"""Phase-A statistical analyses for KYRA-Bench (PREREGISTERED_kyra_v2.yaml).

One module per registered analysis; each exposes a CLI

    python -m kyra.analysis.<name> --items ... --runs ... --panels ... --out <json>
    python -m kyra.analysis.<name> --fixture <tidy.csv> --out <json>

and writes a machine-readable JSON carrying the frozen protocol hash in
its "version" field.  The scripts never judge: they emit numbers that
src/gates (G6) reads against the frozen decision rules.
"""

__all__ = [
    "loader",
    "n1_escalation",
    "n2_localization",
    "n3_reliability",
    "transitions",
    "pareto",
]
