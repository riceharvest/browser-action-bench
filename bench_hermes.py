"""Real Hermes -> Neeble end-to-end benchmark with owned fixture resources."""
from __future__ import annotations

import http.server
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULT = ROOT / "results/hermes-neeble-e2e.json"


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'''<!doctype html><title>step 1</title><script>
function advance(id,title,label){const old=document.getElementById(id);old.remove();document.title=title;const b=document.createElement('button');b.id=label.toLowerCase();b.textContent=label;b.onclick=()=>advance(b.id,label==='Continue'?'step 3':'done',label==='Continue'?'Finish':'Done');document.body.appendChild(b)}
</script><button id="login" onclick="advance('login','step 2','Continue')">Login</button>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_chromium(cdp_port: int) -> subprocess.Popen[str]:
    code = (
        "import playwright.sync_api as s, time; "
        "p=s.sync_playwright().start(); "
        f"b=p.chromium.launch(headless=True,args=['--remote-debugging-port={cdp_port}']); "
        "b.new_page(); time.sleep(600)"
    )
    return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True)


def wait_cdp(port: int, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Chromium CDP did not start on {port}")


def parse_tool_result(content: str) -> dict:
    # Session exports wrap tool output in untrusted markers; retain exact raw data.
    try:
        candidate = content
        if "</untrusted_tool_result>" in candidate:
            candidate = candidate.split("</untrusted_tool_result>", 1)[0]
        candidate = candidate.replace("\\\\n", "").strip()
        outer = json.loads(candidate)
        text = outer.get("result", outer)
        if isinstance(text, str):
            text = json.loads(text)
        if isinstance(text, dict) and "action_trajectory" in text:
            return text
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    try:
        marker = content.find('"result"')
        colon = content.find(':', marker)
        start_quote = content.find('"', colon + 1)
        encoded, _ = json.JSONDecoder().raw_decode(content, start_quote)
        text = json.loads(encoded)
        if isinstance(text, dict) and "action_trajectory" in text:
            return text
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    normalized = content
    start = normalized.find("<untrusted_tool_result>")
    end = normalized.find("</untrusted_tool_result>", start)
    if start < 0 or end < 0:
        raise AssertionError(f"Neeble tool result not found in exported session: {content[-1000:]}")
    raw = normalized[start + len("<untrusted_tool_result>"):end].strip()
    # The export may include a label line before the JSON envelope.
    raw = raw[raw.find("{"):]
    payload = json.loads(raw)
    text = payload.get("result", payload)
    if isinstance(text, str):
        text = json.loads(text)
    return text


def inspect_session(session_id: str, export_path: Path) -> dict:
    subprocess.run(["hermes", "sessions", "export", "--session-id", session_id,
                    "--format", "jsonl", str(export_path)], check=True,
                   capture_output=True, text=True, timeout=120)
    records = [json.loads(line) for line in export_path.read_text().splitlines() if line.strip()]
    if len(records) != 1:
        raise AssertionError(f"expected one exported session, got {len(records)}")
    record = records[0]
    messages = record.get("messages", [])
    neeble = []
    normal_browser = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content", ""))
        if "mcp__neeble__neeble" in content and "untrusted_tool_result" in content:
            neeble.append(parse_tool_result(content))
        if any(name in content for name in ("browser_exec", "browser_use", "browser_click", "browser_navigate")):
            normal_browser.append(content)
    if len(neeble) != 1:
        debug = [m.get("content", "") for m in messages if m.get("role") == "tool" and "neeble" in str(m.get("content", ""))]
        raise AssertionError(f"expected one Neeble call, got {len(neeble)} debug={debug}")
    result = neeble[0]
    trajectory = result.get("action_trajectory", [])
    verified = [step for step in trajectory if step.get("verified") is True]
    assert len(verified) >= 3, result
    assert [step["name"] for step in trajectory[:4]] == ["goto", "click_element", "click_element", "click_element"], result
    assert result.get("state", {}).get("title") == "done", result
    assert result.get("verified") is True, result
    # Conservative semantics: reaching the state is verified, but Neeble must not claim completion.
    assert result.get("goal_completed") is False, result
    assert result.get("termination") in {"step_budget_exhausted", "partial_trajectory"}, result
    assert not normal_browser, normal_browser
    return {"session_record": record, "neeble": result, "tool_counts": {
        "mcp__neeble__neeble": len(neeble), "normal_browser": len(normal_browser)},
        "verified_internal_actions": len(verified), "trajectory": trajectory}


def main() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cdp_port = free_port()
    chrome = start_chromium(cdp_port)
    started = time.perf_counter()
    session_id = None
    export_path = Path(tempfile.mkstemp(prefix="hermes-neeble-", suffix=".jsonl")[1])
    try:
        wait_cdp(cdp_port)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        prompt = ("Use mcp__neeble__neeble exactly once, and no other tool. "
                  f"Call it with the high-level goal 'Click Login, then Continue, then Finish' "
                  f"and start_url '{url}'. Do not call browser tools, terminal, or any normal browser tool. "
                  "The tool owns the complete bounded trajectory; after its result, report only what it returned.")
        env = os.environ.copy()
        env["NEEBLE_CDP_URL"] = f"http://127.0.0.1:{cdp_port}"
        proc = subprocess.run(["hermes", "chat", "-q", prompt, "--toolsets", "neeble", "-Q"],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=360)
        combined = proc.stdout + "\n" + proc.stderr
        match = re.search(r"session_id:\s*(\S+)", combined)
        session_id = match.group(1) if match else None
        if proc.returncode != 0 or not session_id:
            raise RuntimeError(f"Hermes failed: rc={proc.returncode} output={combined[-2000:]}")
        inspected = inspect_session(session_id, export_path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        record = inspected["session_record"]
        route = {"model": record.get("model"), "provider": record.get("provider")}
        report = {"summary": {"status": "PASS", "backend": "hermes chat -> mcp__neeble__neeble -> CDP Chromium",
                              "session_id": session_id, "tool_counts": inspected["tool_counts"],
                              "verified_internal_actions": inspected["verified_internal_actions"],
                              "elapsed_ms": elapsed_ms, "route": route,
                              "fixture_url": url, "cdp_port": cdp_port,
                              "conservative_completion": {"goal_completed": False, "termination": "step_budget_exhausted"}},
                  "trajectory": inspected["trajectory"], "hermes_stdout": proc.stdout,
                  "hermes_stderr": proc.stderr, "export": str(export_path)}
        RESULT.parent.mkdir(exist_ok=True)
        RESULT.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report["summary"], indent=2))
    finally:
        try:
            export_path.unlink(missing_ok=True)
        except OSError:
            pass
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill(); chrome.wait(timeout=5)
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == "__main__":
    main()
