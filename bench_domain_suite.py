from __future__ import annotations

import json
import argparse
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from benchmark_domains import DOMAIN_SCENARIOS


def tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [token for item in value.values() for token in tokens(item)]
    if isinstance(value, list):
        return [token for item in value for token in tokens(item)]
    return [str(value)]


def run_case(scenario, mode: str, oracle: dict[str, Any]) -> dict[str, Any]:
    if mode == "normal":
        toolsets = "browser,terminal"
        instruction = "Use browser_exec for all navigation."
    else:
        toolsets = "neeble"
        instruction = "Call the high-level neeble tool exactly once. Do not use browser_exec, web search, APIs, curl, or extraction tools. Use its returned trajectory/state to answer."
    prompt = f"""{scenario.prompt}
Start at {scenario.start_url}.
{instruction}
This is a timed benchmark. Return a concise answer with observed values, URLs, and uncertainty if the task escalated. Do not guess."""
    started = time.perf_counter()
    process = subprocess.run(["hermes", "chat", "-q", prompt, "--toolsets", toolsets, "-Q"],
                             capture_output=True, text=True, timeout=900)
    output = (process.stdout + "\n" + process.stderr).strip()
    checks = {key: all(token in output for token in tokens(oracle[key])) for key in scenario.required_values}
    return {"mode": mode, "elapsed_ms": (time.perf_counter() - started) * 1000,
            "exit_code": process.returncode, "answer_verified": all(checks.values()),
            "checks": checks, "session_id": (re.search(r"session_id:\s*(\S+)", output) or [None, None])[1],
            "output_tail": output[-5000:]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', action='append', help='Run only this scenario name (repeatable)')
    parser.add_argument('--mode', choices=('normal', 'neeble'), action='append', help='Run only this track (repeatable)')
    args = parser.parse_args()
    selected = [s for s in DOMAIN_SCENARIOS if not args.scenario or s.name in args.scenario]
    modes = args.mode or ['normal', 'neeble']
    report = {"scenarios": []}
    for scenario in selected:
        oracle = scenario.oracle()
        rows = [run_case(scenario, mode, oracle) for mode in modes]
        report["scenarios"].append({"name": scenario.name, "start_url": scenario.start_url,
                                    "oracle": oracle, "runs": rows})
        print(json.dumps({"name": scenario.name, "oracle": oracle,
                          "runs": [{k: v for k, v in row.items() if k != "output_tail"} for row in rows]}, indent=2))
    Path("results").mkdir(exist_ok=True)
    Path("results/cross-domain-hermes-neeble-suite.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
