use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BrowserAction {
    pub name: String,
    #[serde(default)]
    pub arguments: Value,
}
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Decision {
    Execute,
    Escalate,
}
#[derive(Debug, thiserror::Error, PartialEq)]
pub enum ValidationError {
    #[error("unknown action: {0}")]
    UnknownAction(String),
    #[error("risky action requires escalation")]
    Risky,
    #[error("confidence below threshold")]
    LowConfidence,
}
const ROUTINE: &[&str] = &[
    "click_element",
    "type",
    "scroll",
    "scroll_into_view",
    "wait",
    "wait_for_selector",
    "snapshot",
    "get_url",
    "get_title",
    "get_text",
    "find",
    "focus",
    "blur",
    "select_option",
    "check",
    "uncheck",
    "clear",
];
const RISKY: &[&str] = &[
    "upload_file",
    "submit",
    "set_cookie",
    "set_storage",
    "execute_script",
    "download",
    "close_tab",
    "close_window",
    "goto",
];
pub fn decide(
    action: &BrowserAction,
    confidence: Option<f32>,
    threshold: f32,
) -> Result<Decision, ValidationError> {
    if !ROUTINE.contains(&action.name.as_str()) && !RISKY.contains(&action.name.as_str()) {
        return Err(ValidationError::UnknownAction(action.name.clone()));
    }
    if RISKY.contains(&action.name.as_str()) {
        return Err(ValidationError::Risky);
    }
    if confidence.unwrap_or(0.0) < threshold {
        return Err(ValidationError::LowConfidence);
    }
    Ok(Decision::Execute)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn action(name: &str) -> BrowserAction {
        BrowserAction {
            name: name.into(),
            arguments: Value::Null,
        }
    }
    #[test]
    fn routine_high_confidence_executes() {
        assert_eq!(
            decide(&action("click_element"), Some(0.9), 0.7),
            Ok(Decision::Execute)
        );
    }
    #[test]
    fn low_confidence_escalates() {
        assert_eq!(
            decide(&action("click_element"), Some(0.2), 0.7),
            Err(ValidationError::LowConfidence)
        );
    }
    #[test]
    fn risky_escalates() {
        assert_eq!(
            decide(&action("submit"), Some(1.0), 0.7),
            Err(ValidationError::Risky)
        );
    }
}
