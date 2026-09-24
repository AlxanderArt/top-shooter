use chrono::{DateTime, Utc};
use std::sync::{Arc, Mutex};
use thiserror::Error;
use top_shooter_contracts::{
    ContractError, DiscordId, RawDiscordMessageEvent, normalize_message_event,
};
use top_shooter_control::{Authorization, ControlError, ControlPlane, GuardContext};
use top_shooter_store::{
    AuditIntent, IntentDisposition, PostgresAuditStore, StoreError, ToolOutcome,
};
use uuid::Uuid;

const COMPILED_PHASE_1_TOOLS: &[&str] = &["discord.reply"];

#[derive(Debug, Clone, Copy)]
pub struct PipelineIds {
    pub event_id: Uuid,
    pub correlation_id: Uuid,
    pub tool_call_id: Uuid,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PipelineResult {
    SimulatedSuccess,
    IgnoredAudited,
    Replayed { correlation_id: Uuid },
}

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("event contract rejected input: {0}")]
    Contract(#[from] ContractError),
    #[error("control plane failed closed: {0}")]
    Control(#[from] ControlError),
    #[error("Discord ID cannot be represented by the PostgreSQL BIGINT contract")]
    DiscordIdOutOfRange,
    #[error("authorized tool has no static content")]
    MissingStaticContent,
    #[error("audit authority rejected the intent: {0}")]
    Audit(#[from] StoreError),
    #[error("simulated tool failed: {0}")]
    ToolExecution(String),
    #[error("tool ran but outcome evidence could not be persisted: {0}")]
    ReconciliationRequired(StoreError),
}

pub trait ToolExecutor: Send + Sync {
    fn execute(&self, tool_id: &str, static_content: &str) -> Result<(), String>;
}

#[derive(Debug, Default)]
pub struct SimulatedReplyExecutor {
    calls: Mutex<Vec<String>>,
}

impl SimulatedReplyExecutor {
    pub fn calls(&self) -> Vec<String> {
        self.calls
            .lock()
            .expect("call ledger mutex poisoned")
            .clone()
    }
}

impl ToolExecutor for SimulatedReplyExecutor {
    fn execute(&self, tool_id: &str, static_content: &str) -> Result<(), String> {
        if tool_id != "discord.reply" {
            return Err("unregistered_tool".to_owned());
        }
        if static_content != "TOP SHOOTER ONLINE." {
            return Err("non_static_or_unapproved_content".to_owned());
        }
        self.calls
            .lock()
            .map_err(|_| "call_ledger_unavailable".to_owned())?
            .push(static_content.to_owned());
        Ok(())
    }
}

pub async fn process_event<E: ToolExecutor + 'static>(
    raw: RawDiscordMessageEvent,
    ids: PipelineIds,
    received_at: DateTime<Utc>,
    control: &ControlPlane,
    store: &PostgresAuditStore,
    executor: Arc<E>,
) -> Result<PipelineResult, PipelineError> {
    let event = normalize_message_event(raw, ids.event_id, ids.correlation_id, received_at)?;
    let decision = control.route(&event)?;
    let authorization = control.authorize(
        &decision,
        GuardContext {
            compiled_tools: COMPILED_PHASE_1_TOOLS,
            approval_present: false,
        },
    );

    let (allowed, reason_code) = match &authorization {
        Authorization::Allowed => (true, "phase1_static_reply_allowed".to_owned()),
        Authorization::NoAction if decision.security_signal() => {
            (false, "security_signal_ignored".to_owned())
        }
        Authorization::NoAction if decision.actor_is_bot() => {
            (false, "bot_message_ignored".to_owned())
        }
        Authorization::NoAction => (false, "route_ignored".to_owned()),
        Authorization::Denied(reason) => (false, reason.clone()),
    };

    let tool_id = allowed
        .then(|| decision.tool_id().map(str::to_owned))
        .flatten();
    let tool_call_id = allowed.then_some(ids.tool_call_id);
    let idempotency_key = allowed.then(|| {
        format!(
            "discord:{}:{}:{}",
            event.context.guild_id,
            event.event_type.as_str(),
            event.source_event_id
        )
    });

    let intent = AuditIntent {
        event_id: event.event_id,
        correlation_id: event.correlation_id,
        tool_call_id,
        source: "discord_gateway".to_owned(),
        source_event_id: event.source_event_id.clone(),
        event_type: event.event_type.as_str().to_owned(),
        guild_id: postgres_id(&event.context.guild_id)?,
        channel_id: postgres_id(&event.context.channel_id)?,
        actor_id: postgres_id(&event.actor.id)?,
        occurred_at: event.occurred_at,
        content_sha256: event.payload.content_sha256.clone(),
        route_id: decision.route_id().to_owned(),
        policy_version: decision.policy_version().to_owned(),
        policy_digest: decision.policy_digest().to_owned(),
        autonomy: decision.autonomy().as_str().to_owned(),
        risk: decision.risk().as_str().to_owned(),
        outcome: decision.outcome().as_str().to_owned(),
        allowed,
        reason_code,
        tool_id: tool_id.clone(),
        idempotency_key,
    };

    match store.record_intent(&intent).await? {
        IntentDisposition::Replay { correlation_id, .. } => {
            return Ok(PipelineResult::Replayed { correlation_id });
        }
        IntentDisposition::New { .. } if !allowed => return Ok(PipelineResult::IgnoredAudited),
        IntentDisposition::New { .. } => {}
    }

    let tool_id = tool_id
        .as_deref()
        .ok_or(PipelineError::MissingStaticContent)?;
    let static_content = control
        .static_tool_content(tool_id)
        .ok_or(PipelineError::MissingStaticContent)?;

    if let Err(error_code) = executor.execute(tool_id, static_content) {
        if let Err(audit_error) = store
            .record_tool_outcome(
                ids.tool_call_id,
                ToolOutcome::SimulatedFailure,
                Some(&error_code),
            )
            .await
        {
            return Err(PipelineError::ReconciliationRequired(audit_error));
        }
        return Err(PipelineError::ToolExecution(error_code));
    }

    store
        .record_tool_outcome(ids.tool_call_id, ToolOutcome::SimulatedSuccess, None)
        .await
        .map_err(PipelineError::ReconciliationRequired)?;
    Ok(PipelineResult::SimulatedSuccess)
}

fn postgres_id(id: &DiscordId) -> Result<i64, PipelineError> {
    id.as_str()
        .parse::<i64>()
        .map_err(|_| PipelineError::DiscordIdOutOfRange)
}
