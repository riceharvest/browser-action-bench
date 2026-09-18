# Neeble

Neeble is a persistent browser-action accelerator for Hermes Agent. Hermes sends
one high-level goal; a small local Needle policy executes and verifies a bounded
sequence of safe browser actions over one persistent CDP connection. Risky or
uncertain work is returned to Hermes as an explicit escalation.

The project compares a tiny action model such as Needle 3 with a larger OpenAI-compatible model on the same browser-action fixtures. It measures decision latency, valid actions, schema accuracy, end-to-end action latency, and actions/minute.

## Action map

The initial taxonomy covers:

- navigation: `goto`, `back`, `forward`, `reload`, `new_tab`, `close_tab`
- inspection: `snapshot`, `screenshot`, `get_url`, `get_title`, `get_text`, `find`
- pointer: `click`, `double_click`, `hover`, `drag`, `scroll`, `scroll_into_view`
- keyboard: `type`, `press`, `key_down`, `key_up`, `clear`, `paste`
- forms: `select_option`, `check`, `uncheck`, `upload_file`, `submit`
- tabs/windows: `switch_tab`, `new_window`, `close_window`
- waiting: `wait`, `wait_for_selector`, `wait_for_navigation`, `wait_for_network_idle`
- browser data: `cookies`, `local_storage`, `set_cookie`
- recovery: `retry`, `refresh_snapshot`, `escalate`

The action map is deliberately fine-grained: observation, pointer, keyboard, form, synchronization, browser data, and recovery are separate decisions. This lets us measure which operations Needle can safely own instead of hiding failures inside a generic `click` or `interact` action.

See `PROTOCOL.md` for the agent-facing JSONL CLI contract.

```bash
pip install -e '.[needle]'
python -m playwright install chromium
export NEEBLE_CDP_URL=http://127.0.0.1:9222
neeble --weights "$PWD/models/needle3.cact"
```

The CLI is a JSONL process: one request produces one structured action. It
never executes an unknown, stale, invisible, malformed, or risky action.
Invalid input and missing policy weights return an escalation record and keep
the process alive so Hermes can take over.

```bash
python -m babench --help
python -m babench run --backend mock --cases 100
```

The mock backend only validates the harness. It is not a model benchmark.

See `RUNTIME.md` for the intended single-runtime architecture: Needle attempts routine actions, validates them against browser state, and escalates only low-confidence or failed decisions to the larger model.

For the larger-model baseline through OpenRouter:

```bash
export OPENROUTER_API_KEY=...
python -m babench run --backend openai \
  --base-url https://openrouter.ai/api/v1 \
  --model deepseek/deepseek-v4.1-flash \
  --cases 100
```

Needle integration is isolated behind the `neeble` CLI. Install its package separately when available:

```bash
pip install cactus-needle
python -m babench run --backend needle --layers 8 --cases 100
```

```bash
hermes mcp add neeble \
  --command "$(command -v neeble-mcp)" \
  --env NEEBLE_WEIGHTS=/absolute/path/to/models/needle3.cact
hermes mcp test neeble
# Start a new session, then include the neeble MCP toolset.
hermes chat -q 'Use neeble for routine browser actions.' --toolsets browser,neeble
```

The MCP server keeps the model and browser connection alive across the complete navigation trajectory. `NEEBLE_WEIGHTS` must be absolute because Hermes may launch the stdio server from a different working directory.
Results are JSONL plus a summary JSON. Never compare runs unless the fixture set, action set, prompt, and concurrency are identical.

## Verified benchmark evidence

The matched four-action proof uses the same Hermes model, fixture, browser
executor, CDP session, and final `title=done` postcondition in both modes:

- Neeble, one high-level call: 8 valid runs, p50 **18.88 s**
- one-action MCP baseline, four calls: 9 valid runs, p50 **40.96 s**
- measured end-to-end wall-time speedup: **2.17x**

Three additional real Hermes sessions verified risky handoff: Neeble escalated
with zero actions and no mutation, then Hermes used a separate inspection-only
tool to confirm the untouched page title. See
[`benchmarks/proof-summary.json`](benchmarks/proof-summary.json) for the
sanitized aggregate and `scripts/` for reproducible local smokes. These figures
apply to this controlled fixture; they are not a claim that every website or
task is accelerated.

The recorded Chromium fixture results are real DOM executions, not mock
actions. The last recorded 40-case Needle run verified 40/40 actions at 100%
success and 159.4 verified actions/minute (p50 decision plus execution
latency: 376.3 ms). The recorded direct-provider fixture result was 28.2 actions/minute, but it is
only a microbenchmark: it excludes Hermes startup, the Hermes conversation
loop, MCP dispatch, browser startup, and browser-state acquisition. It must
not be described as a normal Hermes/browser baseline.

The browser executor and policy process are persistent in `neeble` and
`NeebleTool`; `babench` remains an explicit benchmark harness. Risky actions
such as submit, upload, downloads, script execution, storage mutation, and
tab destruction always return to Hermes.

The live Hermes integration was also exercised with the configured MCP server:
`python bench_hermes.py` ran 2 fresh Hermes sessions, both called
`mcp__neeble__neeble`, and both produced `verified: true` executor results in
the exported session records. The recorded end-to-end wall time was 18.7 s
mean. This includes starting Hermes and the main-model turn, so it must not
be compared to the 0.38 s local policy-only figure as if they measured the
same thing. The normal Hermes browser tool was not available in this local
session, so no fabricated same-host Hermes-browser comparison is reported.

The live Hugging Face research task is reproducible with
`python bench_hf_tasks.py`. It asks the main Hermes model to find Qwen's newest
model, most-downloaded model, and author-listing total using rendered pages,
then checks the answer against a separately fetched live API oracle. The latest
recorded run was accurate in both tracks, but it is not yet a valid Neeble
replacement benchmark: normal Hermes/browser took 85.3 s, while the Neeble
track took 94.9 s and its three Neeble calls escalated because the policy
subprocess exited. Hermes then completed the research with ten normal
`browser_exec` calls. The report preserves this failure evidence rather than
calling the fallback a Neeble speedup.

The broader live prompt suite is `python bench_hf_suite.py`. It currently
covers five distinct research trajectories: Qwen overview/counts, most-liked
model, text-generation top three, Transformers-library top three, and the
Qwen Datasets tab/count. Each case gets a fresh live oracle from Hugging Face,
and each Hermes/Neeble run records wall time, answer checks, session ID, and
the final output in `results/huggingface-qwen-suite.json`.

For cross-domain evaluation, run `python bench_domain_suite.py`. Its five
independent live research tasks cover GitHub repository ranking, npm package
search and package details, arXiv paper discovery, Stack Overflow technical
answer ranking, and PyPI project comparison. Each domain has its own start
URL, navigation instructions, independently fetched oracle, and accuracy
checks; no single site's search behavior can dominate the result. Reports are
written to `results/cross-domain-hermes-neeble-suite.json`.
Use `--scenario NAME` and `--mode normal|neeble` for bounded reruns while
debugging one domain, for example:
`python bench_domain_suite.py --scenario npm-browser-automation --mode neeble`.

`NeebleTool` now detects dead or stalled policy subprocesses, restarts them,
and returns an explicit `escalate` result instead of wedging a long browser
trajectory. That keeps complex tasks recoverable by Hermes and makes failures
visible in benchmark results rather than silently dropping a tool call.

The policy now receives the current browser state when selecting an action;
this is essential and is covered by the live npm smoke. After the state-input,
single-call, and early-partial-return changes, the npm high-level run completed
in 18.1 s wall time, versus 37.8 s for the earlier equivalent smoke; the local
Neeble trajectory itself now reaches the correct package detail page in 1.8 s,
with the
top-three package result and leading version correct. This is a measured
improvement, not a claim that every domain is solved.

## What this answers

- Needle decode TPS versus large-model decode TPS
- decision latency per action
- valid JSON and valid action rate
- exact action/argument accuracy
- end-to-end actions/minute
- escalation rate

TPS is reported as a diagnostic. Actions/minute is the primary metric.

## Status

This repository contains the reproducible harness and action schemas. It does not contain fabricated speed claims. Real numbers require running the same cases against the selected local endpoints.
