use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use thiserror::Error;
use top_shooter_contracts::CanonicalEvent;

const MAX_CONFIG_BYTES: usize = 65_536;
const MAX_ROUTES: usize = 64;
const MAX_TOOLS: usize = 32;
const MAX_STATIC_CONTENT_BYTES: usize = 256;
const COMPILED_TOOL_REGISTRY: &[&str] = &["discord.reply"];

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Deserialize)]
pub enum AutonomyLevel {
    A0,
    A1,
    A2,
    A3,
    A4,
    A5,
}

impl AutonomyLevel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::A0 => "A0",
            Self::A1 => "A1",
            Self::A2 => "A2",
            Self::A3 => "A3",
            Self::A4 => "A4",
            Self::A5 => "A5",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum RiskLevel {
    R0,
    R1,
    R2,
    R3,
    R4,
    R5,
}

impl RiskLevel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::R0 => "R0",
            Self::R1 => "R1",
            Self::R2 => "R2",
            Self::R3 => "R3",
            Self::R4 => "R4",
            Self::R5 => "R5",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RouteOutcome {
    Ignore,
    ExecuteTool,
    RequestHumanReview,
}

impl RouteOutcome {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Ignore => "ignore",
            Self::ExecuteTool => "execute_tool",
            Self::RequestHumanReview => "request_human_review",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Decision {
    route_id: String,
    outcome: RouteOutcome,
    autonomy: AutonomyLevel,
    risk: RiskLevel,
    tool_id: Option<String>,
    policy_version: String,
    policy_digest: String,
    actor_is_bot: bool,
    security_signal: bool,
}

impl Decision {
    pub fn route_id(&self) -> &str {
        &self.route_id
    }

    pub fn outcome(&self) -> RouteOutcome {
        self.outcome
    }

    pub fn autonomy(&self) -> AutonomyLevel {
        self.autonomy
    }

    pub fn risk(&self) -> RiskLevel {
        self.risk
    }

    pub fn tool_id(&self) -> Option<&str> {
        self.tool_id.as_deref()
    }

    pub fn policy_version(&self) -> &str {
        &self.policy_version
    }

    pub fn policy_digest(&self) -> &str {
        &self.policy_digest
    }

    pub fn actor_is_bot(&self) -> bool {
        self.actor_is_bot
    }

    pub fn security_signal(&self) -> bool {
        self.security_signal
    }
}

#[derive(Debug, Clone, Copy)]
pub struct GuardContext<'a> {
    pub compiled_tools: &'a [&'a str],
    pub approval_present: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Authorization {
    Allowed,
    NoAction,
    Denied(String),
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ControlError {
    #[error("control-plane document is empty or too large")]
    InvalidDocumentSize,
    #[error("YAML aliases, custom tags, and multiple documents are prohibited")]
    ProhibitedYamlFeature,
    #[error("control-plane YAML is invalid: {0}")]
    InvalidYaml(String),
    #[error("unsupported control-plane schema version")]
    UnsupportedSchemaVersion,
    #[error("policy version is invalid")]
    InvalidPolicyVersion,
    #[error("control-plane cardinality exceeds limits")]
    CardinalityExceeded,
    #[error("duplicate tool or route identifier")]
    DuplicateIdentifier,
    #[error("tool is not in the compiled registry: {0}")]
    UnknownTool(String),
    #[error("route references an invalid tool or outcome")]
    InvalidRoute,
    #[error("no route decision could be produced")]
    NoRoute,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ControlDocument {
    schema_version: u16,
    policy_version: String,
    tools: Vec<ToolPolicy>,
    routes: Vec<RoutePolicy>,
    default_route: DefaultRoute,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct ToolPolicy {
    id: String,
    risk: RiskLevel,
    max_autonomy: AutonomyLevel,
    static_content: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RoutePolicy {
    id: String,
    priority: i32,
    event_type: String,
    when: RouteConditions,
    outcome: RouteOutcome,
    tool: Option<String>,
    autonomy: AutonomyLevel,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct RouteConditions {
    actor_is_bot: bool,
    mentions_top_shooter: bool,
    security_signal: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct DefaultRoute {
    id: String,
    outcome: RouteOutcome,
    autonomy: AutonomyLevel,
}

#[derive(Debug, Clone)]
pub struct ControlPlane {
    document: ControlDocument,
    digest: String,
}

impl ControlPlane {
    pub fn from_yaml(input: &str) -> Result<Self, ControlError> {
        if input.is_empty() || input.len() > MAX_CONFIG_BYTES {
            return Err(ControlError::InvalidDocumentSize);
        }
        reject_prohibited_yaml_features(input)?;
        let document: ControlDocument = serde_yaml_ng::from_str(input)
            .map_err(|error| ControlError::InvalidYaml(error.to_string()))?;
        validate_document(&document)?;
        let digest = hex::encode(Sha256::digest(input.as_bytes()));
        Ok(Self { document, digest })
    }

    pub fn route(&self, event: &CanonicalEvent) -> Result<Decision, ControlError> {
        let mut routes: Vec<&RoutePolicy> = self.document.routes.iter().collect();
        routes.sort_by_key(|route| std::cmp::Reverse(route.priority));

        let selected = routes.into_iter().find(|route| {
            route.event_type == event.event_type.as_str()
                && route.when.actor_is_bot == event.actor.is_bot
                && route.when.mentions_top_shooter == event.payload.mentions_top_shooter
                && route.when.security_signal == event.payload.security_signal
        });

        if let Some(route) = selected {
            let risk = route
                .tool
                .as_deref()
                .and_then(|tool_id| self.document.tools.iter().find(|tool| tool.id == tool_id))
                .map_or(RiskLevel::R0, |tool| tool.risk);
            return Ok(Decision {
                route_id: route.id.clone(),
                outcome: route.outcome,
                autonomy: route.autonomy,
                risk,
                tool_id: route.tool.clone(),
                policy_version: self.document.policy_version.clone(),
                policy_digest: self.digest.clone(),
                actor_is_bot: event.actor.is_bot,
                security_signal: event.payload.security_signal,
            });
        }

        Ok(Decision {
            route_id: self.document.default_route.id.clone(),
            outcome: self.document.default_route.outcome,
            autonomy: self.document.default_route.autonomy,
            risk: RiskLevel::R0,
            tool_id: None,
            policy_version: self.document.policy_version.clone(),
            policy_digest: self.digest.clone(),
            actor_is_bot: event.actor.is_bot,
            security_signal: event.payload.security_signal,
        })
    }

    pub fn authorize(&self, decision: &Decision, context: GuardContext<'_>) -> Authorization {
        if decision.policy_version != self.document.policy_version
            || decision.policy_digest != self.digest
        {
            return Authorization::Denied("policy_provenance_mismatch".to_owned());
        }
        let route_matches = self
            .document
            .routes
            .iter()
            .find(|route| route.id == decision.route_id)
            .is_some_and(|route| {
                route.outcome == decision.outcome
                    && route.autonomy == decision.autonomy
                    && route.tool == decision.tool_id
            })
            || (self.document.default_route.id == decision.route_id
                && self.document.default_route.outcome == decision.outcome
                && self.document.default_route.autonomy == decision.autonomy
                && decision.tool_id.is_none());
        if !route_matches {
            return Authorization::Denied("route_provenance_mismatch".to_owned());
        }
        if decision.outcome != RouteOutcome::ExecuteTool {
            return Authorization::NoAction;
        }
        if decision.actor_is_bot || decision.security_signal {
            return Authorization::Denied("untrusted_context_not_actionable".to_owned());
        }
        let Some(tool_id) = decision.tool_id.as_deref() else {
            return Authorization::Denied("missing_tool".to_owned());
        };
        if !COMPILED_TOOL_REGISTRY.contains(&tool_id) || !context.compiled_tools.contains(&tool_id)
        {
            return Authorization::Denied("tool_not_compiled".to_owned());
        }
        let Some(tool) = self.document.tools.iter().find(|tool| tool.id == tool_id) else {
            return Authorization::Denied("tool_not_configured".to_owned());
        };
        if decision.autonomy > tool.max_autonomy {
            return Authorization::Denied("autonomy_exceeds_tool_limit".to_owned());
        }
        if decision.autonomy >= AutonomyLevel::A4 && !context.approval_present {
            return Authorization::Denied("human_approval_required".to_owned());
        }
        if !matches!(tool.risk, RiskLevel::R0 | RiskLevel::R1) {
            return Authorization::Denied("risk_not_enabled_in_phase_1".to_owned());
        }
        Authorization::Allowed
    }

    pub fn static_tool_content(&self, tool_id: &str) -> Option<&str> {
        self.document
            .tools
            .iter()
            .find(|tool| tool.id == tool_id)
            .map(|tool| tool.static_content.as_str())
    }
}

fn validate_document(document: &ControlDocument) -> Result<(), ControlError> {
    if document.schema_version != 1 {
        return Err(ControlError::UnsupportedSchemaVersion);
    }
    if !valid_identifier(&document.policy_version) {
        return Err(ControlError::InvalidPolicyVersion);
    }
    if document.tools.is_empty()
        || document.tools.len() > MAX_TOOLS
        || document.routes.is_empty()
        || document.routes.len() > MAX_ROUTES
    {
        return Err(ControlError::CardinalityExceeded);
    }

    let mut identifiers = HashSet::new();
    for tool in &document.tools {
        if !valid_identifier(&tool.id) {
            return Err(ControlError::InvalidRoute);
        }
        if !identifiers.insert(format!("tool:{}", tool.id)) {
            return Err(ControlError::DuplicateIdentifier);
        }
        if !COMPILED_TOOL_REGISTRY.contains(&tool.id.as_str()) {
            return Err(ControlError::UnknownTool(tool.id.clone()));
        }
        if tool.static_content.is_empty()
            || tool.static_content.len() > MAX_STATIC_CONTENT_BYTES
            || tool.static_content.contains(['\r', '\n'])
        {
            return Err(ControlError::InvalidRoute);
        }
    }

    for route in &document.routes {
        if !valid_identifier(&route.id) {
            return Err(ControlError::InvalidRoute);
        }
        if !identifiers.insert(format!("route:{}", route.id)) {
            return Err(ControlError::DuplicateIdentifier);
        }
        if route.event_type != "message.created" {
            return Err(ControlError::InvalidRoute);
        }
        match route.outcome {
            RouteOutcome::ExecuteTool => {
                let Some(tool_id) = route.tool.as_deref() else {
                    return Err(ControlError::InvalidRoute);
                };
                if !document.tools.iter().any(|tool| tool.id == tool_id) {
                    return Err(ControlError::UnknownTool(tool_id.to_owned()));
                }
            }
            RouteOutcome::Ignore | RouteOutcome::RequestHumanReview => {
                if route.tool.is_some() {
                    return Err(ControlError::InvalidRoute);
                }
            }
        }
    }

    if !valid_identifier(&document.default_route.id)
        || document.default_route.outcome != RouteOutcome::Ignore
        || document.default_route.autonomy != AutonomyLevel::A0
    {
        return Err(ControlError::InvalidRoute);
    }
    Ok(())
}

fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn reject_prohibited_yaml_features(input: &str) -> Result<(), ControlError> {
    if input.bytes().any(|byte| matches!(byte, b'&' | b'*' | b'!')) {
        return Err(ControlError::ProhibitedYamlFeature);
    }
    let meaningful: Vec<&str> = input
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .collect();
    if meaningful
        .iter()
        .any(|line| *line == "---" || *line == "..." || line.starts_with('%'))
    {
        return Err(ControlError::ProhibitedYamlFeature);
    }
    Ok(())
}
