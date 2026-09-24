use chrono::{DateTime, Utc};
use sqlx::PgPool;
use top_shooter_store::{
    AuditIntent, IntentDisposition, PostgresAuditStore, StoreError, ToolOutcome,
};
use uuid::Uuid;

fn intent(content_sha256: &str) -> AuditIntent {
    AuditIntent {
        event_id: Uuid::parse_str("018f0000-0000-7000-8000-000000000001").unwrap(),
        correlation_id: Uuid::parse_str("018f0000-0000-7000-8000-000000000002").unwrap(),
        tool_call_id: Some(Uuid::parse_str("018f0000-0000-7000-8000-000000000003").unwrap()),
        source: "discord_gateway".to_owned(),
        source_event_id: "100000000000000001".to_owned(),
        event_type: "message.created".to_owned(),
        guild_id: 200000000000000001,
        channel_id: 300000000000000001,
        actor_id: 400000000000000001,
        occurred_at: "2026-01-15T12:00:00Z".parse::<DateTime<Utc>>().unwrap(),
        content_sha256: content_sha256.to_owned(),
        route_id: "mention_static_reply".to_owned(),
        policy_version: "phase1-v1".to_owned(),
        policy_digest: "a".repeat(64),
        autonomy: "A2".to_owned(),
        risk: "R1".to_owned(),
        outcome: "execute_tool".to_owned(),
        allowed: true,
        reason_code: "phase1_static_reply_allowed".to_owned(),
        tool_id: Some("discord.reply".to_owned()),
        idempotency_key: Some("discord:message.created:100000000000000001".to_owned()),
    }
}

#[sqlx::test]
async fn postgres_audit_is_idempotent_conflict_aware_and_append_only(pool: PgPool) {
    let store = PostgresAuditStore::from_pool(pool);
    store.migrate().await.unwrap();

    let expected_event = Uuid::parse_str("018f0000-0000-7000-8000-000000000001").unwrap();
    let expected_tool_id = Uuid::parse_str("018f0000-0000-7000-8000-000000000003").unwrap();
    let expected_tool = Some(expected_tool_id);
    let first = store.record_intent(&intent(&"1".repeat(64))).await.unwrap();
    assert_eq!(
        first,
        IntentDisposition::New {
            event_id: expected_event,
            tool_call_id: expected_tool,
        }
    );

    let mut replayed_intent = intent(&"1".repeat(64));
    replayed_intent.event_id = Uuid::parse_str("018f0000-0000-7000-8000-000000000011").unwrap();
    replayed_intent.correlation_id =
        Uuid::parse_str("018f0000-0000-7000-8000-000000000012").unwrap();
    replayed_intent.tool_call_id =
        Some(Uuid::parse_str("018f0000-0000-7000-8000-000000000013").unwrap());
    let replay = store.record_intent(&replayed_intent).await.unwrap();
    assert_eq!(
        replay,
        IntentDisposition::Replay {
            event_id: expected_event,
            correlation_id: Uuid::parse_str("018f0000-0000-7000-8000-000000000002").unwrap(),
            tool_call_id: expected_tool,
        }
    );

    let conflict = store.record_intent(&intent(&"2".repeat(64))).await;
    assert!(matches!(conflict, Err(StoreError::IdempotencyConflict)));

    store
        .record_tool_outcome(expected_tool_id, ToolOutcome::SimulatedSuccess, None)
        .await
        .unwrap();

    let evidence = store
        .read_evidence(Uuid::parse_str("018f0000-0000-7000-8000-000000000002").unwrap())
        .await
        .unwrap();
    assert_eq!(evidence.events, 1);
    assert_eq!(evidence.decisions, 1);
    assert_eq!(evidence.tool_calls, 1);
    assert_eq!(evidence.audit_events, 2);
    assert_eq!(evidence.raw_content_rows, 0);

    let guards = store.prove_append_only_guards().await.unwrap();
    assert!(guards.events);
    assert!(guards.decisions);
    assert!(guards.tool_calls);
    assert!(guards.audit_events);
    store.close().await;
}

#[sqlx::test]
async fn concurrent_duplicate_source_event_records_once(pool: PgPool) {
    let store = PostgresAuditStore::from_pool(pool);
    store.migrate().await.unwrap();
    let first = intent(&"3".repeat(64));
    let mut second = first.clone();
    second.event_id = Uuid::parse_str("018f0000-0000-7000-8000-000000000021").unwrap();
    second.correlation_id = Uuid::parse_str("018f0000-0000-7000-8000-000000000022").unwrap();
    second.tool_call_id = Some(Uuid::parse_str("018f0000-0000-7000-8000-000000000023").unwrap());

    let (left, right) = tokio::join!(store.record_intent(&first), store.record_intent(&second));
    let outcomes = [left.unwrap(), right.unwrap()];
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| matches!(outcome, IntentDisposition::New { .. }))
            .count(),
        1
    );
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| matches!(outcome, IntentDisposition::Replay { .. }))
            .count(),
        1
    );

    let first_counts = store.read_evidence(first.correlation_id).await.unwrap();
    let second_counts = store.read_evidence(second.correlation_id).await.unwrap();
    assert_eq!(first_counts.events + second_counts.events, 1);
    assert_eq!(first_counts.tool_calls + second_counts.tool_calls, 1);
    store.close().await;
}

#[sqlx::test]
async fn postgres_rejects_noncanonical_source_event_ids(pool: PgPool) {
    let store = PostgresAuditStore::from_pool(pool);
    store.migrate().await.unwrap();

    for source_event_id in ["0001", "0", "9223372036854775808"] {
        let mut invalid = intent(&"4".repeat(64));
        invalid.source_event_id = source_event_id.to_owned();
        invalid.idempotency_key = Some(format!("discord:message.created:{source_event_id}"));
        assert!(
            matches!(
                store.record_intent(&invalid).await,
                Err(StoreError::Database(_))
            ),
            "database accepted noncanonical source_event_id={source_event_id}"
        );
    }
    store.close().await;
}
