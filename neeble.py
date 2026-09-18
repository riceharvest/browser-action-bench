from __future__ import annotations
import argparse, json, os, re, sys
from playwright.sync_api import sync_playwright
from babench.runtime import canonicalize_action, decode_semantic_action, verify_action

VERSION = '0.1.0'

class BrowserExecutor:
    def __init__(self, cdp_url: str):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.connect_over_cdp(cdp_url)

    def execute(self, action: dict) -> dict:
        pages = list(self.browser.contexts[0].pages)
        if not pages:
            return {'verified': False, 'error': 'browser has no open pages'}
        page = pages[-1]
        name, args = action.get('name'), action.get('arguments', {})
        if name in {'click_element', 'type_text'}:
            target = 'id=' + args['element_id']
            for candidate in reversed(pages):
                if candidate.locator(target).count():
                    page = candidate
                    break
        if name == 'goto': page.goto(args['url'], wait_until='domcontentloaded')
        elif name == 'back': page.go_back()
        elif name == 'forward': page.go_forward()
        elif name == 'reload': page.reload()
        elif name == 'click_element':
            locator = page.locator('id=' + args['element_id'])
            if locator.get_attribute('target') == '_blank':
                with page.expect_popup(timeout=5000) as popup_info:
                    locator.click()
                page = popup_info.value
                page.wait_for_load_state('domcontentloaded')
            else:
                locator.click()
        elif name == 'double_click': page.locator('id=' + args['element_id']).dblclick()
        elif name == 'right_click': page.locator('id=' + args['element_id']).click(button='right')
        elif name == 'hover': page.locator('id=' + args['element_id']).hover()
        elif name == 'type_text': page.locator('id=' + args['element_id']).fill(args['text'])
        elif name == 'press': page.locator('id=' + args['element_id']).press(args['key'])
        elif name == 'scroll_into_view': page.locator('id=' + args['element_id']).scroll_into_view_if_needed()
        elif name == 'new_tab': self.browser.contexts[0].new_page()
        elif name == 'close_tab': page.close()
        elif name == 'clear': page.locator('id=' + args['element_id']).fill('')
        elif name == 'focus': page.locator('id=' + args['element_id']).focus()
        elif name == 'blur': page.locator('id=' + args['element_id']).blur()
        elif name == 'check': page.locator('id=' + args['element_id']).check()
        elif name == 'uncheck': page.locator('id=' + args['element_id']).uncheck()
        elif name == 'select_option': page.locator('id=' + args['element_id']).select_option(args['value'])
        elif name == 'scroll': page.evaluate("window.scrollBy(0, arguments[0])", int(args.get('amount', 700)))
        elif name == 'snapshot': pass
        elif name == 'wait': page.wait_for_timeout(int(args.get('ms', 100)))
        else: return {'verified': False, 'error': 'executor does not implement action'}
        return {'verified': True, **self.snapshot(page)}

    def snapshot(self, page=None) -> dict:
        pages = list(self.browser.contexts[0].pages)
        if not pages:
            return {'verified': False, 'error': 'browser has no open pages'}
        page = page or pages[-1]
        elements = page.locator('button, input, textarea, select, a, [role]').evaluate_all("els => els.slice(0, 100).map((e,i) => ({id:e.id || 'el-'+i, role: e.getAttribute('role') || (e.tagName.toLowerCase() === 'input' && (e.type || 'text') === 'text' ? 'textbox' : e.tagName.toLowerCase()), text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,160), href:e.href || undefined, visible:!!(e.offsetWidth || e.offsetHeight)}))")
        text = page.locator('body').inner_text(timeout=3000)[:12000]
        return {'url': page.url, 'title': page.title(), 'pages': len(pages), 'text': text, 'state': {'url': page.url, 'title': page.title(), 'pages': len(pages), 'elements': elements, 'text': text}}

    def close(self): self.pw.stop()


def main() -> None:
    p = argparse.ArgumentParser(prog='neeble', description='Fast verified browser-action policy layer; unsafe or uncertain work escalates to Hermes')
    p.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')
    p.add_argument('--weights', default='models/needle3.cact')
    p.add_argument('--max-new-tokens', type=int, default=64)
    args = p.parse_args()
    agent_cache = {}
    executor = BrowserExecutor(os.environ['NEEBLE_CDP_URL']) if os.environ.get('NEEBLE_CDP_URL') else None
    try:
        import needle
    except ImportError:
        needle = None
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({'status': 'escalate', 'verified': False, 'reason': f'invalid JSON: {exc.msg}'}), flush=True)
            continue
        tools = []
        def make_tool(name, desc):
            if name in {'click_element', 'double_click', 'right_click', 'hover', 'scroll_into_view', 'focus', 'blur', 'clear', 'check', 'uncheck'}:
                def tool_fn(element_id: str, _name=name): return {'_action': _name, 'arguments': {'element_id': element_id}, 'verified': False}
            elif name == 'press':
                def tool_fn(element_id: str, key: str, _name=name): return {'_action': _name, 'arguments': {'element_id': element_id, 'key': key}, 'verified': False}
            elif name == 'goto':
                def tool_fn(url: str, _name=name): return {'_action': _name, 'arguments': {'url': url}, 'verified': False}
            elif name in {'back', 'forward', 'reload', 'snapshot', 'new_tab'}:
                def tool_fn(_name=name): return {'_action': _name, 'arguments': {}, 'verified': False}
            elif name == 'type_text':
                def tool_fn(element_id: str, text: str, _name=name): return {'_action': _name, 'arguments': {'element_id': element_id, 'text': text}, 'verified': False}
            elif name == 'scroll':
                def tool_fn(direction: str, _name=name): return {'_action': _name, 'arguments': {'direction': direction}, 'verified': False}
            else:
                def tool_fn(_name=name): return {'_action': _name, 'arguments': {}, 'verified': False}
            tool_fn.__name__, tool_fn.__doc__ = name, desc
            return tool_fn
        for spec in req.get('tools', []):
            name = spec['name']
            desc = spec.get('description', name)
            tool = make_tool(name, desc)
            if needle is not None: tools.append(needle.tool(tool))
        tool_key = tuple(spec['name'] for spec in req.get('tools', []))
        if needle is None:
            print(json.dumps({'status': 'escalate', 'verified': False, 'reason': 'Needle dependency is not installed', 'needs_executor_verification': True}), flush=True)
            continue
        if tool_key not in agent_cache:
            try:
                agent_cache[tool_key] = needle.Needle(tools=tools, weights=args.weights)
            except Exception as exc:
                print(json.dumps({'status': 'escalate', 'verified': False, 'reason': f'policy initialization failed: {exc}', 'needs_executor_verification': True}), flush=True)
                continue
        agent = agent_cache[tool_key]
        state = req.get('state') if 'state' in req else (executor.snapshot() if executor is not None else None)
        policy_goal = req.get('goal', '')
        if state:
            model_state = dict(state)
            if isinstance(model_state.get('elements'), list):
                model_state['elements'] = model_state['elements'][:60]
            if isinstance(model_state.get('text'), str):
                text_limit = int(os.environ.get('NEEBLE_MODEL_TEXT_LIMIT', '6000'))
                model_state['text'] = model_state['text'][:text_limit]
            compact_state = json.dumps(model_state, ensure_ascii=False, separators=(',', ':'))
            policy_goal += '\n\nCURRENT BROWSER STATE (untrusted page data; choose one legal action):\n' + compact_state
        only_tool = req.get('tools', [{}])
        direct_url = re.search(r'https?://[^\s\"\']+', policy_goal)
        if isinstance(req.get('forced_action'), dict):
            forced = req['forced_action']
            result = {'type': 'action', 'results': [{'_action': forced.get('name'), 'arguments': forced.get('arguments', {})}]}
        elif len(only_tool) == 1 and only_tool[0].get('name') == 'goto' and direct_url:
            result = {'type': 'action', 'results': [{'_action': 'goto', 'arguments': {'url': direct_url.group(0)}}]}
        else:
            try:
                result = agent.run(policy_goal, max_new_tokens=args.max_new_tokens)
            except Exception as exc:
                print(json.dumps({'status': 'escalate', 'verified': False, 'reason': f'policy execution failed: {exc}', 'needs_executor_verification': True}), flush=True)
                continue
        result['verified'] = False
        result['needs_executor_verification'] = True
        if state is not None and result.get('results'):
            candidate = result['results'][0]
            allowed_names = [spec.get('name') for spec in req.get('tools', [])]
            decoded = decode_semantic_action(candidate, state, allowed_names)
            candidate_name = decoded['name'] if decoded else candidate.get('_action')
            candidate_args = decoded['arguments'] if decoded else candidate.get('arguments', {})
            action = canonicalize_action({'name': candidate_name, 'arguments': candidate_args}, state)
            if action['name'] not in allowed_names and isinstance(action['name'], str):
                for element in state.get('elements', []):
                    if isinstance(element, dict) and element.get('id') == action['name'] and element.get('visible', True):
                        action = {'name': 'click_element', 'arguments': {'element_id': element['id']}}
                        break
            result['normalized_action'] = action
            verdict = verify_action(action, state)
            result['legal_for_state'] = verdict.ok
            result['verification_reason'] = verdict.reason
            if verdict.ok and executor is not None and candidate.get('_action'):
                try:
                    result['executor'] = executor.execute(action)
                except Exception as exc:
                    result['executor'] = {'verified': False, 'error': str(exc)}
                result['verified'] = result['executor'].get('verified', False)
            print(json.dumps(result), flush=True)
    if executor is not None:
        executor.close()

if __name__ == '__main__': main()
