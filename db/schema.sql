-- PROJECTKIDCREATIONS / Top Shooter — Postgres schema (v2)
--
-- Owned by db/__init__.py — runs idempotently on bot startup.
-- All datetimes are unix-epoch seconds (BIGINT) for cheap comparison and indexing.
-- Discord IDs are 64-bit snowflakes → BIGINT.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT INTO schema_version (version) VALUES (2)
ON CONFLICT (version) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Per-guild configuration. One row per guild.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id                BIGINT PRIMARY KEY,
    log_channel_id          BIGINT,
    welcome_channel_id      BIGINT,
    welcome_message         TEXT,
    leave_channel_id        BIGINT,
    leave_message           TEXT,
    autorole_id             BIGINT,
    levels_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    levels_announce_channel BIGINT,
    automod_enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    raid_mode               BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- Warns.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS warns (
    id              BIGSERIAL PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    moderator_id    BIGINT NOT NULL,
    reason          TEXT NOT NULL,
    created_at      BIGINT NOT NULL,
    cleared_at      BIGINT,
    cleared_by      BIGINT
);

CREATE INDEX IF NOT EXISTS idx_warns_guild_user_active ON warns(guild_id, user_id) WHERE cleared_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_warns_guild_user_all ON warns(guild_id, user_id);

-- ---------------------------------------------------------------------------
-- XP / Levels.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS levels (
    guild_id            BIGINT NOT NULL,
    user_id             BIGINT NOT NULL,
    xp                  BIGINT NOT NULL DEFAULT 0,
    level               INTEGER NOT NULL DEFAULT 0,
    last_message_at     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_levels_leaderboard ON levels(guild_id, xp DESC);

-- ---------------------------------------------------------------------------
-- Level → Role mapping.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS level_roles (
    guild_id    BIGINT NOT NULL,
    level       INTEGER NOT NULL,
    role_id     BIGINT NOT NULL,
    PRIMARY KEY (guild_id, level)
);

CREATE INDEX IF NOT EXISTS idx_level_roles_role ON level_roles(role_id);

-- ---------------------------------------------------------------------------
-- Reaction roles.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id    BIGINT NOT NULL,
    message_id  BIGINT NOT NULL,
    emoji       TEXT NOT NULL,
    role_id     BIGINT NOT NULL,
    PRIMARY KEY (guild_id, message_id, emoji)
);

CREATE INDEX IF NOT EXISTS idx_reaction_roles_message ON reaction_roles(message_id);

-- ---------------------------------------------------------------------------
-- AutoMod rules.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS automod_rules (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    pattern     TEXT NOT NULL,
    action      TEXT NOT NULL,
    created_at  BIGINT NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_automod_guild_enabled ON automod_rules(guild_id, enabled);

-- ---------------------------------------------------------------------------
-- Temp voice system.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS temp_voice_config (
    guild_id            BIGINT PRIMARY KEY,
    category_id         BIGINT NOT NULL,
    trigger_channel_id  BIGINT NOT NULL,
    name_template       TEXT NOT NULL DEFAULT '{user}''s VC'
);

CREATE TABLE IF NOT EXISTS temp_voice_active (
    channel_id  BIGINT PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    owner_id    BIGINT NOT NULL,
    created_at  BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_temp_voice_guild ON temp_voice_active(guild_id);

-- ---------------------------------------------------------------------------
-- Anti-raid rolling join tracking.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recent_joins (
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    joined_at   BIGINT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_recent_joins_time ON recent_joins(guild_id, joined_at);
