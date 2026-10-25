#!/usr/bin/env python3
"""Render only the persona component; no API or network calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    for key in ("id", "status", "identity", "relationship"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    for key in ("voice", "boundaries"):
        values = config.get(key)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{key} must be a non-empty list")
        if any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"{key} entries must be non-empty strings")
    examples = config.get("examples")
    if not isinstance(examples, list) or not examples:
        raise ValueError("examples must be a non-empty list")
    for example in examples:
        if not isinstance(example, dict) or not isinstance(example.get("user"), str) or not example["user"].strip():
            raise ValueError("each example needs a non-empty user string")
        replies = example.get("assistant")
        if not isinstance(replies, list) or not replies or any(not isinstance(r, str) or not r.strip() for r in replies):
            raise ValueError("each example needs non-empty assistant strings")


def render(config):
    validate_config(config)
    blocks = [
        "以下只定义默认角色表达，不替代应用的事实、权限、工具和业务契约。",
        "示例表示可能的反应，不要求复用措辞或消息形状。",
        "<identity>", config["identity"], config["relationship"], "</identity>",
        "<voice>", *config["voice"], "</voice>",
        "<boundaries>", *config["boundaries"], "</boundaries>", "<examples>",
    ]
    for ex in config["examples"]:
        blocks.append("用户：" + ex["user"])
        blocks.extend("角色：" + reply for reply in ex["assistant"])
        blocks.append("")
    blocks.append("</examples>")
    return "\n".join(blocks) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, help="write new UTF-8 prompt file; existing files are not overwritten")
    args = parser.parse_args(argv)
    try:
        raw = args.config.read_bytes()
        prompt = render(json.loads(raw))
        if args.output:
            with args.output.open("x", encoding="utf-8") as f:
                f.write(prompt)
        else:
            sys.stdout.write(prompt)
        print("config_sha256=" + hashlib.sha256(raw).hexdigest(), file=sys.stderr)
        print("prompt_sha256=" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(), file=sys.stderr)
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
