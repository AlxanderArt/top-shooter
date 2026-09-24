use clap::{Parser, Subcommand};
use serde_json::json;
use std::{error::Error, fs, path::PathBuf, sync::Arc};
use top_shooter_contracts::RawDiscordMessageEvent;
use top_shooter_control::ControlPlane;
use top_shooter_runtime::{PipelineIds, PipelineResult, SimulatedReplyExecutor, process_event};
use top_shooter_store::PostgresAuditStore;
use url::Url;
use uuid::Uuid;

#[derive(Debug, Parser)]
#[command(name = "top-shooter-runtime")]
#[command(about = "Offline-first Top Shooter orchestration foundation")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Apply the explicit orchestration migration stream.
    Migrate {
        #[arg(long, default_value = "TEST_DATABASE_URL")]
        database_url_env: String,
    },
    /// Process one fixture with the simulated reply executor. Never connects to Discord.
    OfflineRun {
        #[arg(long, default_value = "TEST_DATABASE_URL")]
        database_url_env: String,
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        event: PathBuf,
    },
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    match Cli::parse().command {
        Command::Migrate { database_url_env } => migrate(&database_url_env).await,
        Command::OfflineRun {
            database_url_env,
            config,
            event,
        } => offline_run(&database_url_env, config, event).await,
    }
}

async fn migrate(database_url_env: &str) -> Result<(), Box<dyn Error>> {
    let database_url = local_test_database_url(database_url_env)?;
    let store = PostgresAuditStore::connect(&database_url).await?;
    store.migrate().await?;
    store.close().await;
    println!("{}", json!({"migration": "applied", "mode": "explicit"}));
    Ok(())
}

async fn offline_run(
    database_url_env: &str,
    config_path: PathBuf,
    event_path: PathBuf,
) -> Result<(), Box<dyn Error>> {
    let database_url = local_test_database_url(database_url_env)?;
    let control = ControlPlane::from_yaml(&fs::read_to_string(config_path)?)?;
    let raw: RawDiscordMessageEvent = serde_json::from_str(&fs::read_to_string(event_path)?)?;
    let ids = PipelineIds {
        event_id: Uuid::now_v7(),
        correlation_id: Uuid::now_v7(),
        tool_call_id: Uuid::now_v7(),
    };
    let store = PostgresAuditStore::connect(&database_url).await?;
    let executor = Arc::new(SimulatedReplyExecutor::default());
    let result = process_event(
        raw,
        ids,
        chrono::Utc::now(),
        &control,
        &store,
        executor.clone(),
    )
    .await?;
    let (result_name, evidence_correlation_id) = match result {
        PipelineResult::SimulatedSuccess => ("simulated_success", ids.correlation_id),
        PipelineResult::IgnoredAudited => ("ignored_audited", ids.correlation_id),
        PipelineResult::Replayed { correlation_id } => ("replayed", correlation_id),
    };
    let evidence = store.read_evidence(evidence_correlation_id).await?;
    println!(
        "{}",
        json!({
            "mode": "offline_simulation",
            "result": result_name,
            "correlation_id": evidence_correlation_id,
            "executor_calls": executor.calls().len(),
            "evidence": {
                "events": evidence.events,
                "decisions": evidence.decisions,
                "tool_calls": evidence.tool_calls,
                "audit_events": evidence.audit_events,
                "raw_content_columns": evidence.raw_content_rows
            }
        })
    );
    store.close().await;
    Ok(())
}

fn required_environment(name: &str) -> Result<String, Box<dyn Error>> {
    if name.is_empty()
        || !name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    {
        return Err("database environment variable name is invalid".into());
    }
    std::env::var(name)
        .map_err(|_| format!("required environment variable {name} is not set").into())
}

fn local_test_database_url(name: &str) -> Result<String, Box<dyn Error>> {
    if std::env::var("TOP_SHOOTER_OFFLINE_MODE").as_deref() != Ok("local_test") {
        return Err("TOP_SHOOTER_OFFLINE_MODE=local_test is required".into());
    }
    let database_url = required_environment(name)?;
    let parsed = Url::parse(&database_url).map_err(|_| "database URL is invalid")?;
    if !matches!(parsed.scheme(), "postgres" | "postgresql") {
        return Err("local-test database URL must use PostgreSQL".into());
    }
    if !matches!(parsed.host_str(), Some("127.0.0.1" | "localhost" | "::1")) {
        return Err("local-test database host must be loopback".into());
    }
    let database_name = parsed.path().trim_start_matches('/');
    if !database_name.starts_with("top_shooter_test_") && !database_name.starts_with("_sqlx_test_")
    {
        return Err(
            "local-test database name must start with top_shooter_test_ or _sqlx_test_".into(),
        );
    }
    Ok(database_url)
}
