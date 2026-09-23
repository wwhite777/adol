"""Tests for the three campaign hardenings (src/kyra/campaign.py):

  1. compile caches pinned inside the project (never /tmp, which a cleanup pass
     deletes under a compiling engine);
  2. one record file per invocation (campaign_<cohort>__<launch_stamp>.json), so
     two concurrent campaigns on one cohort cannot overwrite each other;
  3. --min-free-gb, a logged override of the MIN_FREE_GB disk floor.

Run ONLY this file (other coders are adding tests in parallel):
    cd /home/wjeong/adol && PYTHONPATH=src \
        ~/envs/jeongwoncheol_adol/bin/python -m unittest discover -s test \
        -p "test_campaign_hardening.py" -v

No model is ever loaded and no GPU is touched: every campaign call here is a
--dry-run with a temporary --out-root and a faked nvidia-smi probe.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import sys

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kyra import campaign  # noqa: E402

FIX = REPO / "test" / "fixtures" / "g6"
PREREG = REPO / "PREREGISTERED_kyra_v2.yaml"
SHA = REPO / "PREREGISTERED_kyra_v2.yaml.sha256"
SMOKE_ITEMS = REPO / "test" / "fixtures" / "items_smoke.jsonl"

CACHE_VARS = ("TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR")
STAMP_RE = re.compile(r"^\d{8}T\d{4}Z-[0-9a-f]{6}$")


def fake_gpu_probe(gpus=None, error=None):
    if gpus is None and error is None:
        gpus = [
            {"index": 0, "used_mib": 18779},
            {"index": 1, "used_mib": 4},
            {"index": 2, "used_mib": 4},
            {"index": 3, "used_mib": 4},
        ]

    def probe():
        return gpus, error

    return probe


def campaign_records(cohort_dir, cohort, suffix=""):
    return sorted(Path(cohort_dir).glob("campaign_%s__*%s.json" % (cohort, suffix)))


class EnvGuard(unittest.TestCase):
    """Base class: every variable this module may set is restored afterwards."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="campaign_harden_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved_env = {
            name: os.environ.get(name)
            for name in CACHE_VARS + ("CUDA_VISIBLE_DEVICES",)
        }
        self.addCleanup(self.restore_env)

    def restore_env(self):
        for name, value in self.saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# ==========================================================================
# 1. compile caches
# ==========================================================================
class TestPinCompileCaches(EnvGuard):
    def test_unset_variables_are_pinned_under_the_project(self):
        env = {}  # a fake environment: os.environ is not touched here
        caches = campaign.pin_compile_caches(self.tmp, environ=env)

        inductor = self.tmp / ".cache" / "torchinductor"
        triton = self.tmp / ".cache" / "triton"
        self.assertEqual(caches["TORCHINDUCTOR_CACHE_DIR"], str(inductor))
        self.assertEqual(caches["TRITON_CACHE_DIR"], str(triton))
        self.assertEqual(caches["inherited"], [])
        self.assertEqual(env["TORCHINDUCTOR_CACHE_DIR"], str(inductor))
        self.assertEqual(env["TRITON_CACHE_DIR"], str(triton))
        self.assertTrue(inductor.is_dir())
        self.assertTrue(triton.is_dir())
        # Both live under the given project root (here a temp dir), never under
        # the default /tmp/torchinductor_<user> or ~/.triton.
        for value in (caches["TORCHINDUCTOR_CACHE_DIR"], caches["TRITON_CACHE_DIR"]):
            self.assertEqual(Path(value).parent.parent, self.tmp)
            self.assertNotIn("torchinductor_", Path(value).name)

    def test_preset_variables_are_left_alone_and_reported_as_inherited(self):
        preset = {
            "TORCHINDUCTOR_CACHE_DIR": "/somewhere/inductor",
            "TRITON_CACHE_DIR": "/somewhere/triton",
        }
        env = dict(preset)
        caches = campaign.pin_compile_caches(self.tmp, environ=env)

        self.assertEqual(env, preset, "an inherited value must not be replaced")
        self.assertEqual(caches["TORCHINDUCTOR_CACHE_DIR"], preset["TORCHINDUCTOR_CACHE_DIR"])
        self.assertEqual(caches["TRITON_CACHE_DIR"], preset["TRITON_CACHE_DIR"])
        self.assertEqual(sorted(caches["inherited"]), sorted(CACHE_VARS))
        self.assertFalse((self.tmp / ".cache").exists())


# ==========================================================================
# 2. + 3. one record per invocation, --min-free-gb
# ==========================================================================
class TestCampaignInvocationHardening(EnvGuard):
    def dry_run(self, cohort, out_root=None, extra=None, probe=None):
        out_root = out_root or (self.tmp / "raw")
        argv = [
            "--items", str(SMOKE_ITEMS),
            "--models", str(FIX / "models_fake_vllm.json"),
            "--cohort", cohort,
            "--class", "confirmatory",
            "--dry-run",
            "--out-root", str(out_root),
            "--experiments-csv", str(self.tmp / "EXPERIMENTS.csv"),
            "--prereg", str(PREREG),
            "--sha", str(SHA),
        ] + list(extra or [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(argv, gpu_probe=probe or fake_gpu_probe())
        return code, buf.getvalue(), out_root / cohort

    def test_dry_run_prints_the_cache_line_and_records_the_new_fields(self):
        for name in CACHE_VARS:
            os.environ.pop(name, None)
        code, out, cohort_dir = self.dry_run("hardenrec")
        self.assertEqual(code, campaign.EXIT_OK, out)
        self.assertIn("compile caches: TORCHINDUCTOR_CACHE_DIR=", out)
        self.assertIn("TRITON_CACHE_DIR=", out)
        self.assertIn("(inherited: none)", out)

        paths = campaign_records(cohort_dir, "hardenrec")
        self.assertEqual(len(paths), 1, [p.name for p in paths])
        record = json.loads(paths[0].read_text(encoding="utf-8"))

        caches = record["compile_caches"]
        self.assertEqual(caches["inherited"], [])
        expected_leaf = {
            "TORCHINDUCTOR_CACHE_DIR": "torchinductor",
            "TRITON_CACHE_DIR": "triton",
        }
        for name in CACHE_VARS:
            value = caches[name]
            self.assertEqual(os.environ.get(name), value)
            self.assertFalse(value.startswith("/tmp/"), value)
            self.assertTrue(Path(value).is_dir(), value)
            self.assertEqual(Path(value).name, expected_leaf[name])
            self.assertEqual(Path(value).parent.name, ".cache")
            self.assertIn("compile caches: ", out)

        self.assertTrue(STAMP_RE.match(record["launch_stamp"]), record["launch_stamp"])
        self.assertEqual(record["record_path"], str(paths[0]))
        self.assertIn("__%s.json" % record["launch_stamp"], paths[0].name)

    def test_two_invocations_leave_two_distinct_records(self):
        out_root = self.tmp / "raw"
        code_a, out_a, cohort_dir = self.dry_run("harden2", out_root=out_root)
        code_b, out_b, _ = self.dry_run("harden2", out_root=out_root)
        self.assertEqual((code_a, code_b), (campaign.EXIT_OK, campaign.EXIT_OK), out_a + out_b)

        paths = campaign_records(cohort_dir, "harden2")
        self.assertEqual(len(paths), 2, [p.name for p in paths])
        stamps = [json.loads(p.read_text(encoding="utf-8"))["launch_stamp"] for p in paths]
        self.assertEqual(len(set(stamps)), 2, stamps)
        self.assertEqual(sorted(p.name for p in paths),
                         sorted("campaign_harden2__%s.json" % s for s in stamps))

    # ---- disk floor ------------------------------------------------------
    def fake_free_gb(self, value=5.0):
        original = campaign.free_gb
        campaign.free_gb = lambda path: value
        self.addCleanup(setattr, campaign, "free_gb", original)

    def test_default_floor_refuses_a_full_volume(self):
        self.fake_free_gb(5.0)
        code, out, cohort_dir = self.dry_run("hardenfloor")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("preflight disk: free 5.00 GB / required 20.00 GB -> FAIL", out)
        record = json.loads(
            campaign_records(cohort_dir, "hardenfloor")[0].read_text(encoding="utf-8")
        )
        disk = record["preflight"][0]["disk"]
        self.assertFalse(disk["ok"])
        self.assertEqual(disk["required_gb"], campaign.MIN_FREE_GB)
        self.assertFalse(disk["min_free_gb_overridden"])

    def test_override_lowers_the_floor_and_says_so(self):
        self.fake_free_gb(5.0)
        code, out, cohort_dir = self.dry_run(
            "hardenlow", extra=["--min-free-gb", "1"]
        )
        self.assertEqual(code, campaign.EXIT_OK, out)
        self.assertIn("preflight disk: free 5.00 GB / required 1.00 GB -> OK", out)
        self.assertIn("min_free_gb_overridden=True", out)
        record = json.loads(
            campaign_records(cohort_dir, "hardenlow")[0].read_text(encoding="utf-8")
        )
        disk = record["preflight"][0]["disk"]
        self.assertTrue(disk["ok"])
        self.assertEqual(disk["required_gb"], 1.0)
        self.assertTrue(disk["min_free_gb_overridden"])

    def test_passing_the_default_value_is_not_an_override(self):
        self.fake_free_gb(5.0)
        code, out, cohort_dir = self.dry_run(
            "hardensame", extra=["--min-free-gb", "20"]
        )
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertNotIn("min_free_gb_overridden=True", out)
        record = json.loads(
            campaign_records(cohort_dir, "hardensame")[0].read_text(encoding="utf-8")
        )
        disk = record["preflight"][0]["disk"]
        self.assertEqual(disk["required_gb"], 20.0)
        self.assertFalse(disk["min_free_gb_overridden"])
        self.assertFalse(disk["ok"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
