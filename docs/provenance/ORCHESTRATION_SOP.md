# Orchestration SOP Provenance

The orchestration foundation was implemented from a user-supplied planning archive that was safety-validated and extracted outside the repository.

## Source identity

- Archive filename: `Top-Shooter-PKC-Agent-Orchestration-SOP.zip`
- Archive SHA-256: `dda61586571c2ea4caad7dabc36da0663c2a70f53a064725f3a12cbff44ef1e0`
- Primary SOP entry: `top-shooter-pkc-agent-orchestration/TOP_SHOOTER_ORCHESTRATION_SOP.md`
- Primary SOP SHA-256: `d30976ee5da86a4b26bbf9fba77cefef517e38a03153c4f04c723bddab499e79`
- Archive safety result: 18 UTF-8 text/YAML entries; no encryption, path traversal, absolute paths, symlinks, nested archives, or binary executables.

## Use boundary

The archive is design authority for the Rust/YAML/PostgreSQL orchestration direction. It is not deployment authorization, credential material, or permission to execute live Discord actions. The original archive is not committed to this public repository; only non-secret provenance hashes and the independently implemented foundation are recorded here.

## Reconciliation

Concord architecture, security/identity, QA/SDET, and backend/database reviews were applied. Where the architecture review proposed calling the legacy Python `/action` endpoint, the security review controlled: the first slice uses a simulated tool and does not call the legacy dispatcher.
