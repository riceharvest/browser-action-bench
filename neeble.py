from __future__ import annotations
import argparse, json, sys
import needle
from babench.runtime import verify_action


def main() -> None:
    p = argparse.ArgumentParser(prog='neeble', description='Fast verified browser-action policy layer')
    p.add_argument('--weights', default='models/needle3.cact')
    p.add_argument('--max-new-tokens', type=int, default=128)
    args = p.parse_args()
    for line in sys.stdin:
        if not line.strip(): continue
        req = json.loads(line)
        tools = []
        for spec in req.get('tools', []):
            name = spec['name']
            desc = spec.get('description', name)
            params = spec.get('parameters', {})
            if name == 'click_element':
                def tool(element_id: str): return {'_action': 'click_element', 'arguments': {'element_id': element_id}, 'verified': False}
            elif name == 'type_text':
                def tool(element_id: str, text: str): return {'_action': 'type_text', 'arguments': {'element_id': element_id, 'text': text}, 'verified': False}
            elif name == 'scroll':
                def tool(direction: str): return {'_action': 'scroll', 'arguments': {'direction': direction}, 'verified': False}
            else:
                def tool(): return {'_action': name, 'arguments': {}, 'verified': False}
            tool.__name__, tool.__doc__ = name, desc
            tools.append(needle.tool(tool))
        agent = needle.Needle(tools=tools, weights=args.weights)
        result = agent.run(req.get('goal', ''), max_new_tokens=args.max_new_tokens)
        result['verified'] = False
        result['needs_executor_verification'] = True
        state = req.get('state')
        if state and result.get('results'):
            candidate = result['results'][0]
            action = {'name': candidate.get('_action'), 'arguments': candidate.get('arguments', {})}
            verdict = verify_action(action, state)
            result['legal_for_state'] = verdict.ok
            result['verification_reason'] = verdict.reason
        print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
