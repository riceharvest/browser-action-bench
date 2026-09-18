from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class Verification:
    ok: bool
    reason: str


ROUTINE_ACTIONS = {
    "goto", "back", "forward", "reload", "click_element", "type_text",
    "double_click", "right_click", "hover", "press", "scroll",
    "scroll_into_view", "wait", "snapshot", "focus", "blur", "clear",
    "select_option", "check", "uncheck", "get_url", "get_title", "get_text",
    "find", "new_tab", "refresh_snapshot",
}
RISKY_ACTIONS = {
    "submit", "upload_file", "set_cookie", "set_storage", "execute_script",
    "download", "close_tab", "close_window", "paste", "cut",
}

def canonicalize_action(action: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Resolve a bounded natural element label to the current canonical ID."""
    result = dict(action)
    args = dict(action.get("arguments", {}))
    result["arguments"] = args
    elements = {e.get("id"): e for e in state.get("elements", [])
                if isinstance(e, dict) and isinstance(e.get("id"), str)}
    raw = args.get("element_id")
    if not isinstance(raw, str) or raw in elements:
        return result
    wanted = " ".join(raw.casefold().split())
    wanted_base = wanted[:-7].strip() if wanted.endswith(" button") else wanted
    for element_id, element in elements.items():
        labels = [element.get("text"), element.get("name"), element.get("aria_label")]
        normalized_labels = {" ".join(label.casefold().split()) for label in labels if isinstance(label, str)}
        if wanted_base == str(element_id).casefold() or wanted in normalized_labels or wanted_base in normalized_labels:
            args["element_id"] = element_id
            break
    return result


def decode_semantic_action(candidate: dict[str, Any], state: dict[str, Any],
                           allowed_names: list[str]) -> dict[str, Any] | None:
    """Decode a semantic label only on an exact, unique visible match."""
    if not isinstance(candidate, dict) or not isinstance(state, dict):
        return None
    raw_name = candidate.get("_action")
    args = candidate.get("arguments") if isinstance(candidate.get("arguments"), dict) else {}
    if raw_name in allowed_names:
        return {"name": raw_name, "arguments": dict(args)}
    wanted = raw_name if isinstance(raw_name, str) else args.get("element_id")
    if isinstance(wanted, str):
        wanted = " ".join(wanted.casefold().split())
    # Needle may put the semantic action in _action and the exact element id in args.
    # Prefer the action label, then fall back to that exact supplied argument.
    candidates = [wanted]
    if isinstance(args.get("element_id"), str):
        candidates.append(" ".join(args["element_id"].casefold().split()))
    if not any(candidates):
        return None
    matches = []
    for element in state.get("elements", []):
        if not isinstance(element, dict) or not element.get("visible", True):
            continue
        labels = [element.get(key) for key in ("id", "text", "name", "aria_label")]
        if any(isinstance(label, str) and " ".join(label.casefold().split()) in candidates for label in labels):
            matches.append(element)
    if len(matches) != 1 or "click_element" not in allowed_names:
        return None
    return {"name": "click_element", "arguments": {"element_id": matches[0].get("id")}}


def verify_action(action: dict[str, Any], state: dict[str, Any]) -> Verification:
    """Validate a model action against the latest compact browser state."""
    name = action.get("name")
    args = action.get("arguments", {})
    if not isinstance(name, str) or not isinstance(args, dict):
        return Verification(False, "malformed action")
    if not isinstance(state, dict) or not isinstance(state.get("elements", []), list):
        return Verification(False, "missing or malformed browser state")
    if name not in ROUTINE_ACTIONS and name not in RISKY_ACTIONS:
        return Verification(False, "unsupported action")
    if name in RISKY_ACTIONS:
        return Verification(False, "risky action requires Hermes escalation")
    elements = {e.get("id"): e for e in state.get("elements", [])
                if isinstance(e, dict) and isinstance(e.get("id"), str)}

    def resolve_element_id(raw: Any) -> str | None:
        if isinstance(raw, str) and raw in elements:
            return raw
        if not isinstance(raw, str):
            return None
        wanted = " ".join(raw.casefold().split())
        wanted_base = wanted[:-7].strip() if wanted.endswith(" button") else wanted
        for element_id, element in elements.items():
            if wanted_base == str(element_id).casefold():
                return element_id
            labels = [element.get("text"), element.get("name"), element.get("aria_label")]
            for label in labels:
                if not isinstance(label, str):
                    continue
                normalized = " ".join(label.casefold().split())
                if normalized == wanted or normalized == wanted_base or (normalized.endswith(" button") and normalized[:-7].strip() == wanted_base):
                    return element_id
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
        if not elements[element_id].get("visible", True):
            return Verification(False, "target is not visible")
        if elements[element_id].get("role") not in {"textbox", "combobox", "searchbox"}:
            return Verification(False, "target is not text-editable")
    if name in {"select_option", "scroll_into_view", "press"}:
        if resolve_element_id(args.get("element_id")) not in elements:
            return Verification(False, "stale or unknown element_id")
    if name == "goto":
        url = args.get("url")
        if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"}:
            return Verification(False, "goto requires an http(s) URL")
    if name == "type_text" and not isinstance(args.get("text"), str):
        return Verification(False, "type_text requires text")
    return Verification(True, "action is legal for current state")
