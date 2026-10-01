import json
import tempfile
import unittest
from pathlib import Path

from kyra.analysis import posthoc_hcx_plan_v1 as hp


class TestRule(unittest.TestCase):
    def test_classify_rule(self):
        self.assertTrue(hp.classify("사용자가 학교 이야기를 하고 있다. 공감하며 답한다.")["flagged"])
        self.assertTrue(hp.classify("  The user is sad.")["start"])
        self.assertTrue(hp.classify("친구 이야기를 들었어요. 이제 답변을 구성해 보겠다.")["plan"])
        late = "가" * 310 + " 답변을 구성해야 한다"
        self.assertFalse(hp.classify(late)["flagged"])
        self.assertFalse(hp.classify("그런 일이 있었구나. 많이 힘들었겠다.")["flagged"])
        self.assertFalse(hp.classify("나는 사용자가 아니라 친구야.")["start"])


class TestScan(unittest.TestCase):
    def test_scan_counts_and_bad_input(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            run = tmp / "raw" / "m" / "main" / "s1"
            run.mkdir(parents=True)
            rows = [{"item_id": "a", "turn_index": 0, "model_text": "사용자는 위로가 필요하다."},
                    {"item_id": "a", "turn_index": 1, "model_text": "괜찮아. 같이 생각해 보자."},
                    {"item_id": "b", "turn_index": 0, "model_text": "지침에 따라 안전하게 답한다."}]
            (run / "responses.jsonl").write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            # no MARKER -> no run directory -> exit 4
            self.assertEqual(hp.main(["--raw-root", str(tmp / "raw"), "--out-root", str(tmp / "out")]), 4)
            (run / "MARKER").write_text("ok\n")
            r = hp.scan_run(run)
            self.assertEqual((r["n_replies"], r["n_start"], r["n_plan_first300"], r["n_flagged"]), (3, 1, 1, 2))
            self.assertEqual(r["flagged_keys"], [["a", 0], ["b", 0]])
            self.assertEqual(hp.main(["--raw-root", str(tmp / "raw"), "--out-root", str(tmp / "ok")]), 0)
            # a row without model_text -> exit 4
            (run / "responses.jsonl").write_text(json.dumps({"item_id": "c", "turn_index": 0}) + "\n",
                                                 encoding="utf-8")
            self.assertEqual(hp.main(["--raw-root", str(tmp / "raw"), "--out-root", str(tmp / "out2")]), 4)


if __name__ == "__main__":
    unittest.main()
