from babench.runtime import verify_action

STATE = {"elements": [
    {"id": "login", "role": "button", "visible": True},
    {"id": "search", "role": "textbox", "visible": True},
]}

def test_click_known_element():
    assert verify_action({"name": "click_element", "arguments": {"element_id": "login"}}, STATE).ok

def test_stale_element_escalates():
    assert not verify_action({"name": "click_element", "arguments": {"element_id": "gone"}}, STATE).ok

def test_natural_label_resolves_to_id():
    state = {"elements": [{"id": "login", "role": "button", "text": "Log in", "visible": True}]}
    assert verify_action({"name": "click_element", "arguments": {"element_id": "login button"}}, state).ok

def test_type_requires_textbox():
    assert not verify_action({"name": "type_text", "arguments": {"element_id": "login", "text": "x"}}, STATE).ok
