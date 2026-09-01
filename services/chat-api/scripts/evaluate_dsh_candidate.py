#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from dsh_upgrade import DshCandidateEvaluator
from dsh_upgrade.reporting import write_report


def executable(value: str) -> str:
    resolved = shutil.which(value)
    if resolved is None:
        raise argparse.ArgumentTypeError(f"executable not found: {value}")
    return resolved


def main() -> int:
    chat_api_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Evaluate a DSH npm candidate in isolation without mutating the active Runtime Host.",
    )
    parser.add_argument("candidate", nargs="?", default="latest", help="exact npm version or dist-tag")
    parser.add_argument("--node", default="node")
    parser.add_argument("--pnpm", default="pnpm")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--output", type=Path, default=Path("/tmp/askai-dsh-upgrade-evaluation"))
    args = parser.parse_args()

    evaluator = DshCandidateEvaluator(
        chat_api_root=chat_api_root,
        node=executable(args.node),
        pnpm=executable(args.pnpm),
        npm=executable(args.npm),
    )
    report = evaluator.evaluate(args.candidate)
    json_path, markdown_path = write_report(report, args.output.resolve())
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    print(f"Contract ready: {report.decision['contract_ready']}")
    print("Release ready: false (full application and packaged smoke admission still required)")
    return 0 if report.decision["contract_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
