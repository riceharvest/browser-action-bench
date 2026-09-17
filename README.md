# browser-action-bench

Benchmark browser automation as completed actions per minute, not just model tokens/sec.

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

See `RUNTIME.md` for the intended single-runtime architecture: Needle attempts routine actions, validates them against browser state, and escalates only low-confidence or failed decisions to the larger model.


```bash
python -m babench --help
python -m babench run --backend mock --cases 100
```

The mock backend only validates the harness. It is not a model benchmark.

See `RUNTIME.md` for the intended single-runtime architecture: Needle attempts routine actions, validates them against browser state, and escalates only low-confidence or failed decisions to the larger model.

For a larger model:

```bash
python -m babench run --backend openai \
  --base-url http://127.0.0.1:8014/v1 \
  --model YOUR_MODEL \
  --cases 100
```

Needle integration is isolated behind `babench.backends.needle_backend`. Install its package separately when available:

```bash
pip install cactus-needle
python -m babench run --backend needle --layers 8 --cases 100
```

Results are JSONL plus a summary JSON. Never compare runs unless the fixture set, action set, prompt, and concurrency are identical.

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
