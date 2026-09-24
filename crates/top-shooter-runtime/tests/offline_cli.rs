use serde_json::Value;
use sqlx::{ConnectOptions, PgPool};
use std::process::Command;

#[sqlx::test]
async fn offline_cli_migrates_runs_and_emits_evidence_json(pool: PgPool) {
    let database_url = pool.connect_options().to_url_lossy().to_string();
    let binary = env!("CARGO_BIN_EXE_top-shooter-runtime");

    let migration = Command::new(binary)
        .args(["migrate", "--database-url-env", "TEST_DATABASE_URL"])
        .env("TEST_DATABASE_URL", &database_url)
        .env("TOP_SHOOTER_OFFLINE_MODE", "local_test")
        .output()
        .unwrap();
    assert!(
        migration.status.success(),
        "{}",
        String::from_utf8_lossy(&migration.stderr)
    );

    let repo_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let config = repo_root.join("orchestration/config/phase1.yaml");
    let event = repo_root.join("orchestration/tests/fixtures/cli_message_mention.json");
    let run = Command::new(binary)
        .arg("offline-run")
        .args(["--database-url-env", "TEST_DATABASE_URL"])
        .arg("--config")
        .arg(&config)
        .arg("--event")
        .arg(&event)
        .env("TEST_DATABASE_URL", &database_url)
        .env("TOP_SHOOTER_OFFLINE_MODE", "local_test")
        .output()
        .unwrap();
    assert!(
        run.status.success(),
        "{}",
        String::from_utf8_lossy(&run.stderr)
    );

    let receipt: Value = serde_json::from_slice(&run.stdout).unwrap();
    assert_eq!(receipt["mode"], "offline_simulation");
    assert_eq!(receipt["result"], "simulated_success");
    assert_eq!(receipt["executor_calls"], 1);
    assert_eq!(receipt["evidence"]["events"], 1);
    assert_eq!(receipt["evidence"]["decisions"], 1);
    assert_eq!(receipt["evidence"]["tool_calls"], 1);
    assert_eq!(receipt["evidence"]["audit_events"], 2);

    let replay = Command::new(binary)
        .arg("offline-run")
        .args(["--database-url-env", "TEST_DATABASE_URL"])
        .arg("--config")
        .arg(config)
        .arg("--event")
        .arg(event)
        .env("TEST_DATABASE_URL", &database_url)
        .env("TOP_SHOOTER_OFFLINE_MODE", "local_test")
        .output()
        .unwrap();
    assert!(
        replay.status.success(),
        "{}",
        String::from_utf8_lossy(&replay.stderr)
    );
    let replay_receipt: Value = serde_json::from_slice(&replay.stdout).unwrap();
    assert_eq!(replay_receipt["result"], "replayed");
    assert_eq!(replay_receipt["executor_calls"], 0);
    assert_eq!(replay_receipt["evidence"], receipt["evidence"]);
}

#[test]
fn cli_rejects_database_without_explicit_local_test_mode() {
    let binary = env!("CARGO_BIN_EXE_top-shooter-runtime");
    let rejected = Command::new(binary)
        .args(["migrate", "--database-url-env", "TEST_DATABASE_URL"])
        .env(
            "TEST_DATABASE_URL",
            "postgresql://postgres@example.com/production",
        )
        .env_remove("TOP_SHOOTER_OFFLINE_MODE")
        .output()
        .unwrap();
    assert!(!rejected.status.success());
    assert!(
        String::from_utf8_lossy(&rejected.stderr).contains("TOP_SHOOTER_OFFLINE_MODE=local_test")
    );
}
