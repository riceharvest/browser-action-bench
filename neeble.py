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
        if name in {'click_element', 'type_text'}:
            target = '#' + args['element_id']
            for candidate in reversed(pages):
                if candidate.locator(target).count():
                    page = candidate
                    break
        if name == 'goto': page.goto(args['url'])
        elif name == 'back': page.go_back()
        elif name == 'forward': page.go_forward()
        elif name == 'reload': page.reload()
        elif name == 'click_element': page.locator('#' + args['element_id']).click()
        elif name == 'double_click': page.locator('#' + args['element_id']).dblclick()
        elif name == 'right_click': page.locator('#' + args['element_id']).click(button='right')
        elif name == 'hover': page.locator('#' + args['element_id']).hover()
        elif name == 'type_text': page.locator('#' + args['element_id']).fill(args['text'])
        elif name == 'press': page.locator('#' + args['element_id']).press(args['key'])
        elif name == 'scroll_into_view': page.locator('#' + args['element_id']).scroll_into_view_if_needed()
        elif name == 'new_tab': self.browser.contexts[0].new_page()
        elif name == 'close_tab': page.close()
        elif name == 'clear': page.locator('#' + args['element_id']).fill('')
        elif name == 'focus': page.locator('#' + args['element_id']).focus()
        elif name == 'blur': page.locator('#' + args['element_id']).blur()
        elif name == 'check': page.locator('#' + args['element_id']).check()
        elif name == 'uncheck': page.locator('#' + args['element_id']).uncheck()
        elif name == 'select_option': page.locator('#' + args['element_id']).select_option(args['value'])
        elif name == 'scroll': page.evaluate("window.scrollBy(0, arguments[0])", int(args.get('amount', 700)))
        elif name == 'snapshot': pass
        elif name == 'wait': page.wait_for_timeout(int(args.get('ms', 100)))
        else: return {'verified': False, 'error': 'executor does not implement action'}
        elements = page.locator('button, input, textarea, select, a, [role]').evaluate_all("els => els.slice(0, 100).map((e,i) => ({id:e.id || 'el-'+i, role:e.getAttribute('role') || e.tagName.toLowerCase(), text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,160), visible:!!(e.offsetWidth || e.offsetHeight)}))")
        return {'verified': True, 'url': page.url, 'title': page.title(), 'pages': len(pages), 'state': {'url': page.url, 'elements': elements}}

    def snapshot(self) -> dict:
        page = self.browser.contexts[0].pages[-1]
        elements = page.locator('button, input, textarea, select, a, [role]').evaluate_all("els => els.slice(0, 100).map((e,i) => ({id:e.id || 'el-'+i, role:e.getAttribute('role') || e.tagName.toLowerCase(), text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,160), visible:!!(e.offsetWidth || e.offsetHeight)}))")
        return {'url': page.url, 'title': page.title(), 'elements': elements}

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
            if name in {'click_element', 'double_click', 'right_click', 'hover', 'scroll_into_view'}:
                def tool(element_id: str): return {'_action': name, 'arguments': {'element_id': element_id}, 'verified': False}
            elif name == 'press':
                def tool(element_id: str, key: str): return {'_action': 'press', 'arguments': {'element_id': element_id, 'key': key}, 'verified': False}
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
        state = req.get('state') or (executor.snapshot() if executor is not None else None)
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
