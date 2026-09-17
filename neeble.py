from __future__ import annotations
import argparse, json, os, sys
import needle
from playwright.sync_api import sync_playwright
from babench.runtime import verify_action


class BrowserExecutor:
    def __init__(self, cdp_url: str):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.connect_over_cdp(cdp_url)

    def execute(self, action: dict) -> dict:
        pages = self.browser.contexts[0].pages
        page = pages[-1]
        name, args = action.get('name'), action.get('arguments', {})
        if name == 'goto': page.goto(args['url'])
        elif name == 'back': page.go_back()
        elif name == 'forward': page.go_forward()
        elif name == 'reload': page.reload()
        elif name == 'click_element': page.locator('#' + args['element_id']).click()
        elif name == 'type_text': page.locator('#' + args['element_id']).fill(args['text'])
        elif name == 'scroll': page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        elif name == 'wait': page.wait_for_timeout(int(args.get('ms', 100)))
        else: return {'verified': False, 'error': 'executor does not implement action'}
        return {'verified': True, 'url': page.url, 'title': page.title(), 'pages': len(pages)}

    def close(self): self.pw.stop()


def main() -> None:
    p = argparse.ArgumentParser(prog='neeble', description='Fast verified browser-action policy layer')
    p.add_argument('--weights', default='models/needle3.cact')
    p.add_argument('--max-new-tokens', type=int, default=128)
    args = p.parse_args()
    agent_cache = {}
    executor = BrowserExecutor(os.environ['NEEBLE_CDP_URL']) if os.environ.get('NEEBLE_CDP_URL') else None
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
            elif name == 'goto':
                def tool(url: str): return {'_action': 'goto', 'arguments': {'url': url}, 'verified': False}
            elif name == 'back':
                def tool(): return {'_action': 'back', 'arguments': {}, 'verified': False}
            elif name == 'forward':
                def tool(): return {'_action': 'forward', 'arguments': {}, 'verified': False}
            elif name == 'reload':
                def tool(): return {'_action': 'reload', 'arguments': {}, 'verified': False}
            elif name == 'type_text':
                def tool(element_id: str, text: str): return {'_action': 'type_text', 'arguments': {'element_id': element_id, 'text': text}, 'verified': False}
            elif name == 'scroll':
                def tool(direction: str): return {'_action': 'scroll', 'arguments': {'direction': direction}, 'verified': False}
            else:
                def tool(): return {'_action': name, 'arguments': {}, 'verified': False}
            tool.__name__, tool.__doc__ = name, desc
            tools.append(needle.tool(tool))
        tool_key = tuple(spec['name'] for spec in req.get('tools', []))
        if tool_key not in agent_cache:
            agent_cache[tool_key] = needle.Needle(tools=tools, weights=args.weights)
        agent = agent_cache[tool_key]
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
            cdp_url = os.environ.get('NEEBLE_CDP_URL')
            if verdict.ok and executor is not None and candidate.get('_action'):
                result['executor'] = executor.execute(action)
                result['verified'] = result['executor'].get('verified', False)
        print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
