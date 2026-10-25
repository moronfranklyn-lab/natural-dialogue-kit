#!/usr/bin/env python3
"""Offline checks for this package, not a persona benchmark or full secret audit."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

from render_prompt import render
from review_runs import analyze, validate_cases

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    for path in sorted((ROOT / "configs").glob("*.json")):
        try:
            render(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    try:
        expected = validate_cases(json.loads((ROOT / "evals/cases.json").read_text(encoding="utf-8")))
        report = analyze(json.loads((ROOT / "examples/demo-run.json").read_text(encoding="utf-8")), expected)
        if report["kind"] != "synthetic_demo" or report["missing"] or len(report["failures"]) != 1:
            errors.append("demo must cover cases and retain exactly one intentional error")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    # File targets only; anchors, remote URLs, and rendered Mermaid are not checked.
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0])
            if target and not (path.parent / target).exists():
                errors.append(f"broken local file link: {path.relative_to(ROOT)} -> {target}")
    skill = ROOT / "skills/natural-dialogue/SKILL.md"
    content = skill.read_text(encoding="utf-8")
    if not content.startswith("---\nname: natural-dialogue\ndescription:"):
        errors.append("Skill frontmatter missing name/description")
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name.startswith(".env"):
            errors.append("environment file present: " + str(path.relative_to(ROOT)))
        text = path.read_text(encoding="utf-8")
        if re.search(r"/(?:Volumes|Users|home/ubuntu)/[A-Za-z0-9_\u4e00-\u9fff]", text):
            errors.append("private absolute path: " + str(path.relative_to(ROOT)))
        if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)", text):
            errors.append("potential secret: " + str(path.relative_to(ROOT)))
    for error in errors:
        print("FAIL " + error, file=sys.stderr)
    if errors:
        return 1
    print("PASS: configs, cases, deliberate demo error, local file links, Skill frontmatter, basic disclosure scan")
    print("No model calls; no naturalness or business-runtime result inferred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
