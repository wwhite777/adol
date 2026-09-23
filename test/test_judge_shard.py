"""Self-tests for sharded judging (kyra.judge --shard K/N + `kyra.judge merge`).

The claim under test: splitting one judge's sequential pass over a run directory
across N engines changes only WHICH process decodes a view, never what is
written. So every test here compares an unsharded run with the merge of its N
shards on the SAME per-view canned outputs and requires the judge JSONL to be
byte-identical - including a view that is re-asked after a parse error and a view
that ends as an ERROR record.

The provider double is keyed by (view, attempt) rather than by call order
(imported from test_judge_batch), because a shard consumes the outputs of its own
views only.

Runnable as `PYTHONPATH=src:test python -m unittest test_judge_shard`.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kyra import campaign  # noqa: E402
from kyra.judge import (  # noqa: E402
    DEFAULT_SHARD,
    build_merge_parser,
    build_parser as judge_build_parser,
    judge_run,
    main as judge_main,
    merge_shards,
    meta_path_for,
    ordered_view_keys,
    parse_shard,
)

# The run fixture, the view-keyed provider double and the canned replies are the
# ones the batching tests use: the two options must be judged against the same
# views to be comparable at all.
from test_judge_batch import (  # noqa: E402
    MALFORMED,
    RecordingProvider,
    VIEW_DEPTH,
    VIEW_KEYS,
    all_valid_replies,
    retry_replies,
    valid_output,
    write_run_dir,
)
from test_g6_campaign import (  # noqa: E402
    ANCHORS,
    FIX,
    REAL_CSV,
    SMOKE_ITEMS,
    fake_gpu_probe,
    fake_judge_outputs,
    one_campaign_record,
    sha256,
)

N_VIEWS = len(VIEW_KEYS)  # 7 prefix views over 4 conversations


class ShardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kyra_judge_shard_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = write_run_dir(self.tmp / "run")

    def judge(self, replies, name, shard=1, n_shards=1, batch_size=1, **kwargs):
        """One judge_run over the fixture run dir; the judge_id is always the same
        so the records of a shard and of the unsharded run are comparable."""
        provider = RecordingProvider(replies)
        out = self.tmp / ("judge_%s.jsonl" % name)
        counts = judge_run(
            self.run_dir, provider, "JS", "lg", out, manual_text="",
            batch_size=batch_size, shard=shard, n_shards=n_shards, **kwargs
        )
        return provider, out, counts

    def shard_files(self, replies, n_shards, tag="S", **kwargs):
        """Judge the run in n_shards separate passes; returns the shard paths."""
        paths = []
        for k in range(1, n_shards + 1):
            _, out, _ = self.judge(
                replies, "%s%dof%d" % (tag, k, n_shards), shard=k, n_shards=n_shards,
                **kwargs
            )
            paths.append(out)
        return paths


# -- the slice ----------------------------------------------------------------


class TestShardSlicing(ShardTest):
    def test_shard_takes_every_nth_view_in_the_original_order(self):
        p1, out1, c1 = self.judge(all_valid_replies(), "A1", shard=1, n_shards=2)
        p2, out2, c2 = self.judge(all_valid_replies(), "A2", shard=2, n_shards=2)
        self.assertEqual(p1.calls, [VIEW_KEYS[i] for i in (0, 2, 4, 6)])
        self.assertEqual(p2.calls, [VIEW_KEYS[i] for i in (1, 3, 5)])
        self.assertEqual(c1["total"], 4)
        self.assertEqual(c2["total"], 3)
        self.assertEqual(c1["n_views_total"], N_VIEWS)
        self.assertEqual(c2["n_views_total"], N_VIEWS)
        self.assertEqual(c1["shard"], "1/2")
        self.assertEqual(c2["shard"], "2/2")

    def test_a_shard_with_no_views_still_writes_an_empty_file(self):
        replies = all_valid_replies()
        paths = self.shard_files(replies, N_VIEWS + 1, tag="E")
        self.assertTrue(paths[-1].is_file())
        self.assertEqual(paths[-1].read_bytes(), b"")
        merged = self.tmp / "judge_empty_merged.jsonl"
        counts = merge_shards(self.run_dir, paths, merged)
        self.assertEqual(counts["total"], N_VIEWS)

    def test_judge_run_rejects_an_impossible_shard(self):
        for shard, n_shards in ((0, 2), (3, 2), (1, 0), (True, 2), (1, 1.5)):
            with self.assertRaises(ValueError):
                judge_run(
                    self.run_dir, RecordingProvider(all_valid_replies()), "JS", "lg",
                    self.tmp / ("judge_bad_%s_%s.jsonl" % (shard, n_shards)),
                    manual_text="", shard=shard, n_shards=n_shards,
                )

    def test_parse_shard(self):
        self.assertEqual(parse_shard("1/1"), (1, 1))
        self.assertEqual(parse_shard("2/4"), (2, 4))
        self.assertEqual(parse_shard(DEFAULT_SHARD), (1, 1))
        for bad in ("0/2", "3/2", "2", "a/b", "1/0", "-1/2", "1/2/3", "", None, 2):
            with self.assertRaises(ValueError):
                parse_shard(bad)

    def test_ordered_view_keys_is_the_order_judge_run_writes(self):
        keys = ordered_view_keys(self.run_dir)
        self.assertEqual(len(keys), N_VIEWS)
        self.assertEqual(
            keys,
            [("I1", "base", 1), ("I2", "base", 1), ("I2", "base", 2), ("I2", "base", 3),
             ("I3", "base", 1), ("I3", "base", 2), ("I4", "base", 1)],
        )


# -- 1/1 is today's behaviour -------------------------------------------------


class TestShardOneOfOne(ShardTest):
    def test_library_shard_1_1_is_byte_identical_to_no_shard(self):
        _, plain, _ = self.judge(retry_replies(), "P1")
        _, one, _ = self.judge(retry_replies(), "P2", shard=1, n_shards=1)
        self.assertEqual(plain.read_bytes(), one.read_bytes())

    def test_shard_1_1_keeps_the_sidecar_key_set(self):
        _, plain, _ = self.judge(all_valid_replies(), "P3")
        _, one, _ = self.judge(all_valid_replies(), "P4", shard=1, n_shards=1)
        plain_meta = json.loads(meta_path_for(plain).read_text(encoding="utf-8"))
        one_meta = json.loads(meta_path_for(one).read_text(encoding="utf-8"))
        self.assertEqual(set(plain_meta), set(one_meta))
        self.assertNotIn("shard", one_meta)
        self.assertNotIn("n_views_total", one_meta)
        self.assertEqual(one_meta["n_views"], N_VIEWS)

    def cli(self, out_name, extra):
        fake = self.tmp / "fake_outputs.json"
        fake.write_text(
            json.dumps([valid_output(VIEW_DEPTH[k]) for k in VIEW_KEYS]), encoding="utf-8"
        )
        out = self.tmp / out_name
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["--run-dir", str(self.run_dir), "--provider", "fake", "--judge-id", "JC",
                 "--family", "lg", "--fake-outputs", str(fake), "--no-items",
                 "--batch-size", "1", "--out", str(out)] + extra
            )
        return rc, out, buf.getvalue()

    def test_cli_shard_1_of_1_is_byte_identical_to_no_flag(self):
        rc1, plain, out1 = self.cli("judge_cli_plain.jsonl", [])
        rc2, one, out2 = self.cli("judge_cli_1of1.jsonl", ["--shard", "1/1"])
        self.assertEqual((rc1, rc2), (0, 0), out1 + out2)
        self.assertEqual(plain.read_bytes(), one.read_bytes())
        self.assertIn("shard=1/1 shard_views=7", out2)

    def test_cli_rejects_a_malformed_shard_before_the_provider(self):
        for bad in ("0/2", "3/2", "2", "1/0", "x/y"):
            rc, out, text = self.cli("judge_cli_bad.jsonl", ["--shard", bad])
            self.assertEqual(rc, 4, text)
            self.assertIn("--shard", text)
            self.assertFalse(out.exists())


# -- merged == single engine --------------------------------------------------


class TestMergeEqualsSingleEngine(ShardTest):
    def merge_of(self, replies, n_shards, tag, **kwargs):
        _, full, full_counts = self.judge(replies, "full_%s" % tag, **kwargs)
        paths = self.shard_files(replies, n_shards, tag=tag, **kwargs)
        merged = self.tmp / ("judge_merged_%s.jsonl" % tag)
        counts = merge_shards(self.run_dir, paths, merged)
        return full, full_counts, merged, counts, paths

    def test_two_shards_merge_to_the_single_engine_file(self):
        full, fc, merged, counts, _ = self.merge_of(all_valid_replies(), 2, "M2")
        self.assertEqual(merged.read_bytes(), full.read_bytes())
        self.assertEqual(counts["total"], fc["total"])
        self.assertEqual(counts["ok"], fc["ok"])
        self.assertEqual(counts["error"], 0)

    def test_a_retried_view_and_an_error_view_survive_the_split(self):
        """views 2 and 5 parse only on the re-ask, view 7 never parses; the split
        puts view 5 and view 7 in shard 1 and view 2 in shard 2."""
        full, fc, merged, counts, _ = self.merge_of(retry_replies(), 2, "M3")
        self.assertEqual(merged.read_bytes(), full.read_bytes())
        rows = [json.loads(l) for l in merged.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["attempts"] for r in rows], [1, 2, 1, 1, 2, 1, 2])
        self.assertEqual(
            [r["status"] for r in rows], ["ok", "ok", "ok", "ok", "ok", "ok", "ERROR"]
        )
        self.assertTrue(rows[6]["error"].startswith("JudgeParseError"))
        self.assertEqual(rows[6]["raw_text"], MALFORMED)
        self.assertEqual(counts["error"], 1)
        self.assertEqual(counts["ok"], fc["ok"])

    def test_a_provider_failure_inside_a_shard_lands_on_its_own_view(self):
        replies = {k: [valid_output(VIEW_DEPTH[k])] * 2 for k in VIEW_KEYS}
        replies["I2m2"] = [TimeoutError("simulated judge timeout")] * 2
        full, _, merged, counts, _ = self.merge_of(replies, 2, "M4")
        self.assertEqual(merged.read_bytes(), full.read_bytes())
        rows = [json.loads(l) for l in merged.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["status"] for r in rows],
                         ["ok", "ok", "ERROR", "ok", "ok", "ok", "ok"])
        self.assertIn("TimeoutError", rows[2]["error"])

    def test_three_shards_merge_the_same_way(self):
        full, _, merged, counts, paths = self.merge_of(retry_replies(), 3, "M5")
        self.assertEqual(merged.read_bytes(), full.read_bytes())
        self.assertEqual(
            [len(p.read_text(encoding="utf-8").splitlines()) for p in paths], [3, 2, 2]
        )

    def test_batched_shards_merge_to_the_batched_single_engine_file(self):
        full, _, merged, _, _ = self.merge_of(retry_replies(), 2, "M6", batch_size=8)
        self.assertEqual(merged.read_bytes(), full.read_bytes())

    def test_merge_cli(self):
        paths = self.shard_files(all_valid_replies(), 2, tag="C")
        out = self.tmp / "judge_cli_merged.jsonl"
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["merge", "--run-dir", str(self.run_dir), "--views", "prefix",
                 "--shards"] + [str(p) for p in paths] + ["--out", str(out)]
            )
        text = buf.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertIn("merged shards=2 total=7 ok=7 error=0", text)
        self.assertTrue(out.is_file())
        self.assertTrue(meta_path_for(out).is_file())

    def test_merge_parser_shape(self):
        args = build_merge_parser().parse_args(
            ["--run-dir", "r", "--shards", "a.jsonl", "b.jsonl", "--out", "o.jsonl"]
        )
        self.assertEqual(args.shards, ["a.jsonl", "b.jsonl"])
        self.assertEqual(args.views, "prefix")


# -- merge refuses ------------------------------------------------------------


class TestMergeRefusals(ShardTest):
    def setUp(self):
        super().setUp()
        self.paths = self.shard_files(all_valid_replies(), 2, tag="R")
        self.out = self.tmp / "judge_merge_out.jsonl"

    def test_a_missing_shard_is_refused_naming_the_missing_views(self):
        with self.assertRaises(ValueError) as ctx:
            merge_shards(self.run_dir, [self.paths[0]], self.out)
        msg = str(ctx.exception)
        self.assertIn("3 view(s) in no shard", msg)
        self.assertIn("I2/base/d1", msg)
        self.assertFalse(self.out.exists())

    def test_a_duplicate_key_is_refused_naming_the_duplicated_views(self):
        _, full, _ = self.judge(all_valid_replies(), "R_full")
        with self.assertRaises(ValueError) as ctx:
            merge_shards(self.run_dir, [full, self.paths[0]], self.out)
        msg = str(ctx.exception)
        self.assertIn("4 view(s) in more than one shard", msg)
        self.assertIn("I1/base/d1", msg)
        self.assertFalse(self.out.exists())

    def test_a_record_for_a_view_the_run_does_not_have_is_refused(self):
        other = self.tmp / "other_run"
        write_run_dir(other)
        with (other / "responses.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"item_id": "I9", "condition": "base", "turn_index": 0,
                                 "user_text": "I9u1", "model_text": "I9m1"}) + "\n")
        with self.assertRaises(ValueError) as ctx:
            merge_shards(self.run_dir, self.paths + [self.stray_shard(other)], self.out)
        self.assertIn("views this run does not have", str(ctx.exception))

    def stray_shard(self, other_run):
        provider = RecordingProvider(
            dict(all_valid_replies(), **{"I9m1": [valid_output(1)]})
        )
        out = self.tmp / "judge_stray.jsonl"
        judge_run(other_run, provider, "JS", "lg", out, manual_text="", batch_size=1,
                  shard=8, n_shards=8)
        return out

    def rewrite_meta(self, path, **changes):
        meta_path = meta_path_for(path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(changes)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
                             encoding="utf-8")

    def test_disagreeing_prompt_template_is_refused(self):
        self.rewrite_meta(self.paths[1], prompt_template_sha256="deadbeef")
        with self.assertRaises(ValueError) as ctx:
            merge_shards(self.run_dir, self.paths, self.out)
        self.assertIn("shards disagree on prompt_template_sha256", str(ctx.exception))
        self.assertFalse(self.out.exists())

    def test_disagreeing_items_anchors_model_or_batch_size_is_refused(self):
        for field, value in (
            ("items_sha256", "a" * 64),
            ("anchors_sha256", "b" * 64),
            ("model_path", "/models/other-judge"),
            ("batch_size", 64),
            ("judge_id", "JOTHER"),
        ):
            paths = self.shard_files(all_valid_replies(), 2, tag="D_%s" % field)
            self.rewrite_meta(paths[1], **{field: value})
            out = self.tmp / ("judge_merge_%s.jsonl" % field)
            with self.assertRaises(ValueError) as ctx:
                merge_shards(self.run_dir, paths, out)
            self.assertIn("shards disagree on %s" % field, str(ctx.exception))
            self.assertFalse(out.exists())

    def test_disagreeing_engine_knobs_are_refused(self):
        for field in ("engine_kwargs", "vllm_env"):
            paths = self.shard_files(all_valid_replies(), 2, tag="K_%s" % field)
            meta_path = meta_path_for(paths[1])
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            params = dict(meta.get("provider_effective_params") or {})
            params[field] = {"changed": True}
            meta["provider_effective_params"] = params
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True),
                                 encoding="utf-8")
            out = self.tmp / ("judge_merge_knob_%s.jsonl" % field)
            with self.assertRaises(ValueError) as ctx:
                merge_shards(self.run_dir, paths, out)
            self.assertIn(
                "shards disagree on provider_effective_params.%s" % field, str(ctx.exception)
            )

    def test_a_missing_sidecar_is_refused(self):
        meta_path_for(self.paths[1]).unlink()
        with self.assertRaises(ValueError) as ctx:
            merge_shards(self.run_dir, self.paths, self.out)
        self.assertIn("shard sidecar not found", str(ctx.exception))

    def test_an_existing_merged_file_is_never_overwritten(self):
        self.out.write_text("stale\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            merge_shards(self.run_dir, self.paths, self.out)
        self.assertIn("refusing to overwrite", str(ctx.exception))
        self.assertEqual(self.out.read_text(encoding="utf-8"), "stale\n")

    def test_merge_cli_exit_code_is_4(self):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["merge", "--run-dir", str(self.run_dir), "--shards", str(self.paths[0]),
                 "--out", str(self.out)]
            )
        self.assertEqual(rc, 4, buf.getvalue())
        self.assertIn("in no shard", buf.getvalue())


# -- sidecars -----------------------------------------------------------------


class TestShardSidecars(ShardTest):
    def test_a_shard_sidecar_says_which_shard_it_is(self):
        _, out, _ = self.judge(all_valid_replies(), "SC", shard=2, n_shards=2)
        meta = json.loads(meta_path_for(out).read_text(encoding="utf-8"))
        self.assertEqual(meta["shard"], "2/2")
        self.assertEqual(meta["n_views"], 3)
        self.assertEqual(meta["n_views_total"], N_VIEWS)
        self.assertEqual(meta["decode_mode"], "sequential")

    def test_merged_sidecar_fields(self):
        paths = self.shard_files(retry_replies(), 2, tag="MS")
        merged = self.tmp / "judge_ms.jsonl"
        counts = merge_shards(self.run_dir, paths, merged)
        meta = json.loads(meta_path_for(merged).read_text(encoding="utf-8"))
        shard_metas = [
            json.loads(meta_path_for(p).read_text(encoding="utf-8")) for p in paths
        ]
        self.assertEqual(meta["decode_mode"], "sequential")
        self.assertEqual(meta["batch_size"], 1)
        self.assertEqual(meta["shards"], 2)
        self.assertEqual(meta["views"], "prefix")
        self.assertEqual(meta["judge_id"], "JS")
        self.assertEqual(meta["family"], "lg")
        self.assertEqual(meta["out_path"], str(merged))
        self.assertEqual(meta["run_dir"], str(self.run_dir))
        self.assertEqual(meta["n_views"], N_VIEWS)
        self.assertEqual(meta["n_ok"], counts["ok"])
        self.assertEqual(meta["n_error_final"], 1)
        self.assertEqual(
            meta["n_parse_errors_first_pass"],
            sum(m["n_parse_errors_first_pass"] for m in shard_metas),
        )
        self.assertEqual(meta["n_retried"], sum(m["n_retried"] for m in shard_metas))
        # provider parameters and the prompt come from shard 1 (all shards agreed)
        self.assertEqual(
            meta["provider_effective_params"], shard_metas[0]["provider_effective_params"]
        )
        self.assertEqual(
            meta["prompt_template_sha256"], shard_metas[0]["prompt_template_sha256"]
        )
        # per-shard started/finished
        self.assertEqual([s["shard"] for s in meta["shard_runs"]], ["1/2", "2/2"])
        self.assertEqual([s["path"] for s in meta["shard_runs"]], [str(p) for p in paths])
        self.assertEqual([s["n_views"] for s in meta["shard_runs"]], [4, 3])
        for shard_run, shard_meta in zip(meta["shard_runs"], shard_metas):
            self.assertEqual(shard_run["started_utc"], shard_meta["started_utc"])
            self.assertEqual(shard_run["finished_utc"], shard_meta["finished_utc"])
            self.assertEqual(shard_run["sha256"], sha256(shard_run["path"]))
        self.assertEqual(meta["started_utc"], min(m["started_utc"] for m in shard_metas))
        self.assertEqual(meta["finished_utc"], max(m["finished_utc"] for m in shard_metas))
        self.assertTrue(meta["merged_utc"].endswith("Z"))

    def test_merged_sidecar_keeps_a_batched_decode_mode(self):
        paths = self.shard_files(all_valid_replies(), 2, tag="MB", batch_size=8)
        merged = self.tmp / "judge_mb.jsonl"
        merge_shards(self.run_dir, paths, merged)
        meta = json.loads(meta_path_for(merged).read_text(encoding="utf-8"))
        self.assertEqual(meta["decode_mode"], "batched")
        self.assertEqual(meta["batch_size"], 8)


# -- campaign -----------------------------------------------------------------


class TestCampaignShards(unittest.TestCase):
    """judges.json "shards": 2 -> two kyra.judge children per judge per run,
    merged into the one judge file the panel reads. Fake providers only."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="campaign_shard_"))
        cls.out_root = cls.tmp / "raw"
        cls.csv = cls.tmp / "EXPERIMENTS.csv"
        shutil.copy2(REAL_CSV, cls.csv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(
                ["--items", str(SMOKE_ITEMS), "--models", str(FIX / "models_fake.json"),
                 "--cohort", "shardme", "--class", "smoke",
                 "--out-root", str(cls.out_root), "--experiments-csv", str(cls.csv)],
                gpu_probe=fake_gpu_probe(),
            )
        assert code == 0, buf.getvalue()
        record = json.loads(
            one_campaign_record(cls.out_root / "shardme", "shardme").read_text(encoding="utf-8")
        )
        cls.runs = [r["run_dir"] for r in record["runs"]]
        cls.judges_doc = json.loads((FIX / "judges_fake.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def setUp(self):
        # The production stagger is 45 s per shard (TestShardStagger asserts it on
        # the argv). These end-to-end tests really start the children, so they run
        # with no stagger at all: what they test is the split and the merge.
        real = campaign.SHARD_START_STAGGER_S
        campaign.SHARD_START_STAGGER_S = 0
        self.addCleanup(setattr, campaign, "SHARD_START_STAGGER_S", real)

    def judges_file(self, run_dir, shards=None, keep=None):
        doc = json.loads(json.dumps(self.judges_doc))
        judges = doc["judges"] if keep is None else [
            j for j in doc["judges"] if j["judge_id"] in keep
        ]
        for i, judge in enumerate(judges):
            out = self.tmp / ("fake_outputs_%s_%s.json" % (judge["judge_id"], Path(run_dir).name))
            out.write_text(
                json.dumps(fake_judge_outputs(run_dir, SMOKE_ITEMS, offset=i)),
                encoding="utf-8",
            )
            judge["fake_outputs"] = str(out)
            if shards is not None:
                judge["shards"] = shards
        path = self.tmp / ("judges_%s_%s.json" % (Path(run_dir).name, shards))
        path.write_text(json.dumps({"judges": judges}), encoding="utf-8")
        return path

    def score(self, run_dir, judges_path, cohort, extra=None):
        argv = [
            "score",
            "--items", str(SMOKE_ITEMS),
            "--models", str(FIX / "models_fake.json"),
            "--judges", str(judges_path),
            "--cohort", cohort,
            "--runs", str(run_dir),
            "--anchors", str(ANCHORS),
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
        ] + list(extra or [])
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = campaign.main(argv, gpu_probe=fake_gpu_probe())
        return code, buf.getvalue()

    def single_engine_file(self, run_dir, judge_id, family, fake_outputs, out):
        """The same judge over the same run in ONE process: the file the merge of
        the shards must reproduce byte for byte."""
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["--run-dir", str(run_dir), "--provider", "fake", "--judge-id", judge_id,
                 "--family", family, "--views", "prefix", "--items", str(SMOKE_ITEMS),
                 "--anchors", str(ANCHORS), "--fake-outputs", str(fake_outputs),
                 "--out", str(out)]
            )
        self.assertEqual(rc, 0, buf.getvalue())
        return out

    # -- the concurrency itself ---------------------------------------------

    def test_1_run_subprocesses_runs_the_children_at_the_same_time(self):
        cmds = [[sys.executable, "-c", "import time; time.sleep(0.6)"] for _ in range(2)]
        logs = [self.tmp / ("concurrent_%d.log" % i) for i in range(2)]
        start = time.monotonic()
        results = campaign.run_subprocesses(cmds, logs, REPO_ROOT, None)
        elapsed = time.monotonic() - start
        self.assertEqual([r[0] for r in results], [0, 0])
        self.assertTrue(all(p.is_file() for p in logs))
        self.assertLess(elapsed, 1.0, "two 0.6 s children took %.2f s: not concurrent" % elapsed)

    # -- end to end ----------------------------------------------------------

    def test_2_two_shards_per_judge_merge_into_the_judge_file(self):
        run_dir = Path(self.runs[0])
        judges_path = self.judges_file(run_dir, shards=2)
        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))
        code, out = self.score(run_dir, judges_path, "shardscore")
        self.assertEqual(code, 0, out)
        self.assertIn("(2 concurrent shards)", out)

        judges = json.loads(judges_path.read_text(encoding="utf-8"))["judges"]
        for judge in judges:
            jid = judge["judge_id"]
            merged = run_dir / ("judge_%s.jsonl" % jid)
            # after the merge the shard artifacts live in <run_dir>/shards/ only
            shards = [
                run_dir / "shards" / ("judge_%s.shard%dof2.jsonl" % (jid, k)) for k in (1, 2)
            ]
            self.assertTrue(merged.is_file(), out)
            self.assertTrue(meta_path_for(merged).is_file())
            for path in shards:
                self.assertTrue(path.is_file(), out)
                self.assertTrue(meta_path_for(path).is_file())
            self.assertEqual(
                sorted(p.name for p in run_dir.glob("judge_%s.shard*" % jid)), []
            )
            self.assertEqual(
                sorted(p.name for p in (run_dir / "shards").glob("judge_%s.*" % jid)),
                ["judge_%s.shard1of2.jsonl" % jid, "judge_%s.shard1of2.meta.json" % jid,
                 "judge_%s.shard2of2.jsonl" % jid, "judge_%s.shard2of2.meta.json" % jid],
            )
            n_merged = len(merged.read_text(encoding="utf-8").splitlines())
            n_shards = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in shards)
            self.assertEqual(n_merged, n_shards)
            # the merge reproduces the single-engine file byte for byte
            single = self.single_engine_file(
                run_dir, jid, judge["family"], judge["fake_outputs"],
                self.tmp / ("single_%s_%s.jsonl" % (jid, run_dir.name)),
            )
            self.assertEqual(merged.read_bytes(), single.read_bytes())
            meta = json.loads(meta_path_for(merged).read_text(encoding="utf-8"))
            self.assertEqual(meta["shards"], 2)
            self.assertEqual(meta["n_views"], n_merged)

        # the panel still ran over the merged files
        self.assertTrue((run_dir / "panel.jsonl").is_file())

        record = json.loads(
            one_campaign_record(self.out_root / "shardscore", "shardscore", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "completed")
        self.assertEqual(len(record["judge_runs"]), 2)
        for judge_run_record in record["judge_runs"]:
            self.assertEqual(judge_run_record["shards"], 2)
            self.assertEqual(len(judge_run_record["shard_files"]), 2)
            self.assertEqual(len(judge_run_record["shard_logs"]), 2)
            for path in judge_run_record["shard_files"] + judge_run_record["shard_logs"]:
                self.assertTrue(Path(path).is_file(), path)
            # the recorded shard paths are where the artifacts actually are now
            for path in judge_run_record["shard_files"]:
                self.assertEqual(Path(path).parent, run_dir / "shards")
            self.assertTrue(Path(judge_run_record["log"]).is_file())
        plan_judges = {j["judge_id"]: j for j in record["plan"]["judges"]}
        self.assertEqual(plan_judges["JF1"]["shards"], 2)
        # the stagger this batch used is part of the scoring record (0 here: see setUp)
        self.assertEqual(
            record["plan"]["shard_start_stagger_s"], campaign.SHARD_START_STAGGER_S
        )

        # one EXPERIMENTS row per judge, carrying both shard commands + the merge
        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows) - before, 3)  # two judges + one panel
        fields = dict(zip(campaign.EXPERIMENTS_HEADER, rows[-3]))
        self.assertTrue(fields["run"].endswith("__judge_JF1"))
        self.assertIn("; shards=2", fields["config"])
        command_lines = fields["command"].splitlines()
        self.assertEqual(len(command_lines), 3)
        self.assertIn("--shard 1/2", command_lines[0])
        self.assertIn("--shard 2/2", command_lines[1])
        # each shard command carries its own start delay (0 s each under setUp)
        self.assertIn("--start-delay-s 0", command_lines[0])
        self.assertIn("--start-delay-s 0", command_lines[1])
        self.assertIn("kyra.judge merge", command_lines[2])
        self.assertIn("--shards", command_lines[2])
        self.assertEqual(fields["status"], "completed")

    def test_3_existing_shard_file_is_refused(self):
        run_dir = Path(self.runs[1])
        stray = run_dir / "judge_JF1.shard2of2.jsonl"
        stray.write_text("", encoding="utf-8")
        self.addCleanup(lambda: stray.exists() and stray.unlink())
        code, out = self.score(run_dir, self.judges_file(run_dir, shards=2), "shardstray")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("judge_JF1.shard2of2.jsonl", out)
        self.assertFalse((run_dir / "judge_JF1.jsonl").exists())

    def test_3b_a_shard_left_in_the_shards_directory_is_refused_too(self):
        run_dir = Path(self.runs[4])
        stored = run_dir / "shards"
        stored.mkdir(exist_ok=True)
        stale = stored / "judge_JF1.shard1of2.jsonl"
        stale.write_text("", encoding="utf-8")
        self.addCleanup(shutil.rmtree, stored, True)
        code, out = self.score(run_dir, self.judges_file(run_dir, shards=2), "shardstored")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn(str(stale), out)
        self.assertFalse((run_dir / "judge_JF1.jsonl").exists())

    def test_4_shards_1_is_exactly_the_previous_command_and_config(self):
        run_dir = Path(self.runs[2])
        judges_path = self.judges_file(run_dir, shards=1)
        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))
        code, out = self.score(run_dir, judges_path, "shardone")
        self.assertEqual(code, 0, out)
        record = json.loads(
            one_campaign_record(self.out_root / "shardone", "shardone", "_scoring")
            .read_text(encoding="utf-8")
        )
        plan_judges = {j["judge_id"]: j for j in record["plan"]["judges"]}
        self.assertNotIn("shards", plan_judges["JF1"])
        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows) - before, 3)
        fields = dict(zip(campaign.EXPERIMENTS_HEADER, rows[-3]))
        expected_config = (
            "judge=JF1; family=judge_x; provider=fake; model=fake/judge-1; views=prefix; "
            "items=%s; anchors=%s; anchors_sha256=%s; evaluated_family=%s; "
            "gpu=%s; run_dir=%s"
            % (SMOKE_ITEMS, ANCHORS, sha256(ANCHORS),
               record["plan"]["runs"][0]["evaluated_family"], record["gpu"]["chosen"], run_dir)
        )
        self.assertEqual(fields["config"], expected_config)
        self.assertNotIn("shard_start_stagger_s", record["plan"])
        self.assertNotIn("--shard", fields["command"])
        self.assertNotIn("--start-delay-s", fields["command"])
        self.assertEqual(len(fields["command"].splitlines()), 1)
        self.assertEqual(
            [p.name for p in run_dir.glob("judge_*.shard*")], []
        )
        judge_run_record = record["judge_runs"][0]
        self.assertEqual(judge_run_record["shards"], 1)
        self.assertEqual(judge_run_record["shard_files"], [])

    def test_5_a_failing_shard_stops_the_batch_before_the_merge(self):
        """An unusable --fake-outputs file makes every shard child exit 4: the
        batch stops, no merged judge file is written, and the shard logs stay."""
        run_dir = Path(self.runs[3])
        judges_path = self.judges_file(run_dir, shards=2, keep={"JF1"})
        doc = json.loads(judges_path.read_text(encoding="utf-8"))
        broken = self.tmp / "fake_outputs_broken.json"
        broken.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        doc["judges"][0]["fake_outputs"] = str(broken)
        judges_path.write_text(json.dumps(doc), encoding="utf-8")

        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))
        code, out = self.score(run_dir, judges_path, "shardfail")
        self.assertEqual(code, campaign.EXIT_RUN_FAILED, out)
        self.assertFalse((run_dir / "judge_JF1.jsonl").exists())
        self.assertFalse((run_dir / "panel.jsonl").exists())
        record = json.loads(
            one_campaign_record(self.out_root / "shardfail", "shardfail", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "failed")
        judge_run_record = record["judge_runs"][0]
        self.assertEqual(judge_run_record["status"], "failed")
        self.assertEqual(judge_run_record["shards"], 2)
        self.assertIn("shard 1/2 failed", judge_run_record["failure"])
        for path in judge_run_record["shard_logs"]:
            self.assertTrue(Path(path).is_file(), path)
        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows) - before, 1)
        fields = dict(zip(campaign.EXPERIMENTS_HEADER, rows[-1]))
        self.assertEqual(fields["status"], "failed")
        self.assertIn("; shards=2", fields["config"])

    def test_6_judge_command_and_merge_command_shapes(self):
        judge = {
            "judge_id": "J1", "family": "lg", "provider": "vllm",
            "model_path": "/models/j1", "gpu_memory_utilization": 0.42,
            "batch_size": 1, "shards": 2, "fake_outputs": None,
        }
        cmd = campaign.judge_command(
            judge, Path("/runs/r1"), Path("items.jsonl"),
            campaign.shard_out_path(Path("/runs/r1"), "J1", 2, 2), None, shard=(2, 2),
        )
        self.assertIn("--shard", cmd)
        self.assertEqual(cmd[cmd.index("--shard") + 1], "2/2")
        self.assertEqual(cmd[cmd.index("--out") + 1], "/runs/r1/judge_J1.shard2of2.jsonl")
        self.assertEqual(cmd[cmd.index("--batch-size") + 1], "1")
        plain = campaign.judge_command(
            judge, Path("/runs/r1"), Path("items.jsonl"), Path("/runs/r1/judge_J1.jsonl"), None
        )
        self.assertNotIn("--shard", plain)
        merge = campaign.judge_merge_command(
            Path("/runs/r1"),
            [campaign.shard_out_path(Path("/runs/r1"), "J1", k, 2) for k in (1, 2)],
            Path("/runs/r1/judge_J1.jsonl"),
        )
        self.assertEqual(merge[1:4], ["-m", "kyra.judge", "merge"])
        self.assertEqual(merge[merge.index("--views") + 1], "prefix")
        self.assertEqual(
            merge[merge.index("--shards") + 1:merge.index("--out")],
            ["/runs/r1/judge_J1.shard1of2.jsonl", "/runs/r1/judge_J1.shard2of2.jsonl"],
        )

    def test_8_a_failed_merge_leaves_the_shard_files_in_the_run_dir_root(self):
        """A stale judge file makes `kyra.judge merge` refuse: the shards must
        stay exactly where they are (and out of <run_dir>/shards/) for diagnosis."""
        run_dir = Path(self.runs[5])
        judge = campaign.load_judges(self.judges_file(run_dir, shards=2, keep={"JF1"}))[0]
        out_path = run_dir / "judge_JF1.jsonl"
        out_path.write_text("stale\n", encoding="utf-8")
        outcome = campaign.run_one_judge(
            judge, run_dir, SMOKE_ITEMS, out_path, ANCHORS, "failmerge",
            self.tmp / "failmerge_logs", REPO_ROOT, None,
        )
        self.assertNotEqual(outcome["code"], 0)
        self.assertEqual(len(outcome["shard_files"]), 2)
        for path in outcome["shard_files"]:
            self.assertEqual(Path(path).parent, run_dir)
            self.assertTrue(Path(path).is_file())
            self.assertTrue(meta_path_for(Path(path)).is_file())
        self.assertFalse((run_dir / "shards").exists())
        self.assertEqual(out_path.read_text(encoding="utf-8"), "stale\n")
        for path in outcome["shard_files"]:
            meta_path_for(Path(path)).unlink()
            Path(path).unlink()
        out_path.unlink()

    def test_7_load_judges_validates_shards(self):
        path = self.tmp / "judges_bad_shards.json"
        for bad in (0, -1, 1.5, True, "2"):
            path.write_text(
                json.dumps({"judges": [{"judge_id": "J1", "family": "lg",
                                        "provider": "fake", "shards": bad}]}),
                encoding="utf-8",
            )
            with self.assertRaises(campaign.CampaignError):
                campaign.load_judges(path)
        path.write_text(
            json.dumps({"judges": [{"judge_id": "J1", "family": "lg", "provider": "fake"}]}),
            encoding="utf-8",
        )
        self.assertEqual(campaign.load_judges(path)[0]["shards"], 1)


# -- staggered shard starts ---------------------------------------------------


class TestShardStagger(unittest.TestCase):
    """Shard k builds its engine (k-1)*45 s after shard 1 (2026-09-23).

    Two engines that probe free GPU memory in the same second collide, and that
    collision used to be written into the first views of both shards. This class
    uses the REAL constant (TestCampaignShards sets it to 0 for its end-to-end
    runs), so a change of the 45 s stagger has to be made here too.
    """

    JUDGE = {
        "judge_id": "J2", "family": "qwen", "provider": "vllm",
        "model_path": "/models/j2", "gpu_memory_utilization": 0.42,
        "batch_size": None, "shards": 2, "fake_outputs": None,
    }

    def cmd(self, shard):
        run_dir = Path("/runs/r1")
        out = (
            campaign.shard_out_path(run_dir, "J2", shard[0], shard[1])
            if shard else run_dir / "judge_J2.jsonl"
        )
        return campaign.judge_command(
            self.JUDGE, run_dir, Path("items.jsonl"), out, None, shard=shard
        )

    def test_the_stagger_constant_is_45_seconds(self):
        self.assertEqual(campaign.SHARD_START_STAGGER_S, 45)

    def test_the_first_shard_starts_now_and_the_second_45_seconds_later(self):
        first, second = self.cmd((1, 2)), self.cmd((2, 2))
        self.assertEqual(first[first.index("--start-delay-s") + 1], "0")
        self.assertEqual(second[second.index("--start-delay-s") + 1], "45")
        self.assertEqual(first[first.index("--shard") + 1], "1/2")
        self.assertEqual(second[second.index("--shard") + 1], "2/2")

    def test_three_shards_are_spread_45_seconds_apart(self):
        delays = []
        for k in (1, 2, 3):
            cmd = self.cmd((k, 3))
            delays.append(cmd[cmd.index("--start-delay-s") + 1])
        self.assertEqual(delays, ["0", "45", "90"])

    def test_an_unsharded_judge_gets_no_delay_flag_at_all(self):
        for shard in (None, (1, 1)):
            cmd = self.cmd(shard)
            self.assertNotIn("--start-delay-s", cmd)
            self.assertNotIn("--shard", cmd)

    def test_the_delay_reaches_the_child_from_judges_json(self):
        """judges.json "shards": 2 -> the second child's argv carries 45 s."""
        tmp = Path(tempfile.mkdtemp(prefix="stagger_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        path = tmp / "judges.json"
        path.write_text(
            json.dumps({"judges": [{"judge_id": "J2", "family": "qwen",
                                    "provider": "vllm", "model_path": "/models/j2",
                                    "shards": 2}]}),
            encoding="utf-8",
        )
        judge = campaign.load_judges(path)[0]
        self.assertEqual(judge["shards"], 2)
        cmds = [
            campaign.judge_command(
                judge, Path("/runs/r1"), Path("items.jsonl"),
                campaign.shard_out_path(Path("/runs/r1"), "J2", k, 2), None, shard=(k, 2),
            )
            for k in (1, 2)
        ]
        self.assertIn("--start-delay-s 0", " ".join(cmds[0]))
        self.assertIn("--start-delay-s 45", " ".join(cmds[1]))
        # and the flag the child parses really is the judge CLI's own flag
        args = judge_build_parser().parse_args(
            ["--run-dir", "/runs/r1", "--judge-id", "J2", "--family", "qwen",
             "--start-delay-s", "45"]
        )
        self.assertEqual(args.start_delay_s, 45.0)
        self.assertEqual(
            judge_build_parser().parse_args(
                ["--run-dir", "/runs/r1", "--judge-id", "J2", "--family", "qwen"]
            ).start_delay_s,
            0.0,
        )


# -- the N3 consumer ----------------------------------------------------------


class TestN3IgnoresShardFiles(unittest.TestCase):
    """kyra.analysis.n3_reliability globs judge_*.jsonl per run directory: a shard
    file there would be counted as an extra judge, so it is an error, and the
    merged-away shards under <run_dir>/shards/ are simply out of sight."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kyra_n3_shard_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        for judge_id in ("J1", "J2"):
            (self.run_dir / ("judge_%s.jsonl" % judge_id)).write_text("", encoding="utf-8")

    def discover(self):
        from kyra.analysis.n3_reliability import discover_judge_files

        return discover_judge_files([str(self.run_dir)])

    def test_the_merged_judge_files_are_found(self):
        self.assertEqual(
            [Path(p).name for p in self.discover()], ["judge_J1.jsonl", "judge_J2.jsonl"]
        )

    def test_a_shard_file_in_the_run_dir_root_is_an_error_naming_it(self):
        stray = self.run_dir / "judge_J1.shard2of2.jsonl"
        stray.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.discover()
        msg = str(ctx.exception)
        self.assertIn("judge_J1.shard2of2.jsonl", msg)
        self.assertIn("merge did not complete", msg)

    def test_shard_files_under_the_shards_subdirectory_are_ignored(self):
        stored = self.run_dir / "shards"
        stored.mkdir()
        for k in (1, 2):
            (stored / ("judge_J1.shard%dof2.jsonl" % k)).write_text("", encoding="utf-8")
            (stored / ("judge_J1.shard%dof2.meta.json" % k)).write_text("{}", encoding="utf-8")
        self.assertEqual(
            [Path(p).name for p in self.discover()], ["judge_J1.jsonl", "judge_J2.jsonl"]
        )


if __name__ == "__main__":
    unittest.main()
