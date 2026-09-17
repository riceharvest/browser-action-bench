from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import needle


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--weights', default='models/needle3.cact')
    p.add_argument('--cases', type=int, default=100)
    p.add_argument('--out', default='results/needle3-baseline.json')
    args = p.parse_args()

    actions = []
    calls = {}

    def make_tool(name: str, description: str, **annotations):
        def tool(**kwargs):
            actions.append({'name': name, 'arguments': kwargs})
            return {'verified': True, **kwargs}
        tool.__name__ = name
        tool.__doc__ = description
        return needle.tool(tool)

    tools = [
        make_tool('click_element', 'Click a visible browser element by its stable element id.', element_id=''),
        make_tool('type_text', 'Type text into a visible browser element.', element_id='', text=''),
        make_tool('scroll', 'Scroll the page vertically.', direction='', amount=0),
        make_tool('wait_for_selector', 'Wait until a selector is visible.', selector=''),
    ]
    prompts = [
        'Click the login button with element id login',
        'Type Enschede into the search field with element id search',
        'Scroll down the page',
        'Wait for the results selector .results',
    ]
    timings = []
    reports = []
    for i in range(args.cases):
        actions.clear()
        agent = needle.Needle(tools=tools, weights=args.weights)
        start = time.perf_counter()
        result = agent.run(prompts[i % len(prompts)], max_new_tokens=64)
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)
        reports.append({'prompt': prompts[i % len(prompts)], 'elapsed_ms': elapsed_ms,
                        'success': result.get('success', False),
                        'confidence': result.get('confidence'),
                        'prefill_tps': result.get('prefill_tps'),
                        'decode_tps': result.get('decode_tps'),
                        'results': result.get('results', [])})

    summary = {
        'backend': 'needle3-python', 'cases': args.cases,
        'successful_decisions': sum(r['success'] for r in reports),
        'latency_ms_mean': statistics.mean(timings),
        'latency_ms_p50': statistics.median(timings),
        'latency_ms_min': min(timings), 'latency_ms_max': max(timings),
        'actions_per_minute': args.cases / (sum(timings) / 1000 / 60),
        'prefill_tps_median': statistics.median([r['prefill_tps'] for r in reports if r['prefill_tps']]),
        'decode_tps_median': statistics.median([r['decode_tps'] for r in reports if r['decode_tps']]),
        'note': 'Needle model decision loop with Python runtime and function tools; executor is a verification stub, not Chromium yet.',
        'reports': reports,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'reports'}, indent=2))


if __name__ == '__main__':
    main()
