#!/usr/bin/env python3
"""Validate run records and report observations; never infer naturalness."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = {"pending", "accept", "reject", "tie", "neither"}


def validate_cases(data):
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("cases must contain a non-empty cases list")
    ids = []
    for case in data["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not case["case_id"].strip():
            raise ValueError("invalid case_id in cases")
        if case["case_id"] in ids:
            raise ValueError("duplicate case_id in cases: " + case["case_id"])
        ids.append(case["case_id"])
        validate_turns(case.get("messages"))
        if not isinstance(case.get("observe"), list) or not case["observe"]:
            raise ValueError("case needs observation points")
    return ids


def validate_turns(turns):
    if not isinstance(turns, list) or not turns:
        raise ValueError("turns/messages must be a non-empty list")
    for turn in turns:
        if not isinstance(turn, dict) or turn.get("role") not in {"system", "user", "assistant", "tool"}:
            raise ValueError("invalid turn role")
        if not isinstance(turn.get("content"), str) or not turn["content"].strip():
            raise ValueError("turn content must be a non-empty string")


def analyze(run, expected):
    if not isinstance(run, dict) or run.get("kind") not in {"synthetic_demo", "model_run"}:
        raise ValueError("kind must be synthetic_demo or model_run")
    if not isinstance(run.get("run_id"), str) or not run["run_id"].strip():
        raise ValueError("run_id must be a non-empty string")
    meta = run.get("metadata")
    if not isinstance(meta, dict):
        raise ValueError("metadata must be an object")
    if run["kind"] == "model_run":
        for key in ("model", "persona_version", "generated_at"):
            if not isinstance(meta.get(key), str) or not meta[key].strip():
                raise ValueError("model_run metadata missing " + key)
        if not isinstance(meta.get("parameters"), dict):
            raise ValueError("model_run metadata needs parameters object")
        if not isinstance(meta.get("prompt_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", meta["prompt_sha256"]):
            raise ValueError("prompt_sha256 must be lowercase SHA-256 hex")
    results = run.get("results")
    if not isinstance(results, list):
        raise ValueError("results must be a list")
    seen, counts, reviews, failures = set(), Counter(), Counter(), []
    last_replies = defaultdict(list)
    for row in results:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str):
            raise ValueError("result must have case_id")
        cid = row["case_id"]
        if cid in seen:
            raise ValueError("duplicate result case_id: " + cid)
        if cid not in expected:
            raise ValueError("unknown result case_id: " + cid)
        seen.add(cid)
        status = row.get("status")
        if status not in {"ok", "error"}:
            raise ValueError("invalid status: " + cid)
        if "error" not in row:
            raise ValueError("error field required: " + cid)
        if status == "ok" and row["error"] is not None:
            raise ValueError("ok result must have null error: " + cid)
        if status == "error":
            err = row["error"]
            if not isinstance(err, dict) or any(not isinstance(err.get(k), str) or not err[k].strip() for k in ("code", "message")):
                raise ValueError("error result needs code/message: " + cid)
            failures.append({"case_id": cid, "error": err})
        validate_turns(row.get("turns"))
        assistants = [t["content"] for t in row["turns"] if t["role"] == "assistant"]
        if status == "ok":
            if row["turns"][-1]["role"] != "assistant":
                raise ValueError("ok result must end with assistant: " + cid)
            last_replies[assistants[-1]].append(cid)
        review = row.get("review")
        if not isinstance(review, dict) or review.get("decision") not in DECISIONS or not isinstance(review.get("reason"), str):
            raise ValueError("invalid review decision/reason: " + cid)
        if review["decision"] != "pending" and not review["reason"].strip():
            raise ValueError("completed review needs reason: " + cid)
        reviews[review["decision"]] += 1
        counts[status] += 1
    return {
        "run_id": run["run_id"], "kind": run["kind"],
        "expected": len(expected), "present": len(seen),
        "missing": sorted(set(expected) - seen),
        "status": dict(counts), "human_review": dict(reviews),
        "identical_last_replies": [ids for ids in last_replies.values() if len(ids) > 1],
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--cases", type=Path, default=ROOT / "evals/cases.json")
    args = parser.parse_args(argv)
    try:
        expected = validate_cases(json.loads(args.cases.read_text(encoding="utf-8")))
        report = analyze(json.loads(args.run.read_text(encoding="utf-8")), expected)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["missing"] or report["failures"] else 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
