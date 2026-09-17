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
    def resolve_element_id(raw: Any) -> str | None:
        if raw in elements: return raw
        needle_text = str(raw).lower().replace(' button', '').strip()
        for element_id, element in elements.items():
            label = str(element.get('text', '')).lower().strip()
            if needle_text and (needle_text == label or needle_text in label): return element_id
        return None

    if name in {"click_element", "focus", "blur", "clear", "check", "uncheck"}:
        element_id = resolve_element_id(args.get("element_id"))
        if element_id not in elements:
            return Verification(False, "stale or unknown element_id")
        if not elements[element_id].get("visible", True):
            return Verification(False, "target is not visible")
    if name == "type_text":
        element_id = resolve_element_id(args.get("element_id"))
        if element_id not in elements:
            return Verification(False, "stale or unknown element_id")
        if elements[element_id].get("role") not in {"textbox", "combobox", "searchbox"}:
            return Verification(False, "target is not text-editable")
    if name == "select_option" and args.get("element_id") not in elements:
        return Verification(False, "stale or unknown element_id")
    return Verification(True, "action is legal for current state")
