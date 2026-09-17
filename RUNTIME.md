# Runtime design

## Goal

Expose one browser-use runtime to an AI agent. The agent sends a vague goal plus the current browser state. The fast local policy model attempts routine actions and only returns uncertain decisions to the larger model.

## Control loop

```text
agent goal + browser state
        |
        v
action normalizer (compact accessibility tree, URL, tabs, recent result)
        |
        v
Needle policy model
        |
        +-- confidence >= threshold and action validates
        |       -> execute exactly one action
        |       -> verify resulting state
        |
        +-- low confidence, invalid action, or repeated failure
                -> return escalation packet to large model
```

The large model remains responsible for planning, novel pages, ambiguity, safety-sensitive actions, and recovery. Needle is not trusted to bypass executor validation.

## Contract

Input:

```json
{
  "goal": "Book the cheapest train to Amsterdam tomorrow morning",
  "state": {
    "url": "https://example.test",
    "elements": [{"id":"e1","role":"textbox","name":"From"}],
    "tabs": [{"id":"t1","title":"Search"}]
  },
  "allowed_actions": ["click", "type", "select_option", "submit", "wait"]
}
```

Output on a routine action:

```json
{"status":"action","confidence":0.96,"action":{"name":"type","arguments":{"element_id":"e1","text":"Enschede"}}}
```

Output on escalation:

```json
{"status":"escalate","confidence":0.41,"reason":"No safe matching action","state_hash":"..."}
```

## Benchmark units

The primary result is successful verified actions per minute. Token throughput is reported alongside it, but is not the goal. Measure the same trajectories with Needle and the larger model, including executor and browser-state overhead:

- action decision latency
- end-to-end verified action latency
- valid action rate
- exact element and argument accuracy
- escalation rate
- recovery rate
- actions/minute
- model prompt/decode TPS

Never count an action as successful merely because the model emitted valid JSON.
