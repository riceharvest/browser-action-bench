# Neeble

[![CI](https://github.com/riceharvest/neeble/actions/workflows/ci.yml/badge.svg)](https://github.com/riceharvest/neeble/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](pyproject.toml)

Fast local browser actions for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Hermes sends one goal. Neeble executes a bounded sequence of routine actions over one persistent CDP connection, verifies every step against fresh browser state, and returns one compact trajectory. Risky or uncertain work goes back to Hermes.

```text
Hermes goal
    │
    ▼
Neeble MCP ──► local Needle policy ──► validator ──► Playwright/CDP
    │                                      │
    └──────── trajectory / escalation ◄────┘
```

## Why

A normal browser agent pays for a large-model turn after every click. Neeble keeps the small policy and browser alive inside one tool call.

| Matched four-action fixture | Calls | Valid runs | p50 wall time |
|---|---:|---:|---:|
| Neeble | 1 | 8 | **18.88 s** |
| One-action MCP baseline | 4 | 9 | 40.96 s |

Measured speedup: **2.17x**. Same Hermes model, fixture, executor, CDP lifetime, four verified actions, and final `title=done` check. This is a controlled fixture result, not a universal website claim. The sanitized aggregate is in [`benchmarks/proof-summary.json`](benchmarks/proof-summary.json).

## Safety

Neeble validates actions against the latest visible DOM state before execution.

- stale, hidden, malformed, ambiguous, or unsupported targets are rejected
- submit, upload, downloads, scripts, storage changes, credentials, and payments escalate
- explicit completion requires an observed URL, title, or text postcondition
- a dead or stalled policy process is restarted once, then escalated

Three real Hermes sessions verified the handoff path: Neeble returned an empty escalation, then Hermes performed one safe title inspection without mutating the page.

## Install

```bash
git clone https://github.com/riceharvest/neeble.git
cd neeble
pip install -e '.[needle]'
python -m playwright install chromium
```

Download compatible Needle weights separately. Model files are not included in this repository.

Start Chromium with CDP enabled:

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/neeble-chrome \
  about:blank
```

## Connect to Hermes

```bash
hermes mcp add neeble \
  --command "$(command -v neeble-mcp)" \
  --env \
    NEEBLE_WEIGHTS=/absolute/path/to/needle3.cact \
    NEEBLE_CDP_URL=http://127.0.0.1:9222

hermes mcp test neeble
```

Start a fresh Hermes session, then give Neeble a high-level goal:

```text
Use neeble once to open the package page, select the newest release,
and stop when the page title contains "Release".
```

The MCP input is small:

```json
{
  "goal": "Click Login, then Continue, then Finish",
  "start_url": "https://example.test",
  "max_steps": 8,
  "completion": {"title": "done"}
}
```

## Verify locally

```bash
python -m pytest -q
cargo test --lib
python scripts/mcp_boundary_smoke.py
python scripts/mcp_scenario_suite.py
```

The scenario suite covers forms, navigation, reload/back, multiple tabs, ambiguous targets, and risky-action escalation.

## Repository map

```text
neeble.py                 browser executor + local policy process
neeble_tool.py            persistent multi-action control loop
neeble_mcp.py             high-level Hermes MCP server
babench/runtime.py        action canonicalization and safety checks
scripts/                  real CDP/MCP smoke tests
benchmarks/               reviewed, sanitized benchmark aggregates
PROTOCOL.md               wire contract
RUNTIME.md                runtime design
```

MIT licensed. See [`PROTOCOL.md`](PROTOCOL.md) for the wire format and [`RUNTIME.md`](RUNTIME.md) for the control loop.