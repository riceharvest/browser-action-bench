from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from benchmark_scenarios import SCENARIOS


def _tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        return [token for item in value for token in _tokens(item)]
    return [str(value)]


def run_case(scenario, mode: str, oracle: dict[str, Any]) -> dict[str, Any]:
    if mode == "normal":
        toolsets = "browser,terminal"
        route = "Use browser_exec for all navigation and page inspection."
    else:
        toolsets = "neeble,terminal"
        route = (
            "Call the high-level neeble tool exactly once to own the browser trajectory. Do not use browser_exec. "
            "Do not use web_search, web_extract, curl, or APIs. Let Neeble return a verified state or escalation."
        )
    prompt = f"""{scenario.prompt}
{route}
This is a benchmark. Return a concise final answer with observed values and URLs. Do not guess."""
    started = time.perf_counter()
    proc = subprocess.run(["hermes", "chat", "-q", prompt, "--toolsets", toolsets, "-Q"],
                          capture_output=True, text=True, timeout=900)
    output = (proc.stdout + "\n" + proc.stderr).strip()
    checks = {key: all(token in output for token in _tokens(oracle[key])) for key in scenario.required_values}
    return {
        "scenario": scenario.name,
        "mode": mode,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "exit_code": proc.returncode,
        "answer_verified_against_live_oracle": all(checks.values()),
        "checks": checks,
        "output_tail": output[-5000:],
        "session_id": (re.search(r"session_id:\s*(\S+)", output) or [None, None])[1],
    }


def main() -> None:
    report: dict[str, Any] = {"scenarios": []}
    for scenario in SCENARIOS:
        oracle = scenario.oracle()
        rows = [run_case(scenario, mode, oracle) for mode in ("normal", "neeble")]
        report["scenarios"].append({"name": scenario.name, "oracle": oracle, "runs": rows})
        print(json.dumps({"scenario": scenario.name, "oracle": oracle,
                          "runs": [{k: v for k, v in row.items() if k != "output_tail"} for row in rows]}, indent=2))
    Path("results").mkdir(exist_ok=True)
    Path("results/huggingface-qwen-suite.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
