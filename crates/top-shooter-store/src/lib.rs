use chrono::{DateTime, Utc};
use sqlx::{PgPool, postgres::PgPoolOptions};
use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct AuditIntent {
    pub event_id: Uuid,
    pub correlation_id: Uuid,
    pub tool_call_id: Option<Uuid>,
    pub source: String,
    pub source_event_id: String,
    pub event_type: String,
    pub guild_id: i64,
    pub channel_id: i64,
    pub actor_id: i64,
    pub occurred_at: DateTime<Utc>,
    pub content_sha256: String,
    pub route_id: String,
    pub policy_version: String,
    pub policy_digest: String,
    pub autonomy: String,
    pub risk: String,
    pub outcome: String,
    pub allowed: bool,
    pub reason_code: String,
    pub tool_id: Option<String>,
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IntentDisposition {
    New {
        event_id: Uuid,
        tool_call_id: Option<Uuid>,
    },
    Replay {
        event_id: Uuid,
        correlation_id: Uuid,
        tool_call_id: Option<Uuid>,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToolOutcome {
    SimulatedSuccess,
    SimulatedFailure,
}

impl ToolOutcome {
    fn as_database_value(self) -> &'static str {
        match self {
            Self::SimulatedSuccess => "simulated_success",
            Self::SimulatedFailure => "simulated_failure",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EvidenceCounts {
    pub events: i64,
    pub decisions: i64,
    pub tool_calls: i64,
    pub audit_events: i64,
    pub raw_content_rows: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AppendOnlyGuards {
    pub events: bool,
    pub decisions: bool,
    pub tool_calls: bool,
    pub audit_events: bool,
}

#[derive(Debug, Error)]
pub enum StoreError {
    #[error("idempotency key was replayed with different semantics")]
    IdempotencyConflict,
    #[error("audit database error: {0}")]
    Database(#[source] sqlx::Error),
}

impl PartialEq for StoreError {
    fn eq(&self, other: &Self) -> bool {
        matches!(
            (self, other),
            (Self::IdempotencyConflict, Self::IdempotencyConflict)
        )
    }
}

pub struct PostgresAuditStore {
    pool: PgPool,
}

impl PostgresAuditStore {
    pub fn from_pool(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn connect(url: &str) -> Result<Self, StoreError> {
        let pool = PgPoolOptions::new()
            .max_connections(5)
            .acquire_timeout(std::time::Duration::from_secs(5))
            .connect(url)
            .await
            .map_err(StoreError::Database)?;
        Ok(Self { pool })
    }

    pub async fn migrate(&self) -> Result<(), StoreError> {
        sqlx::migrate!("./migrations")
            .run(&self.pool)
            .await
            .map_err(|error| StoreError::Database(sqlx::Error::Migrate(Box::new(error))))
    }

    pub async fn record_intent(
        &self,
        intent: &AuditIntent,
    ) -> Result<IntentDisposition, StoreError> {
        let result = sqlx::query_as::<_, (Uuid, Uuid, Option<Uuid>, bool)>(
            r#"
            SELECT event_id, correlation_id, tool_call_id, replayed
            FROM orchestration_api.record_intent(
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
            )
            "#,
        )
        .bind(intent.event_id)
        .bind(intent.correlation_id)
        .bind(intent.tool_call_id)
        .bind(&intent.source)
        .bind(&intent.source_event_id)
        .bind(&intent.event_type)
        .bind(intent.guild_id)
        .bind(intent.channel_id)
        .bind(intent.actor_id)
        .bind(intent.occurred_at)
        .bind(&intent.content_sha256)
        .bind(&intent.route_id)
        .bind(&intent.policy_version)
        .bind(&intent.policy_digest)
        .bind(&intent.autonomy)
        .bind(&intent.risk)
        .bind(&intent.outcome)
        .bind(intent.allowed)
        .bind(&intent.reason_code)
        .bind(&intent.tool_id)
        .bind(&intent.idempotency_key)
        .fetch_one(&self.pool)
        .await;

        match result {
            Ok((event_id, _correlation_id, tool_call_id, false)) => Ok(IntentDisposition::New {
                event_id,
                tool_call_id,
            }),
            Ok((event_id, correlation_id, tool_call_id, true)) => Ok(IntentDisposition::Replay {
                event_id,
                correlation_id,
                tool_call_id,
            }),
            Err(error) if is_idempotency_conflict(&error) => Err(StoreError::IdempotencyConflict),
            Err(error) => Err(StoreError::Database(error)),
        }
    }

    pub async fn record_tool_outcome(
        &self,
        tool_call_id: Uuid,
        outcome: ToolOutcome,
        error_code: Option<&str>,
    ) -> Result<(), StoreError> {
        sqlx::query("SELECT orchestration_api.record_tool_outcome($1, $2, $3)")
            .bind(tool_call_id)
            .bind(outcome.as_database_value())
            .bind(error_code)
            .execute(&self.pool)
            .await
            .map_err(StoreError::Database)?;
        Ok(())
    }

    pub async fn read_evidence(&self, correlation_id: Uuid) -> Result<EvidenceCounts, StoreError> {
        let (events, decisions, tool_calls, audit_events) =
            sqlx::query_as::<_, (i64, i64, i64, i64)>(
                r#"
                SELECT
                    (SELECT count(*) FROM orchestration.events WHERE correlation_id = $1),
                    (SELECT count(*) FROM orchestration.decisions d JOIN orchestration.events e USING (event_id) WHERE e.correlation_id = $1),
                    (SELECT count(*) FROM orchestration.tool_calls t JOIN orchestration.events e USING (event_id) WHERE e.correlation_id = $1),
                    (SELECT count(*) FROM orchestration.audit_events WHERE correlation_id = $1)
                "#,
            )
            .bind(correlation_id)
            .fetch_one(&self.pool)
            .await
            .map_err(StoreError::Database)?;

        let (raw_content_rows,) = sqlx::query_as::<_, (i64,)>(
            r#"
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'orchestration'
              AND column_name IN ('content', 'raw_content', 'message_content', 'payload')
            "#,
        )
        .fetch_one(&self.pool)
        .await
        .map_err(StoreError::Database)?;

        Ok(EvidenceCounts {
            events,
            decisions,
            tool_calls,
            audit_events,
            raw_content_rows,
        })
    }

    pub async fn prove_append_only_guards(&self) -> Result<AppendOnlyGuards, StoreError> {
        let events = mutations_rejected(
            &self.pool,
            &[
                "UPDATE orchestration.events SET content_sha256 = content_sha256",
                "DELETE FROM orchestration.events",
                "TRUNCATE orchestration.events CASCADE",
            ],
        )
        .await;
        let decisions = mutations_rejected(
            &self.pool,
            &[
                "UPDATE orchestration.decisions SET route_id = route_id",
                "DELETE FROM orchestration.decisions",
                "TRUNCATE orchestration.decisions CASCADE",
            ],
        )
        .await;
        let tool_calls = mutations_rejected(
            &self.pool,
            &[
                "UPDATE orchestration.tool_calls SET tool_id = tool_id",
                "DELETE FROM orchestration.tool_calls",
                "TRUNCATE orchestration.tool_calls CASCADE",
            ],
        )
        .await;
        let audit_events = mutations_rejected(
            &self.pool,
            &[
                "UPDATE orchestration.audit_events SET metadata = metadata",
                "DELETE FROM orchestration.audit_events",
                "TRUNCATE orchestration.audit_events",
            ],
        )
        .await;
        Ok(AppendOnlyGuards {
            events,
            decisions,
            tool_calls,
            audit_events,
        })
    }

    pub async fn close(self) {
        self.pool.close().await;
    }
}

async fn mutations_rejected(pool: &PgPool, statements: &[&str]) -> bool {
    for statement in statements {
        if sqlx::query(statement).execute(pool).await.is_ok() {
            return false;
        }
    }
    true
}

fn is_idempotency_conflict(error: &sqlx::Error) -> bool {
    error
        .as_database_error()
        .is_some_and(|database_error| database_error.message().contains("TS001"))
}
