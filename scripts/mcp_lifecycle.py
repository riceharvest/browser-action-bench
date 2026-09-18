"""Owned-process lifecycle helpers for benchmark MCP fixtures."""
from __future__ import annotations
import subprocess
from typing import Optional


def stop_process(proc: Optional[subprocess.Popen], timeout: float = 8.0) -> str:
    """Stop a process, preferring cooperative EOF and escalating if needed."""
    if proc is None or proc.poll() is not None:
        return "already-exited"
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()  # EOF lets neeble_mcp finally close/reap policy.
    except (BrokenPipeError, OSError):
        pass
    try:
        proc.wait(timeout=timeout)
        return "eof"
    except subprocess.TimeoutExpired:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
        return "terminate"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)
        return "kill"


def stop_mcp_then_chrome(mcp: Optional[subprocess.Popen], chrome: Optional[subprocess.Popen]) -> tuple[str, str, str]:
    """Shutdown MCP first, then its browser owner; return methods and stderr."""
    mcp_method = stop_process(mcp)
    stderr = ""
    if mcp is not None and mcp.stderr is not None:
        try:
            stderr = mcp.stderr.read()
        except (OSError, ValueError):
            pass
    chrome_method = stop_process(chrome)
    return mcp_method, chrome_method, stderr
