from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class NeebleTool:
    """Hermes-compatible persistent browser action tool client."""
    def __init__(self, weights: str = 'models/needle3.cact', cdp_url: str | None = None):
        env = os.environ.copy()
        if cdp_url: env['NEEBLE_CDP_URL'] = cdp_url
        self.proc = subprocess.Popen([os.environ.get('PYTHON', 'python'), '-m', 'neeble', '--weights', weights], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env, bufsize=1)

    def __call__(self, goal: str, state: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if self.proc.poll() is not None: raise RuntimeError('neeble process exited')
        request = json.dumps({'goal': goal, 'state': state, 'tools': tools})
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(request + '\n'); self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line: raise RuntimeError('neeble returned no response')
        return json.loads(line)

    def run_trajectory(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run a complete multi-page trajectory over one persistent process."""
        results = []
        state: dict[str, Any] = {}
        for step in steps:
            result = self(step['goal'], step.get('state', state), step['tools'])
            results.append(result)
            if result.get('executor', {}).get('state'):
                state = result['executor']['state']
        return results

    def close(self) -> None:
        if self.proc.poll() is None: self.proc.terminate(); self.proc.wait(timeout=5)
