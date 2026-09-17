from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

ACTIONS = [
    "goto", "back", "forward", "reload", "new_tab", "close_tab",
    "snapshot", "screenshot", "get_url", "get_title", "get_text", "find",
    "click", "double_click", "hover", "drag", "scroll", "scroll_into_view",
    "type", "press", "key_down", "key_up", "clear", "paste",
    "select_option", "check", "uncheck", "upload_file", "submit",
    "switch_tab", "new_window", "close_window", "wait", "wait_for_selector",
    "wait_for_navigation", "wait_for_network_idle", "cookies", "local_storage",
    "set_cookie", "retry", "refresh_snapshot", "escalate",
]


def mock_decide(prompt: str) -> dict:
    return {"name": "snapshot", "arguments": {}}


def run(args: argparse.Namespace) -> None:
    cases = max(1, args.cases)
    decide = mock_decide
    if args.backend != "mock":
        raise SystemExit("Only --backend mock is wired in this initial harness; model adapters are next.")
    latencies = []
    valid = 0
    for i in range(cases):
        start = time.perf_counter_ns()
        result = decide(f"case-{i}")
        elapsed = (time.perf_counter_ns() - start) / 1e6
        latencies.append(elapsed)
        valid += int(result.get("name") in ACTIONS and isinstance(result.get("arguments"), dict))
    total = sum(latencies) / 1000
    summary = {
        "backend": args.backend,
        "cases": cases,
        "valid_actions": valid,
        "valid_rate": valid / cases,
        "decision_ms_mean": statistics.mean(latencies),
        "decision_ms_p50": statistics.median(latencies),
        "actions_per_minute": cases / (total / 60) if total else None,
        "note": "mock harness result; not a model benchmark",
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(summary, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(prog="babench")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--backend", choices=["mock", "needle", "openai"], default="mock")
    run_parser.add_argument("--cases", type=int, default=100)
    run_parser.add_argument("--output")
    run_parser.add_argument("--layers", type=int, default=8)
    args = parser.parse_args()
    run(args)
