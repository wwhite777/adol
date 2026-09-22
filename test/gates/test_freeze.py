"""Self-tests for the fail-closed preregistration freeze gate.

The gate must be proven able to FAIL before any PASS of it is trusted: every
reject fixture in test/gates/fixtures/ must be refused with its own exit code
and must leave no .sha256 receipt behind. The accepting pair must produce a
receipt whose content equals an independently computed sha256 (hashlib here,
never the gate's own helper for the reference value).

Run from the repo root:
    PYTHONPATH=src python -m unittest discover -s test/gates -v

All gate invocations write into a per-test tempfile.TemporaryDirectory; the
fixtures directory is only ever read.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOOD_PREREG = FIXTURES / "good_prereg.yaml"
GOOD_CONTRACT = FIXTURES / "good_contract.md"

from gates.verify_freeze import FreezeMismatch, verify  # noqa: E402


def sha256_bytes(path: Path) -> str:
    """Reference hash, computed independently of the gate's own helper."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_module(module: str, args: list) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-m", module] + [str(a) for a in args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def run_freeze(prereg: Path, contract: Path, out_sha=None) -> subprocess.CompletedProcess:
    args = ["--prereg", prereg, "--contract", contract]
    if out_sha is not None:
        args += ["--out-sha", out_sha]
    return run_module("gates.freeze", args)


class FreezeGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="gate_freeze_")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def stage(self, fixture_name: str) -> Path:
        """Copy a fixture prereg into the temp dir so receipts land there."""
        target = self.tmp / fixture_name
        shutil.copyfile(FIXTURES / fixture_name, target)
        return target

    # -- accepting case ---------------------------------------------------
    def test_good_pair_freezes_and_receipt_matches_independent_hash(self) -> None:
        prereg = self.stage("good_prereg.yaml")
        proc = run_freeze(prereg, GOOD_CONTRACT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        receipt = Path(str(prereg) + ".sha256")
        self.assertTrue(receipt.is_file(), "freeze exited 0 but wrote no receipt")
        expected = sha256_bytes(prereg)
        self.assertEqual(receipt.read_text(), f"{expected}  good_prereg.yaml\n")
        self.assertIn(f"FROZEN good_prereg.yaml sha256={expected}", proc.stdout)

    def test_out_sha_option_places_receipt_where_asked(self) -> None:
        prereg = self.stage("good_prereg.yaml")
        out = self.tmp / "receipts" / "prereg.sha256"
        proc = run_freeze(prereg, GOOD_CONTRACT, out_sha=out)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertTrue(out.is_file())
        self.assertFalse(Path(str(prereg) + ".sha256").exists())
        self.assertEqual(out.read_text().split()[0], sha256_bytes(prereg))

    def test_freezing_twice_is_idempotent(self) -> None:
        prereg = self.stage("good_prereg.yaml")
        first = run_freeze(prereg, GOOD_CONTRACT)
        receipt = Path(str(prereg) + ".sha256")
        content_1 = receipt.read_text()
        second = run_freeze(prereg, GOOD_CONTRACT)
        content_2 = receipt.read_text()
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        self.assertEqual(content_1, content_2)
        self.assertEqual(content_1.split()[0], sha256_bytes(prereg))

    # -- rejecting cases --------------------------------------------------
    def assert_rejected(self, fixture: str, contract: Path, code: int) -> str:
        prereg = self.stage(fixture)
        proc = run_freeze(prereg, contract)
        self.assertEqual(
            proc.returncode,
            code,
            msg=f"{fixture}: expected exit {code}, got {proc.returncode}\n{proc.stderr}",
        )
        self.assertFalse(
            Path(str(prereg) + ".sha256").exists(),
            f"{fixture}: a receipt was written for a rejected preregistration",
        )
        self.assertEqual(proc.stdout.strip(), "", f"{fixture}: refusal printed to stdout")
        self.assertIn("ERROR", proc.stderr)
        return proc.stderr

    def test_reject_parse(self) -> None:
        err = self.assert_rejected("reject_parse.yaml", GOOD_CONTRACT, 2)
        self.assertIn("PARSE_ERROR", err)

    def test_reject_schema_missing_rule(self) -> None:
        err = self.assert_rejected("reject_schema_missing_rule.yaml", GOOD_CONTRACT, 3)
        self.assertIn("SCHEMA_ERROR", err)
        self.assertIn("decision_rule", err)

    def test_reject_schema_threshold_string(self) -> None:
        err = self.assert_rejected("reject_schema_threshold_string.yaml", GOOD_CONTRACT, 3)
        self.assertIn("SCHEMA_ERROR", err)
        self.assertIn("threshold", err)

    def test_reject_two_primary(self) -> None:
        err = self.assert_rejected("reject_two_primary.yaml", GOOD_CONTRACT, 3)
        self.assertIn("SCHEMA_ERROR", err)
        self.assertIn("primary", err)

    def test_reject_contract_missing_claim_id(self) -> None:
        contract = FIXTURES / "reject_contract_id_contract.md"
        err = self.assert_rejected("reject_contract_id.yaml", contract, 4)
        self.assertIn("CONTRACT_DISAGREEMENT", err)
        self.assertIn("N3", err)

    def test_reject_contract_missing_forbidden_phrase(self) -> None:
        contract = FIXTURES / "reject_contract_forbidden_contract.md"
        err = self.assert_rejected("reject_contract_forbidden.yaml", contract, 4)
        self.assertIn("CONTRACT_DISAGREEMENT", err)
        self.assertIn("proves the toy system is safe", err)

    def test_reject_contract_version_mismatch(self) -> None:
        contract = FIXTURES / "reject_contract_version.md"
        err = self.assert_rejected("good_prereg.yaml", contract, 4)
        self.assertIn("CONTRACT_DISAGREEMENT", err)
        self.assertIn("Version: 1.0", err)

    def test_missing_prereg_file_is_refused(self) -> None:
        proc = run_freeze(self.tmp / "does_not_exist.yaml", GOOD_CONTRACT)
        self.assertEqual(proc.returncode, 2, msg=proc.stderr)
        self.assertFalse((self.tmp / "does_not_exist.yaml.sha256").exists())

    # -- planted-violation demonstration (check 2 of the task card) -------
    def test_planted_violation_demonstration(self) -> None:
        prereg = self.stage("reject_schema_threshold_string.yaml")
        proc = run_freeze(prereg, GOOD_CONTRACT)
        receipt = Path(str(prereg) + ".sha256")
        print(
            "\nPLANTED-VIOLATION DEMO -- gates.freeze on "
            "reject_schema_threshold_string.yaml (threshold is the string \"0.80\")\n"
            f"  exit code      : {proc.returncode} (expected 3 = SCHEMA_ERROR)\n"
            f"  receipt exists : {receipt.exists()} (expected False)\n"
            f"  stderr         : {proc.stderr.strip()}",
            file=sys.stderr,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(receipt.exists())


class VerifyFreezeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="gate_verify_")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.prereg = self.tmp / "good_prereg.yaml"
        shutil.copyfile(GOOD_PREREG, self.prereg)
        proc = run_freeze(self.prereg, GOOD_CONTRACT)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.sha = Path(str(self.prereg) + ".sha256")

    def test_verify_returns_hash_on_good_pair(self) -> None:
        self.assertEqual(verify(self.prereg, self.sha), sha256_bytes(self.prereg))

    def test_verify_cli_exits_zero_on_match(self) -> None:
        proc = run_module("gates.verify_freeze", ["--prereg", self.prereg, "--sha", self.sha])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("OK", proc.stdout)

    def tamper_one_byte(self) -> str:
        """Change exactly one byte of the prereg copy; return the new hash."""
        data = bytearray(self.prereg.read_bytes())
        index = data.index(b"0.80") + 3  # the final '0' of the threshold 0.80
        before = len(data)
        data[index] = ord("1")
        self.prereg.write_bytes(bytes(data))
        self.assertEqual(len(self.prereg.read_bytes()), before)
        return sha256_bytes(self.prereg)

    def test_verify_raises_on_tampered_file(self) -> None:
        recorded = self.sha.read_text().split()[0]
        tampered = self.tamper_one_byte()
        with self.assertRaises(FreezeMismatch) as ctx:
            verify(self.prereg, self.sha)
        self.assertEqual(ctx.exception.actual, tampered)
        self.assertEqual(ctx.exception.recorded, recorded)
        self.assertNotEqual(tampered, recorded)

    def test_verify_cli_exits_six_on_tampered_file_and_never_prints_ok(self) -> None:
        self.tamper_one_byte()
        proc = run_module("gates.verify_freeze", ["--prereg", self.prereg, "--sha", self.sha])
        self.assertEqual(proc.returncode, 6, msg=proc.stderr)
        self.assertNotIn("OK", proc.stdout)
        self.assertNotIn("OK", proc.stderr)
        self.assertIn("FREEZE_MISMATCH", proc.stderr)

    def test_verify_cli_exits_two_when_a_file_is_missing(self) -> None:
        missing_sha = run_module(
            "gates.verify_freeze",
            ["--prereg", self.prereg, "--sha", self.tmp / "absent.sha256"],
        )
        self.assertEqual(missing_sha.returncode, 2, msg=missing_sha.stderr)
        missing_prereg = run_module(
            "gates.verify_freeze",
            ["--prereg", self.tmp / "absent.yaml", "--sha", self.sha],
        )
        self.assertEqual(missing_prereg.returncode, 2, msg=missing_prereg.stderr)
        for proc in (missing_sha, missing_prereg):
            self.assertNotIn("OK", proc.stdout)

    def test_verify_refuses_a_malformed_receipt(self) -> None:
        self.sha.write_text("not-a-hash  good_prereg.yaml\n")
        with self.assertRaises(FreezeMismatch):
            verify(self.prereg, self.sha)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
