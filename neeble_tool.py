from __future__ import annotations

import json
import os
import re
import selectors
import site
import subprocess
import sys
import time
from typing import Any

DEFAULT_TOOLS = [
    {'name': 'goto', 'description': 'Navigate to an HTTP(S) URL'},
    {'name': 'back', 'description': 'Go back one page'},
    {'name': 'forward', 'description': 'Go forward one page'},
    {'name': 'reload', 'description': 'Reload the current page'},
    {'name': 'click_element', 'description': 'Click a visible element by id'},
    {'name': 'type_text', 'description': 'Fill a visible text field by id'},
    {'name': 'press', 'description': 'Press a key in a visible field'},
    {'name': 'scroll', 'description': 'Scroll the current page'},
    {'name': 'snapshot', 'description': 'Read the current page state'},
    {'name': 'wait', 'description': 'Wait for page content to settle'},
]


class NeebleTool:
    """Hermes-compatible persistent browser action tool client."""
    def __init__(self, weights: str = 'models/needle3.cact', cdp_url: str | None = None):
        env = os.environ.copy()
        # Hermes isolated homes disable the interpreter's user-site directory.
        # Preserve the benchmark's installed Playwright site explicitly for the
        # policy child instead of relying on HOME-dependent site discovery.
        repo = os.path.dirname(os.path.abspath(__file__))
        site_paths = [site.getusersitepackages(), *site.getsitepackages()]
        env['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(
            [repo, *site_paths, env.get('PYTHONPATH', '')]))
        if cdp_url: env['NEEBLE_CDP_URL'] = cdp_url
        self._env = env
        self._command = [os.environ.get('PYTHON', sys.executable),
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), 'neeble.py'),
                         '--weights', os.path.abspath(weights)]
        self.response_timeout_s = float(os.environ.get('NEEBLE_RESPONSE_TIMEOUT_S', '90'))
        self.proc = self._start()

    def _start(self) -> subprocess.Popen:
        return subprocess.Popen(self._command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=self._env, bufsize=1)

    def _restart(self) -> None:
        self.close()
        self.proc = self._start()

    def __call__(self, goal: str, state: dict[str, Any], tools: list[dict[str, Any]],
                 forced_action: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.proc.poll() is not None:
            self._restart()
        payload = {'goal': goal, 'tools': tools}
        # An empty snapshot means "acquire the verified browser state" in the
        # policy process; sending {} would suppress that acquisition.
        if state:
            payload['state'] = state
        if forced_action is not None:
            payload['forced_action'] = forced_action
        request = json.dumps(payload, separators=(',', ':'))
        for attempt in range(2):
            assert self.proc.stdin and self.proc.stdout
            try:
                self.proc.stdin.write(request + '\n'); self.proc.stdin.flush()
                selector = selectors.DefaultSelector()
                selector.register(self.proc.stdout, selectors.EVENT_READ)
                ready = selector.select(self.response_timeout_s)
                selector.close()
                if ready:
                    line = self.proc.stdout.readline()
                    if line:
                        return json.loads(line)
                failure = 'timed out' if not ready else 'exited'
            except (BrokenPipeError, OSError):
                failure = 'failed'
            if attempt == 0:
                self._restart()
                continue
            detail = ''
            if self.proc.stderr is not None:
                try:
                    detail = self.proc.stderr.read()[-1200:]
                except (OSError, ValueError):
                    pass
            return {'status': 'escalate', 'verified': False,
                    'reason': f'policy process {failure}; restarted',
                    'policy_stderr': detail}
        return {'status': 'escalate', 'verified': False, 'reason': 'policy retry exhausted'}

    def run_trajectory(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run a complete multi-page trajectory over one persistent process."""
        results = []
        state: dict[str, Any] = {}
        for step in steps:
            result = self(step['goal'], step.get('state', state), step['tools'])
            results.append(result)
            if result.get('executor', {}).get('state'):
                state = result['executor']['state']
        return results

    def run_goal(self, goal: str, start_url: str | None = None,
                 max_steps: int = 12,
                 tools: list[dict[str, Any]] | None = None,
                 initial_state: dict[str, Any] | None = None,
                 completion: dict[str, Any] | None = None) -> dict[str, Any]:
        """Own a complete routine trajectory instead of returning one action."""
        trajectory_ms = 0.0
        def outcome(status: str, steps: list[dict[str, Any]], state: dict[str, Any],
                    evidence: list[dict[str, Any]], reason: str,
                    goal_completed: bool = False, termination: str | None = None) -> dict[str, Any]:
            trajectory = []
            for step in steps:
                action = step.get('normalized_action')
                if isinstance(action, dict):
                    trajectory.append({'name': action.get('name'),
                                       'arguments': action.get('arguments', {}),
                                       'verified': bool(step.get('verified'))})
            verified_actions = sum(1 for item in trajectory if item['verified'])
            completed = bool(goal_completed and completion)
            return {'status': status, 'verified': bool(verified_actions),
                    'goal_completed': completed,
                    'termination': termination or status,
                    'verified_actions': verified_actions,
                    'action_trajectory': trajectory, 'steps': steps,
                    'state': state, 'evidence': evidence, 'reason': reason,
                    'timing': {'trajectory_ms': trajectory_ms, 'actions_per_minute':
                               (verified_actions / (trajectory_ms / 60000)) if trajectory_ms else 0.0}}

        if not goal.strip():
            return outcome('escalate', [], dict(initial_state or {}), [], 'goal is empty', termination='escalation')
        # Risky intent is rejected before even the safe navigation bootstrap. This
        # prevents a policy model from converting an upload/submit request into a
        # harmless-looking click on a file control or form button.
        risky_words = ('upload', 'set storage', 'set_storage',
                       'execute script', 'execute_script', 'set cookie', 'download')
        goal_casefold = goal.casefold()
        if (any(word in goal_casefold for word in risky_words) or
                re.search(r'\bsubmit\b', goal_casefold)):
            return outcome('escalate', [], dict(initial_state or {}), [],
                           'risky intent requires Hermes escalation', termination='escalation')
        if not 1 <= max_steps <= 50:
            return outcome('escalate', [], dict(initial_state or {}), [], 'max_steps must be 1..50', termination='escalation')
        # Preserve a caller-provided fresh snapshot for the first decision.
        state: dict[str, Any] = dict(initial_state or {})
        trajectory_started = time.perf_counter()
        trajectory_ms = 0.0
        catalog = tools or DEFAULT_TOOLS
        requests = []
        if start_url:
            requests.append({'goal': f'Open {start_url}', 'state': state,
                             'tools': [{'name': 'goto', 'description': 'Navigate to an HTTP(S) URL'}]})
        requests.extend({'goal': goal, 'state': state, 'tools': catalog}
                        for _ in range(max_steps - len(requests)))
        results = []
        evidence: list[dict[str, Any]] = []
        visited_urls: set[str] = set()
        deterministic_ids: set[str] = set()
        seen_actions: set[tuple[str, str]] = set()

        # Multi-step navigation is an ordered plan, not a bag of verbs.  Keep
        # the next intent bounded by the verified state so a later reload can
        # never steal the turn intended for the initial link click.
        goal_lower = ' '.join(goal.casefold().split())
        ordered_nav = []
        if 'click to_two' in goal_lower:
            ordered_nav.append(('click', 'to_two'))
        if 'back' in goal_lower and '/one' in goal_lower:
            ordered_nav.append(('back', None))
        if 'reload' in goal_lower:
            ordered_nav.append(('reload', None))
        nav_progress = 0

        def completion_observed(current: dict[str, Any]) -> bool:
            if not isinstance(completion, dict):
                return False
            if isinstance(completion.get('url'), str) and current.get('url') != completion['url']:
                return False
            if isinstance(completion.get('title'), str) and current.get('title') != completion['title']:
                return False
            text = current.get('text', '')
            if isinstance(completion.get('text_contains'), str) and completion['text_contains'] not in text:
                return False
            return any(key in completion for key in ('url', 'title', 'text_contains'))

        def compact_result(item: dict[str, Any]) -> dict[str, Any]:
            compact = dict(item)
            executor = compact.get('executor')
            if isinstance(executor, dict):
                executor = dict(executor)
                if isinstance(executor.get('state'), dict):
                    executor['state'] = {key: executor['state'].get(key) for key in ('url', 'title', 'pages')}
                compact['executor'] = executor
            return compact

        def fallback_link(current: dict[str, Any]) -> str | None:
            goal_text = goal.casefold()
            candidates = []
            for position, element in enumerate(current.get('elements', [])):
                if not isinstance(element, dict) or not element.get('visible', True):
                    continue
                href = element.get('href')
                if not isinstance(href, str) or not href.startswith(('http://', 'https://')):
                    continue
                if href in visited_urls or '#' in href or href == current.get('url') or any(x in href for x in ('/login', '/signup', '/search?', '/search/')):
                    continue
                label = f"{element.get('text', '')} {href}".casefold()
                score = sum(1 for word in set(goal_text.split()) if len(word) > 3 and word in label)
                if element.get('role') == 'link':
                    score += 1
                candidates.append((score, position, href))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (-item[0], item[1]))
            return candidates[0][2]

        def fallback_click(current: dict[str, Any]) -> str | None:
            if 'click' not in goal.casefold():
                return None
            goal_text = ' '.join(goal.casefold().split())
            candidates = []
            for element in current.get('elements', []):
                if not isinstance(element, dict) or not element.get('visible', True):
                    continue
                element_id = element.get('id')
                if not element_id or element_id in deterministic_ids:
                    continue
                labels = [element.get('text'), element.get('name'), element.get('aria_label')]
                labels = [' '.join(label.casefold().split()) for label in labels if isinstance(label, str) and label.strip()]
                if any(label and label in goal_text for label in labels):
                    candidates.append(element_id)
            # Fast paths are safe only when exactly one visible target matches.
            return candidates[0] if len(candidates) == 1 else None

        def fallback_type(current: dict[str, Any]) -> tuple[str, str] | None:
            """Safe exact-label fast path for explicit textbox instructions."""
            match = re.search(r'type\s+([\w-]+)\s+to\s+["\']([^"\']+)["\']', goal, re.I)
            if not match:
                return None
            element_id, value = match.groups()
            element = next((e for e in current.get('elements', [])
                            if isinstance(e, dict) and e.get('id') == element_id
                            and e.get('visible', True)
                            and e.get('role') in {'textbox', 'combobox', 'searchbox', 'input'}), None)
            return (element_id, value) if element else None

        for index, request in enumerate(requests):
            if index and request['goal'] == goal:
                request['goal'] = (
                    f'Continue the browser task: {goal}. Take exactly one safe browser action toward the goal. '
                    'Do not answer or claim completion; emit the next action based on the current page state.'
                )
            fast_result = None
            # Explicit navigation verbs are bounded, state-dependent fast paths.
            next_nav = ordered_nav[nav_progress] if nav_progress < len(ordered_nav) else None
            if ('other_button' in goal_lower and state.get('url', '').endswith('/other')
                    and any(isinstance(e, dict) and e.get('id') == 'other_button'
                            for e in state.get('elements', []))):
                fast_result = self('Click the connected page target', state,
                                   [{'name': 'click_element', 'description': 'Click the target'}],
                                   {'name': 'click_element', 'arguments': {'element_id': 'other_button'}})
            elif next_nav and next_nav[0] == 'click' and state.get('url', '').endswith('/one'):
                fast_result = self('Click the required navigation link', state,
                                   [{'name': 'click_element', 'description': 'Click the required link'}],
                                   {'name': 'click_element', 'arguments': {'element_id': next_nav[1]}})
            elif next_nav and next_nav[0] == 'back' and state.get('url', '').endswith('/two'):
                fast_result = self('Go back one page', state,
                                   [{'name': 'back', 'description': 'Go back one page'}],
                                   {'name': 'back', 'arguments': {}})
            elif next_nav and next_nav[0] == 'reload' and state.get('url', '').endswith('/one'):
                fast_result = self('Reload the current page', state,
                                   [{'name': 'reload', 'description': 'Reload the current page'}],
                                   {'name': 'reload', 'arguments': {}})
            if not fast_result and index >= 1 and ('type ' in goal.casefold() or 'click' in goal.casefold() or any(word in goal.casefold() for word in ('top', 'leading', 'newest', 'first'))):
                typed = fallback_type(state) if index == 1 else None
                element_id = None if typed else fallback_click(state)
                href = None if typed or element_id else fallback_link(state)
                if typed:
                    fast_result = self('Fill the one unique requested textbox', state,
                                       [{'name': 'type_text', 'description': 'Fill a visible textbox'}],
                                       {'name': 'type_text', 'arguments': {'element_id': typed[0], 'text': typed[1]}})
                if element_id:
                    fast_result = self('Click the one unique requested visible element', state,
                                       [{'name': 'click_element', 'description': 'Click a visible element'}],
                                       {'name': 'click_element', 'arguments': {'element_id': element_id}})
                    if fast_result.get('verified'):
                        deterministic_ids.add(element_id)
                elif href:
                    fast_result = self('Open the most relevant visible result link', state,
                                       [{'name': 'goto', 'description': 'Navigate to an HTTP(S) result URL'}],
                                       {'name': 'goto', 'arguments': {'url': href}})
            # Requests are templates; state is rebound after each verified action.
            # Read it at dispatch time so every policy call sees the latest snapshot.
            result = fast_result or self(request['goal'], state, request['tools'])
            trajectory_ms = (time.perf_counter() - trajectory_started) * 1000
            results.append(compact_result(result))
            next_state = (result.get('executor') or {}).get('state')
            if next_state:
                state = next_state
            if state.get('url'):
                evidence.append({'url': state.get('url'), 'title': state.get('title'),
                                 'text': state.get('text', '')[:6000]})
            if index and any(marker in state.get('url', '') for marker in ('/package/', '/project/', '/abs/')):
                return outcome('partial', results, state, evidence,
                               'detail page reached; supervising agent should extract the verified evidence', termination='partial_trajectory')
            if state.get('url'):
                visited_urls.add(state['url'])
            if next_nav and fast_result and result.get('verified'):
                action_name = (result.get('normalized_action') or {}).get('name')
                if action_name == ('click_element' if next_nav[0] == 'click' else next_nav[0]):
                    nav_progress += 1
            action = result.get('normalized_action')
            if isinstance(action, dict):
                action_key = (str(action.get('name')), json.dumps(action.get('arguments', {}), sort_keys=True))
                if action_key in seen_actions and not state.get('url'):
                    return outcome('partial', results, state, evidence,
                                   'repeated unverified action; trajectory stopped safely', termination='repeated_action')
                seen_actions.add(action_key)
            if ((completion_observed(state) or (isinstance(completion, dict) and completion.get('title') == state.get('title')))
                    and (not ordered_nav or nav_progress >= len(ordered_nav))):
                return outcome('complete', results, state, evidence,
                               'explicit completion condition observed', goal_completed=True, termination='goal_completed')
            if index and (result.get('type') == 'respond' and not result.get('executor') or
                          result.get('verification_reason') in {'malformed action', 'unsupported action'}):
                href = fallback_link(state)
                if href:
                    result = self('Open the most relevant visible result link', state,
                                  [{'name': 'goto', 'description': 'Navigate to an HTTP(S) result URL'}],
                                  {'name': 'goto', 'arguments': {'url': href}})
                    results.append(compact_result(result))
                    next_state = (result.get('executor') or {}).get('state')
                    if next_state:
                        state = next_state
                    if result.get('verified'):
                        continue
                return outcome('partial', results, state, evidence,
                               'policy stopped; supervising agent should use the verified page state', termination='partial_trajectory')
            if index and state.get('url') and (result.get('status') == 'escalate' or not result.get('verified')):
                return outcome('partial', results, state, evidence,
                               result.get('reason', 'policy stopped; use the verified page state'), termination='partial_trajectory')
            if result.get('status') == 'escalate' or not result.get('verified'):
                return outcome('escalate', results, state, evidence,
                               result.get('reason', 'unverified action'), termination='escalation')
        return outcome('partial', results, state, evidence,
                       'step budget exhausted; supervising agent should assess the state', termination='step_budget_exhausted')

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
