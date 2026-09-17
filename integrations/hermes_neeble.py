"""Drop-in Hermes tool handler for the Neeble browser policy layer.

Copy this module into a Hermes tools plugin or import ``neeble_browser`` from a
custom tool registration. It keeps one NeebleTool instance for the process.
"""
import json
import os
from neeble_tool import NeebleTool

_client = None

def neeble_browser(goal: str, state: dict, tools: list[dict]) -> str:
    global _client
    if _client is None:
        _client = NeebleTool(
            weights=os.environ.get('NEEBLE_WEIGHTS', 'models/needle3.cact'),
            cdp_url=os.environ.get('NEEBLE_CDP_URL'),
        )
    result = _client(goal, state, tools)
    return json.dumps(result, separators=(',', ':'))

def close_neeble() -> None:
    global _client
    if _client is not None:
        _client.close(); _client = None
