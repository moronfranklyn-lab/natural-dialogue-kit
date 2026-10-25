"""Tests cover evidence integrity, failures, and deterministic configuration rendering."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_prompt import render
from review_runs import analyze, validate_cases


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((ROOT / "evals/cases.json").read_text())
        self.expected = validate_cases(self.cases)
        self.run = json.loads((ROOT / "examples/demo-run.json").read_text())

    def test_demo_cannot_hide_failure(self):
        report = analyze(self.run, self.expected)
        self.assertEqual(report["kind"], "synthetic_demo")
        self.assertEqual(report["failures"][0]["case_id"], "tutorial")
        self.assertEqual(report["missing"], [])

    def test_missing_cases_reported(self):
        self.run["results"].pop()
        self.assertIn("explicit-memory", analyze(self.run, self.expected)["missing"])

    def test_duplicate_results_rejected(self):
        self.run["results"].append(copy.deepcopy(self.run["results"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            analyze(self.run, self.expected)

    def test_unknown_results_rejected(self):
        self.run["results"][0]["case_id"] = "invented"
        with self.assertRaisesRegex(ValueError, "unknown"):
            analyze(self.run, self.expected)

    def test_success_cannot_contain_error(self):
        self.run["results"][0]["error"] = {"code": "E", "message": "failed"}
        with self.assertRaisesRegex(ValueError, "null error"):
            analyze(self.run, self.expected)

    def test_model_run_requires_provenance(self):
        self.run["kind"] = "model_run"
        with self.assertRaisesRegex(ValueError, "prompt_sha256|parameters"):
            analyze(self.run, self.expected)

    def test_human_rejection_kept_separate_from_execution(self):
        row = self.run["results"][0]
        row["review"] = {"decision": "reject", "reason": "context mismatch"}
        report = analyze(self.run, self.expected)
        self.assertEqual(report["human_review"]["reject"], 1)
        self.assertEqual(report["status"]["ok"], 11)

    def test_review_needs_reason(self):
        self.run["results"][0]["review"]["decision"] = "accept"
        with self.assertRaisesRegex(ValueError, "reason"):
            analyze(self.run, self.expected)

    def test_success_needs_final_answer(self):
        self.run["results"][0]["turns"] = [{"role": "user", "content": "?"}]
        with self.assertRaisesRegex(ValueError, "end with assistant"):
            analyze(self.run, self.expected)

    def test_duplicate_case_definition_rejected(self):
        self.cases["cases"].append(self.cases["cases"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_cases(self.cases)

    def test_render_stable_and_boundary_preserved(self):
        config = json.loads((ROOT / "configs/neutral-template.json").read_text())
        first = render(config)
        self.assertEqual(first, render(config))
        self.assertIn(config["boundaries"][0], first)
        self.assertIn(config["examples"][0]["assistant"][0], first)

    def test_bad_config_rejected(self):
        config = json.loads((ROOT / "configs/neutral-template.json").read_text())
        config["examples"][0]["assistant"] = []
        with self.assertRaises(ValueError):
            render(config)


if __name__ == "__main__":
    unittest.main()
