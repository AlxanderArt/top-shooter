CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS orchestration;
CREATE SCHEMA IF NOT EXISTS orchestration_api;

CREATE TABLE orchestration.events (
    event_id UUID PRIMARY KEY,
    correlation_id UUID NOT NULL,
    producer_id TEXT NOT NULL DEFAULT session_user,
    source TEXT NOT NULL CHECK (source = 'discord_gateway'),
    source_event_id TEXT NOT NULL CHECK (
        source_event_id ~ '^[1-9][0-9]{0,18}$'
        AND source_event_id::NUMERIC <= 9223372036854775807
    ),
    event_type TEXT NOT NULL CHECK (event_type = 'message.created'),
    guild_id BIGINT NOT NULL CHECK (guild_id > 0),
    channel_id BIGINT NOT NULL CHECK (channel_id > 0),
    actor_id BIGINT NOT NULL CHECK (actor_id > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    content_sha256 CHAR(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    UNIQUE (source, event_type, source_event_id)
);

CREATE TABLE orchestration.decisions (
    decision_id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE REFERENCES orchestration.events(event_id),
    route_id TEXT NOT NULL CHECK (length(route_id) BETWEEN 1 AND 64),
    policy_version TEXT NOT NULL CHECK (length(policy_version) BETWEEN 1 AND 64),
    policy_digest CHAR(64) NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
    autonomy TEXT NOT NULL CHECK (autonomy IN ('A0', 'A1', 'A2', 'A3', 'A4', 'A5')),
    risk TEXT NOT NULL CHECK (risk IN ('R0', 'R1', 'R2', 'R3', 'R4', 'R5')),
    outcome TEXT NOT NULL CHECK (outcome IN ('ignore', 'execute_tool', 'request_human_review')),
    allowed BOOLEAN NOT NULL,
    reason_code TEXT NOT NULL CHECK (length(reason_code) BETWEEN 1 AND 64),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE orchestration.tool_calls (
    tool_call_id UUID PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE REFERENCES orchestration.events(event_id),
    decision_id UUID NOT NULL UNIQUE REFERENCES orchestration.decisions(decision_id),
    tool_id TEXT NOT NULL CHECK (tool_id = 'discord.reply'),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 1 AND 160),
    request_digest CHAR(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE orchestration.audit_events (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES orchestration.events(event_id),
    correlation_id UUID NOT NULL,
    tool_call_id UUID REFERENCES orchestration.tool_calls(tool_call_id),
    event_kind TEXT NOT NULL CHECK (
        event_kind IN ('intent_recorded', 'simulated_success', 'simulated_failure')
    ),
    error_code TEXT CHECK (error_code IS NULL OR length(error_code) BETWEEN 1 AND 64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (
        jsonb_typeof(metadata) = 'object' AND octet_length(metadata::text) <= 4096
    ),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE UNIQUE INDEX audit_tool_outcome_once
ON orchestration.audit_events(tool_call_id)
WHERE event_kind IN ('simulated_success', 'simulated_failure');

CREATE OR REPLACE FUNCTION orchestration.reject_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'TS002 append_only_violation';
END;
$$;

CREATE TRIGGER events_no_update_or_delete
BEFORE UPDATE OR DELETE ON orchestration.events
FOR EACH ROW EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER events_no_truncate
BEFORE TRUNCATE ON orchestration.events
FOR EACH STATEMENT EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER decisions_no_update_or_delete
BEFORE UPDATE OR DELETE ON orchestration.decisions
FOR EACH ROW EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER decisions_no_truncate
BEFORE TRUNCATE ON orchestration.decisions
FOR EACH STATEMENT EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER tool_calls_no_update_or_delete
BEFORE UPDATE OR DELETE ON orchestration.tool_calls
FOR EACH ROW EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER tool_calls_no_truncate
BEFORE TRUNCATE ON orchestration.tool_calls
FOR EACH STATEMENT EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER audit_events_no_update_or_delete
BEFORE UPDATE OR DELETE ON orchestration.audit_events
FOR EACH ROW EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE TRIGGER audit_events_no_truncate
BEFORE TRUNCATE ON orchestration.audit_events
FOR EACH STATEMENT EXECUTE FUNCTION orchestration.reject_evidence_mutation();

CREATE OR REPLACE FUNCTION orchestration_api.record_intent(
    p_event_id UUID,
    p_correlation_id UUID,
    p_tool_call_id UUID,
    p_source TEXT,
    p_source_event_id TEXT,
    p_event_type TEXT,
    p_guild_id BIGINT,
    p_channel_id BIGINT,
    p_actor_id BIGINT,
    p_occurred_at TIMESTAMPTZ,
    p_content_sha256 TEXT,
    p_route_id TEXT,
    p_policy_version TEXT,
    p_policy_digest TEXT,
    p_autonomy TEXT,
    p_risk TEXT,
    p_outcome TEXT,
    p_allowed BOOLEAN,
    p_reason_code TEXT,
    p_tool_id TEXT,
    p_idempotency_key TEXT
)
RETURNS TABLE(event_id UUID, correlation_id UUID, tool_call_id UUID, replayed BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, orchestration
AS $$
DECLARE
    v_event orchestration.events%ROWTYPE;
    v_decision orchestration.decisions%ROWTYPE;
    v_tool orchestration.tool_calls%ROWTYPE;
    v_decision_id UUID := gen_random_uuid();
    v_request_digest TEXT;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_source || ':' || p_event_type || ':' || p_source_event_id, 0));
    IF p_allowed THEN
        IF p_outcome <> 'execute_tool' OR p_tool_call_id IS NULL OR p_tool_id IS NULL OR p_idempotency_key IS NULL THEN
            RAISE EXCEPTION 'TS004 invalid_executable_intent';
        END IF;
        v_request_digest := encode(public.digest(p_tool_id || ':' || p_idempotency_key, 'sha256'), 'hex');
    ELSIF p_tool_call_id IS NOT NULL OR p_tool_id IS NOT NULL OR p_idempotency_key IS NOT NULL THEN
        RAISE EXCEPTION 'TS005 invalid_non_executable_intent';
    END IF;

    SELECT * INTO v_event
    FROM orchestration.events existing
    WHERE existing.source = p_source
      AND existing.event_type = p_event_type
      AND existing.source_event_id = p_source_event_id;

    IF FOUND THEN
        SELECT * INTO STRICT v_decision
        FROM orchestration.decisions existing
        WHERE existing.event_id = v_event.event_id;
        SELECT * INTO v_tool
        FROM orchestration.tool_calls existing
        WHERE existing.event_id = v_event.event_id;

        IF v_event.guild_id = p_guild_id
           AND v_event.channel_id = p_channel_id
           AND v_event.actor_id = p_actor_id
           AND v_event.occurred_at = p_occurred_at
           AND v_event.content_sha256 = p_content_sha256
           AND v_decision.route_id = p_route_id
           AND v_decision.policy_version = p_policy_version
           AND v_decision.policy_digest = p_policy_digest
           AND v_decision.autonomy = p_autonomy
           AND v_decision.risk = p_risk
           AND v_decision.outcome = p_outcome
           AND v_decision.allowed = p_allowed
           AND v_decision.reason_code = p_reason_code
           AND (
               (p_tool_id IS NULL AND v_tool.tool_call_id IS NULL)
               OR (v_tool.tool_id = p_tool_id AND v_tool.idempotency_key = p_idempotency_key)
           )
        THEN
            RETURN QUERY
            SELECT v_event.event_id, v_event.correlation_id, v_tool.tool_call_id, TRUE;
            RETURN;
        END IF;
        RAISE EXCEPTION 'TS001 idempotency_conflict' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO orchestration.events (
        event_id, correlation_id, source, source_event_id, event_type,
        guild_id, channel_id, actor_id, occurred_at, content_sha256
    ) VALUES (
        p_event_id, p_correlation_id, p_source, p_source_event_id, p_event_type,
        p_guild_id, p_channel_id, p_actor_id, p_occurred_at, p_content_sha256
    );

    INSERT INTO orchestration.decisions (
        decision_id, event_id, route_id, policy_version, policy_digest,
        autonomy, risk, outcome, allowed, reason_code
    ) VALUES (
        v_decision_id, p_event_id, p_route_id, p_policy_version, p_policy_digest,
        p_autonomy, p_risk, p_outcome, p_allowed, p_reason_code
    );

    IF p_tool_id IS NOT NULL THEN
        INSERT INTO orchestration.tool_calls (
            tool_call_id, event_id, decision_id, tool_id, idempotency_key, request_digest
        ) VALUES (
            p_tool_call_id, p_event_id, v_decision_id, p_tool_id, p_idempotency_key, v_request_digest
        );
    END IF;

    INSERT INTO orchestration.audit_events (
        event_id, correlation_id, tool_call_id, event_kind, metadata
    ) VALUES (
        p_event_id, p_correlation_id, p_tool_call_id, 'intent_recorded',
        jsonb_build_object('policy_digest', p_policy_digest, 'content_sha256', p_content_sha256)
    );

    RETURN QUERY SELECT p_event_id, p_correlation_id, p_tool_call_id, FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION orchestration_api.record_tool_outcome(
    p_tool_call_id UUID,
    p_event_kind TEXT,
    p_error_code TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, orchestration
AS $$
DECLARE
    v_event_id UUID;
    v_correlation_id UUID;
BEGIN
    IF p_event_kind NOT IN ('simulated_success', 'simulated_failure') THEN
        RAISE EXCEPTION 'TS003 invalid_tool_outcome';
    END IF;
    SELECT tool.event_id, event.correlation_id
      INTO STRICT v_event_id, v_correlation_id
    FROM orchestration.tool_calls tool
    JOIN orchestration.events event ON event.event_id = tool.event_id
    WHERE tool.tool_call_id = p_tool_call_id;

    INSERT INTO orchestration.audit_events (
        event_id, correlation_id, tool_call_id, event_kind, error_code
    ) VALUES (
        v_event_id, v_correlation_id, p_tool_call_id, p_event_kind, p_error_code
    );
END;
$$;

REVOKE ALL ON SCHEMA orchestration FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA orchestration FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA orchestration_api FROM PUBLIC;
