from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path


def hf_oracle() -> dict[str, object]:
    def fetch(params: str):
        with urllib.request.urlopen("https://huggingface.co/api/models?" + params, timeout=60) as r:
            return json.load(r)
    newest = fetch("author=Qwen&limit=1&sort=createdAt&direction=-1")[0]
    popular = fetch("author=Qwen&limit=1&sort=downloads&direction=-1")[0]
    all_models = fetch("author=Qwen&limit=1000")
    return {
        "latest_id": newest["id"],
        "latest_created_at": newest.get("createdAt"),
        "popular_id": popular["id"],
        "popular_downloads": popular.get("downloads"),
        "total_models": len(all_models),
    }


def run(mode: str, oracle: dict[str, object]) -> dict[str, object]:
    if mode == "normal":
        tools = "browser,terminal"
        routing = "Use browser_exec for all browser navigation and page inspection."
    else:
        tools = "browser,neeble,terminal"
        routing = (
            "Use neeble for routine browser actions. Before each neeble call, obtain the current browser state; "
            "execute only its verified legal action with browser_exec, and return complex reasoning or ambiguity to yourself."
        )
    prompt = f"""Research this live Hugging Face task using browser navigation only. Do not use web_search, web_extract, curl, or APIs for the answer. {routing}
Open https://huggingface.co/models?author=Qwen and determine:
1. The newest model released by Qwen.
2. The most-downloaded Qwen model and its download count.
3. The total number of Qwen models shown by the author listing.
Return the three answers with model IDs, the observed values, and the Hugging Face URLs used. Do not guess. Keep going until all three are verified.
"""
    started = time.perf_counter()
    proc = subprocess.run(["hermes", "chat", "-q", prompt, "--toolsets", tools, "-Q"],
                          capture_output=True, text=True, timeout=900)
    elapsed_ms = (time.perf_counter() - started) * 1000
    output = (proc.stdout + "\n" + proc.stderr).strip()
    session_match = re.search(r"session_id:\s*(\S+)", output)
    session_id = session_match.group(1) if session_match else None
    checks = {
        "latest_id": str(oracle["latest_id"]) in output,
        "popular_id": str(oracle["popular_id"]) in output,
        "total_models": str(oracle["total_models"]) in output,
    }
    return {
        "mode": mode,
        "elapsed_ms": elapsed_ms,
        "exit_code": proc.returncode,
        "session_id": session_id,
        "answer_verified_against_oracle": all(checks.values()),
        "checks": checks,
        "output_tail": output[-4000:],
    }


def session_tool_calls(session_id: str | None) -> list[str]:
    if not session_id:
        return []
    subprocess.run(["hermes", "sessions", "export", "/tmp/hf-bench-sessions.json", "--force"],
                   capture_output=True, text=True, timeout=120, check=True)
    for line in Path("/tmp/hf-bench-sessions.json").read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("id") != session_id:
            continue
        names = []
        for message in record.get("messages", []):
            if message.get("role") == "tool" and message.get("tool_name"):
                names.append(message["tool_name"])
            for call in message.get("tool_calls") or []:
                fn = (call.get("function") or {}).get("name")
                if fn:
                    names.append(fn)
        return names
    return []


def main() -> None:
    oracle = hf_oracle()
    runs = [run("normal", oracle), run("neeble", oracle)]
    for row in runs:
        sid = row.get("session_id")
        row["tool_calls"] = session_tool_calls(sid if isinstance(sid, str) else None)
    report = {"oracle": oracle, "runs": runs}
    Path("results").mkdir(exist_ok=True)
    Path("results/huggingface-qwen-hermes-comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"oracle": oracle, "runs": [{k: v for k, v in r.items() if k != "output_tail"} for r in runs]}, indent=2))


if __name__ == "__main__":
    main()
