from babench.runtime import verify_action

STATE = {"elements": [
    {"id": "login", "role": "button", "visible": True},
    {"id": "search", "role": "textbox", "visible": True},
]}

def test_click_known_element():
    assert verify_action({"name": "click_element", "arguments": {"element_id": "login"}}, STATE).ok

def test_stale_element_escalates():
    result = verify_action({"name": "click_element", "arguments": {"element_id": "gone"}}, STATE)
    assert not result.ok

def test_type_requires_textbox():
    result = verify_action({"name": "type_text", "arguments": {"element_id": "login", "text": "x"}}, STATE)
    assert not result.ok
