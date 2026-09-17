from __future__ import annotations
import argparse, json, sys
import needle


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
                def tool(element_id: str): return {'verified': False, 'arguments': {'element_id': element_id}}
            elif name == 'type_text':
                def tool(element_id: str, text: str): return {'verified': False, 'arguments': {'element_id': element_id, 'text': text}}
            elif name == 'scroll':
                def tool(direction: str): return {'verified': False, 'arguments': {'direction': direction}}
            else:
                def tool(): return {'verified': False, 'arguments': {}}
            tool.__name__, tool.__doc__ = name, desc
            tools.append(needle.tool(tool))
        agent = needle.Needle(tools=tools, weights=args.weights)
        result = agent.run(req.get('goal', ''), max_new_tokens=args.max_new_tokens)
        # Never allow the policy layer to claim verification: the browser executor must confirm it.
        result['verified'] = False
        result['needs_executor_verification'] = True
        print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
