# Top Shooter Orchestration Foundation

## Status

This repository now contains an **additive, offline-first Rust orchestration foundation** beside the existing Python Discord bot. It does not replace the Python gateway, connect to Discord, call the legacy `/action` dispatcher, activate moderation, or deploy infrastructure.

## Implemented vertical slice

```text
synthetic Discord message fixture
→ strict Rust contract normalization
→ validated YAML routing and policy
→ compiled capability + permission guard
→ PostgreSQL append-only intent/audit evidence
→ typed simulated discord.reply executor
→ immutable PostgreSQL outcome evidence
```

The only executable capability is `discord.reply`, and its only allowed output is the bounded static string `TOP SHOOTER ONLINE.` User content is never interpolated into tool arguments.

## Security boundary

- Discord event content is always classified as untrusted.
- Discord IDs must be canonical positive decimal strings within signed PostgreSQL `BIGINT` range; both serde ingress and PostgreSQL enforce the same boundary.
- YAML rejects unknown fields, duplicate keys, unknown tools, unsupported versions, excessive cardinality, invalid route/tool references, and the reserved `&`, `*`, and `!` characters used by aliases/tags. Multiple documents and directives are also rejected.
- YAML can select only capabilities already compiled into the Rust registry.
- Explicit suspicious-instruction markers route to an audited ignore decision before safe reply routing. This deterministic marker set is a bounded phase-one control, not a general prompt-injection classifier.
- An audit intent must commit before the simulated executor can run.
- Duplicate source events replay the existing receipt and do not execute again.
- A duplicate source ID with changed semantics fails with `TS001 idempotency_conflict`.
- All four orchestration evidence tables reject update, delete, and truncate operations through owner-side triggers. A fully privileged PostgreSQL administrator can still alter or remove those controls; production role separation and ACL enforcement remain deferred.
- Raw Discord message text is not persisted in orchestration tables.
- No Discord token is accepted by the Rust runtime.

## Explicitly deferred

The following remain blocked until their identity, capability, approval, hierarchy, idempotency, privacy, and reconciliation contracts are implemented and reviewed:

- live Discord ingress;
- calls to the legacy Python `/action` API;
- warnings, role changes, timeouts, kicks, bans, or any other moderation mutation;
- model/LLM execution;
- n8n activation;
- production database migration;
- dedicated migration/runtime PostgreSQL identities and production ACLs;
- Docker or VPS deployment;
- autonomous retries after an ambiguous external result.

## Local verification

The PostgreSQL tests require a disposable PostgreSQL 16 instance. SQLx creates and drops an isolated database for each database-backed test. The master `DATABASE_URL` must use a disposable local service.

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
python3 -m unittest tests/test_repository_guard.py
python3 tools/verify_orchestration_foundation.py
cargo test --workspace --locked -- --test-threads=1
```

Explicit migration and offline fixture execution:

```bash
export TOP_SHOOTER_OFFLINE_MODE=local_test
export DATABASE_URL='postgresql://postgres@127.0.0.1:<disposable-port>/top_shooter_test_master?sslmode=disable'
export TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:<disposable-port>/top_shooter_test_manual?sslmode=disable'
cargo run --locked -p top-shooter-runtime -- migrate \
  --database-url-env TEST_DATABASE_URL
cargo run --locked -p top-shooter-runtime -- offline-run \
  --database-url-env TEST_DATABASE_URL \
  --config orchestration/config/phase1.yaml \
  --event orchestration/tests/fixtures/cli_message_mention.json
```

The CLI emits one JSON receipt. It refuses non-loopback hosts, requires the explicit `local_test` mode, and accepts only database names beginning with `top_shooter_test_` or SQLx's `_sqlx_test_`. It performs no Discord or n8n network calls.

## Repository compatibility

`orchestration/protected-files.json` pins the exact baseline commit and legacy runtime bytes, including `api.py`, `bot.py`, key cogs, the existing schema, Docker files, and Python requirements. On pull requests, CI also binds that manifest to GitHub's externally supplied base SHA, so editing a protected file and its manifest together cannot self-authorize the change.
