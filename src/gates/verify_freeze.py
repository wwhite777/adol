"""Frozen-preregistration hash verifier (KYRA-Bench).

Every confirmatory script calls `verify(prereg_path, sha_path)` before it does
any work: it returns the sha256 of the preregistration if that hash equals the
one recorded in the receipt written by `gates.freeze`, and raises
`FreezeMismatch` otherwise. There is no path on which a mismatch prints "OK".

CLI (from the repo root):
    PYTHONPATH=src python -m gates.verify_freeze --prereg <path> --sha <path>
    exit 0 match, 6 mismatch, 2 either file missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Union

from gates.freeze import sha256_file

EXIT_OK = 0
EXIT_MISSING = 2
EXIT_MISMATCH = 6

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class FreezeMismatch(Exception):
    """The preregistration file no longer hashes to its frozen receipt."""

    def __init__(self, prereg_path: Path, actual: str, recorded: str) -> None:
        super().__init__(
            f"{prereg_path} sha256={actual} does not match frozen receipt "
            f"sha256={recorded}"
        )
        self.prereg_path = str(prereg_path)
        self.actual = actual
        self.recorded = recorded


def read_receipt(sha_path: Path) -> str:
    """Return the hash token recorded in a '<hash>  <basename>' receipt."""
    text = sha_path.read_text(encoding="utf-8").strip()
    token = text.split()[0].lower() if text.split() else ""
    return token


def verify(prereg_path: Union[str, Path], sha_path: Union[str, Path]) -> str:
    """Return the prereg's sha256 if it matches the receipt, else raise.

    Raises FileNotFoundError if either file is missing, FreezeMismatch if the
    hashes differ or the receipt does not hold a well-formed sha256.
    """
    prereg_path = Path(prereg_path)
    sha_path = Path(sha_path)
    if not prereg_path.is_file():
        raise FileNotFoundError(f"preregistration not found: {prereg_path}")
    if not sha_path.is_file():
        raise FileNotFoundError(f"freeze receipt not found: {sha_path}")

    actual = sha256_file(prereg_path)
    recorded = read_receipt(sha_path)
    if not _HEX64.match(recorded):
        raise FreezeMismatch(prereg_path, actual, recorded or "<empty receipt>")
    if actual != recorded:
        raise FreezeMismatch(prereg_path, actual, recorded)
    return actual


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gates.verify_freeze",
        description="Verify a preregistration against its frozen sha256 receipt.",
    )
    parser.add_argument("--prereg", required=True, help="preregistration YAML path")
    parser.add_argument("--sha", required=True, help="receipt path written by gates.freeze")
    args = parser.parse_args(argv)

    try:
        digest = verify(args.prereg, args.sha)
    except FileNotFoundError as exc:
        print(f"ERROR MISSING_FILE: {exc}", file=sys.stderr)
        return EXIT_MISSING
    except FreezeMismatch as exc:
        print(
            f"ERROR FREEZE_MISMATCH: {exc.prereg_path} sha256={exc.actual} "
            f"receipt sha256={exc.recorded}",
            file=sys.stderr,
        )
        return EXIT_MISMATCH

    print(f"OK {Path(args.prereg).name} sha256={digest} matches {Path(args.sha).name}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
