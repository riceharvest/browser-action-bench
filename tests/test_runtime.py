from babench.runtime import canonicalize_action, decode_semantic_action, verify_action
from neeble_mcp import SCHEMA
from benchmark_scenarios import SCENARIOS
from benchmark_domains import DOMAIN_SCENARIOS
from neeble_tool import NeebleTool
from baseline_mcp import Server

STATE = {"elements": [
    {"id": "login", "role": "button", "visible": True},
    {"id": "search", "role": "textbox", "visible": True},
]}

def test_click_known_element():
    assert verify_action({"name": "click_element", "arguments": {"element_id": "login"}}, STATE).ok

def test_baseline_click_validation_uses_inner_snapshot_state():
    server = object.__new__(Server)
    snapshot = {"url": "http://local/", "title": "Login",
                "state": {"url": "http://local/", "title": "Login",
                          "elements": [{"id": "login", "role": "button", "visible": True}]}}
    state = server._validation_state(snapshot)
    assert verify_action({"name": "click_element", "arguments": {"element_id": "login"}}, state).ok

def test_baseline_validation_state_preserves_outer_metadata():
    server = object.__new__(Server)
    state = server._validation_state({"url": "http://local/", "title": "T", "state": {"elements": []}})
    assert state["url"] == "http://local/"
    assert state["title"] == "T"

def test_stale_element_escalates():
    assert not verify_action({"name": "click_element", "arguments": {"element_id": "gone"}}, STATE).ok

def test_natural_label_resolves_to_id():
    state = {"elements": [{"id": "login", "role": "button", "text": "Log in", "visible": True}]}
    assert verify_action({"name": "click_element", "arguments": {"element_id": "login button"}}, state).ok

def test_type_requires_textbox():
    assert not verify_action({"name": "type_text", "arguments": {"element_id": "login", "text": "x"}}, STATE).ok

def test_unsupported_action_is_rejected():
    verdict = verify_action({"name": "execute_script", "arguments": {}}, STATE)
    assert not verdict.ok
    assert "risky" in verdict.reason

def test_substring_label_does_not_guess():
    state = {"elements": [{"id": "help", "role": "button", "text": "Help center", "visible": True}]}
    assert verify_action({"name": "click_element", "arguments": {"element_id": "help"}}, state).ok
    assert not verify_action({"name": "click_element", "arguments": {"element_id": "hel"}}, state).ok

def test_goto_requires_http_url():
    assert not verify_action({"name": "goto", "arguments": {"url": "javascript:alert(1)"}}, {}).ok

def test_mcp_tool_is_high_level_and_does_not_require_browser_state():
    schema = SCHEMA["inputSchema"]
    assert schema["required"] == ["goal"]
    assert "max_steps" in schema["properties"]
    assert "start_url" in schema["properties"]
    assert "completion" in schema["properties"]

def test_canonicalize_natural_label_before_execution():
    state = {"elements": [{"id": "login", "role": "button", "text": "Log in", "visible": True}]}
    action = canonicalize_action({"name": "click_element", "arguments": {"element_id": "Log in"}}, state)
    assert action["arguments"]["element_id"] == "login"

def test_semantic_label_accepts_unique_visible_element():
    assert decode_semantic_action({"_action": "Log in", "arguments": {}},
        {"elements": [{"id": "login", "text": "Log in", "visible": True}]}, ["click_element"]) == {
            "name": "click_element", "arguments": {"element_id": "login"}}

def test_semantic_label_rejects_ambiguous_or_unknown():
    state = {"elements": [{"id": "a", "text": "Log in", "visible": True},
                           {"id": "b", "text": "Log in", "visible": True}]}
    assert decode_semantic_action({"_action": "Log in", "arguments": {}}, state, ["click_element"]) is None
    assert decode_semantic_action({"_action": "Login", "arguments": {}}, {"elements": []}, ["click_element"]) is None

def test_benchmark_scenarios_have_distinct_live_tasks():
    names = [scenario.name for scenario in SCENARIOS]
    assert len(names) >= 5
    assert len(names) == len(set(names))
    assert all(scenario.required_values for scenario in SCENARIOS)

def test_domain_benchmark_scenarios_are_independent():
    names = [scenario.name for scenario in DOMAIN_SCENARIOS]
    starts = [scenario.start_url.split('/')[2] for scenario in DOMAIN_SCENARIOS]
    assert len(names) >= 5
    assert len(names) == len(set(names))
    assert len(starts) == len(set(starts))

def test_run_goal_preserves_initial_state_for_first_policy_call(monkeypatch):
    seen = []
    def fake_call(self, goal, state, tools, forced_action=None):
        seen.append(state)
        return {'status': 'escalate', 'verified': False, 'reason': 'test stop'}
    monkeypatch.setattr(NeebleTool, '__call__', fake_call)
    tool = object.__new__(NeebleTool)
    result = tool.run_goal('Inspect this page', max_steps=1,
                           initial_state={'url': 'http://local/', 'elements': []})
    assert result['status'] == 'escalate'
    assert seen[0]['url'] == 'http://local/'


def test_run_goal_passes_latest_verified_state_to_step_two(monkeypatch):
    seen = []
    states = [
        {'url': 'http://local/first', 'title': 'First', 'elements': []},
        {'url': 'http://local/second', 'title': 'Second', 'elements': []},
    ]

    def fake_call(self, goal, state, tools, forced_action=None):
        seen.append(dict(state))
        current = states[len(seen) - 1]
        return {'status': 'ok', 'verified': True,
                'executor': {'state': current}}

    monkeypatch.setattr(NeebleTool, '__call__', fake_call)
    tool = object.__new__(NeebleTool)
    result = tool.run_goal('Inspect this page', max_steps=2,
                           initial_state={'url': 'http://local/initial'})

    assert result['status'] == 'partial'
    assert [state['url'] for state in seen] == [
        'http://local/initial', 'http://local/first']


def test_run_goal_distinguishes_action_verification_from_goal_completion(monkeypatch):
    def fake_call(self, goal, state, tools, forced_action=None):
        name = tools[0]['name']
        return {'status': 'ok', 'verified': True,
                'normalized_action': {'name': name, 'arguments': {}},
                'executor': {'state': {'url': 'http://local/page', 'elements': []}}}
    monkeypatch.setattr(NeebleTool, '__call__', fake_call)
    tool = object.__new__(NeebleTool)
    result = tool.run_goal('Do two safe actions', max_steps=2,
                           initial_state={'url': 'http://local/start', 'elements': []})
    assert result['verified'] is True
    assert result['verified_actions'] == 2
    assert result['goal_completed'] is False
    assert result['termination'] == 'step_budget_exhausted'
    assert [item["name"] for item in result['action_trajectory']] == ['goto', 'goto']

def test_run_goal_requires_explicit_observed_completion(monkeypatch):
    def fake_call(self, goal, state, tools, forced_action=None):
        return {'status': 'ok', 'verified': True,
                'normalized_action': {'name': 'snapshot', 'arguments': {}},
                'executor': {'state': {'url': 'http://local/done', 'title': 'Done', 'text': 'finished', 'elements': []}}}
    monkeypatch.setattr(NeebleTool, '__call__', fake_call)
    tool = object.__new__(NeebleTool)
    partial = tool.run_goal('finish', max_steps=1, initial_state={'url': 'http://local/start'}, completion=None)
    complete = tool.run_goal('finish', max_steps=1, initial_state={'url': 'http://local/start'},
                             completion={'title': 'Done'})
    assert partial['goal_completed'] is False
    assert complete['goal_completed'] is True
    assert complete['termination'] == 'goal_completed'
    assert complete['timing']['actions_per_minute'] >= 0


def test_run_goal_escalates_submit_intent_before_navigation(monkeypatch):
    def fail_call(*args, **kwargs):
        raise AssertionError('risky intent must not reach the policy or browser executor')
    monkeypatch.setattr(NeebleTool, '__call__', fail_call)
    tool = object.__new__(NeebleTool)
    result = tool.run_goal('Submit the risky form',
                           start_url='http://local/risky', max_steps=4)
    assert result['status'] == 'escalate'
    assert result['termination'] == 'escalation'
    assert result['verified_actions'] == 0
    assert result['action_trajectory'] == []
