from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Verification:
    ok: bool
    reason: str


def verify_action(action: dict[str, Any], state: dict[str, Any]) -> Verification:
    """Validate a model action against the latest compact browser state."""
    name = action.get("name")
    args = action.get("arguments", {})
    if not isinstance(name, str) or not isinstance(args, dict):
        return Verification(False, "malformed action")
    elements = {e.get("id"): e for e in state.get("elements", []) if isinstance(e, dict)}
    if name in {"click_element", "focus", "blur", "clear", "check", "uncheck"}:
        element_id = args.get("element_id")
        if element_id not in elements:
            return Verification(False, "stale or unknown element_id")
        if not elements[element_id].get("visible", True):
            return Verification(False, "target is not visible")
    if name == "type_text":
        element_id = args.get("element_id")
        if element_id not in elements:
            return Verification(False, "stale or unknown element_id")
        if elements[element_id].get("role") not in {"textbox", "combobox", "searchbox"}:
            return Verification(False, "target is not text-editable")
    if name == "select_option" and args.get("element_id") not in elements:
        return Verification(False, "stale or unknown element_id")
    return Verification(True, "action is legal for current state")
