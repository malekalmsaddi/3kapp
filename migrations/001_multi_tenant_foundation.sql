-- =============================================================================
-- Migration 001: Multi-Tenant Foundation
-- =============================================================================
-- Safe to run against the existing production database.
-- All operations use IF NOT EXISTS / IF EXISTS / ON CONFLICT guards.
-- The existing single tenant's data is preserved under a default tenant record.
--
-- Run order:
--   1. New platform tables (plans, tenants, users, configs, etc.)
--   2. Insert default plan + default tenant + seed configs
--   3. Add tenant_id to existing tables (nullable → backfill → NOT NULL)
--   4. Change user_threads PK to composite (tenant_id, user_id)
--   5. Migrate admins → users
--   6. Create remaining supporting tables
-- =============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. PLANS
-- =============================================================================
CREATE TABLE IF NOT EXISTS plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(50) NOT NULL UNIQUE,
    display_name    VARCHAR(100) NOT NULL,
    price_monthly   NUMERIC(10,2) NOT NULL DEFAULT 0,
    price_yearly    NUMERIC(10,2) NOT NULL DEFAULT 0,
    entitlements    JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_plans_name ON plans(name);

-- Seed plans (idempotent)
INSERT INTO plans (name, display_name, price_monthly, price_yearly, entitlements, sort_order)
VALUES
    ('free', 'Free', 0, 0,
     '{"max_admins":1,"bulk_daily_cap":100,"max_bulk_batch":50,"calendar_enabled":false,
       "custom_branding":false,"audit_logs":false,"max_messages_per_day":200,
       "ai_model":"gpt-4o-mini","api_access":false,"per_tenant_twilio":false}'::jsonb,
     0),
    ('starter', 'Starter', 49.00, 470.00,
     '{"max_admins":3,"bulk_daily_cap":500,"max_bulk_batch":200,"calendar_enabled":true,
       "custom_branding":false,"audit_logs":false,"max_messages_per_day":1000,
       "ai_model":"gpt-4o-mini","api_access":false,"per_tenant_twilio":false}'::jsonb,
     1),
    ('pro', 'Pro', 149.00, 1430.00,
     '{"max_admins":10,"bulk_daily_cap":2000,"max_bulk_batch":1000,"calendar_enabled":true,
       "custom_branding":true,"audit_logs":true,"max_messages_per_day":5000,
       "ai_model":"gpt-4o","api_access":false,"per_tenant_twilio":true}'::jsonb,
     2),
    ('enterprise', 'Enterprise', 0, 0,
     '{"max_admins":-1,"bulk_daily_cap":-1,"max_bulk_batch":-1,"calendar_enabled":true,
       "custom_branding":true,"audit_logs":true,"max_messages_per_day":-1,
       "ai_model":"any","api_access":true,"per_tenant_twilio":true}'::jsonb,
     3)
ON CONFLICT (name) DO NOTHING;

-- =============================================================================
-- 2. TENANTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                  VARCHAR(63) NOT NULL UNIQUE,
    name                  VARCHAR(255) NOT NULL,
    plan_id               UUID NOT NULL REFERENCES plans(id),
    status                VARCHAR(20) NOT NULL DEFAULT 'active'
                          CHECK (status IN ('trialing','active','suspended','cancelled')),
    brand_name            VARCHAR(255),
    brand_color_primary   VARCHAR(7),
    brand_color_secondary VARCHAR(7),
    brand_logo_url        TEXT,
    stripe_customer_id    VARCHAR(100),
    stripe_subscription_id VARCHAR(100),
    stripe_price_id       VARCHAR(100),
    trial_ends_at         TIMESTAMPTZ,
    current_period_start  TIMESTAMPTZ,
    current_period_end    TIMESTAMPTZ,
    timezone              VARCHAR(50) NOT NULL DEFAULT 'UTC',
    locale                VARCHAR(10) NOT NULL DEFAULT 'en',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at            TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tenants_slug              ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status            ON tenants(status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tenants_plan_id           ON tenants(plan_id);
CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer   ON tenants(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- Insert the default (legacy) tenant — all existing data will be assigned here.
-- Fixed UUID so it can be referenced deterministically in application code.
INSERT INTO tenants (id, slug, name, plan_id, status, timezone)
SELECT
    '00000000-0000-0000-0000-000000000001'::uuid,
    'moeen',
    'Moeen (Legacy)',
    (SELECT id FROM plans WHERE name = 'pro'),
    'active',
    'Asia/Qatar'
WHERE NOT EXISTS (
    SELECT 1 FROM tenants WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
);

-- =============================================================================
-- 3. USERS  (replaces admins)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email                     VARCHAR(255) NOT NULL,
    password_hash             VARCHAR(255) NOT NULL,
    full_name                 VARCHAR(255),
    role                      VARCHAR(20) NOT NULL DEFAULT 'tenant'
                              CHECK (role IN ('super_admin','tenant')),
    email_verified            BOOLEAN NOT NULL DEFAULT FALSE,
    email_verify_token        VARCHAR(255),
    email_verify_expires_at   TIMESTAMPTZ,
    password_reset_token      VARCHAR(255),
    password_reset_expires_at TIMESTAMPTZ,
    last_login_at             TIMESTAMPTZ,
    is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, email)
);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id      ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email          ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role           ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_verify_token   ON users(email_verify_token)
    WHERE email_verify_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_reset_token    ON users(password_reset_token)
    WHERE password_reset_token IS NOT NULL;

-- =============================================================================
-- 4. TENANT CONFIGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS tenant_configs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    -- Twilio
    twilio_account_sid      TEXT,
    twilio_auth_token       TEXT,
    twilio_whatsapp_number  TEXT,
    twilio_service_sid      TEXT,
    -- SendGrid
    sendgrid_api_key        TEXT,
    sender_email            TEXT,
    sender_name             TEXT,
    -- Google Calendar
    calendar_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
    calendar_credentials    JSONB,
    calendar_id             TEXT,
    calendar_timezone       VARCHAR(50),
    -- Messaging
    escalation_msg          TEXT,
    placeholder_msg         TEXT,
    -- Operational
    default_country_code    VARCHAR(5) NOT NULL DEFAULT '974',
    human_active_window_sec INTEGER NOT NULL DEFAULT 1800,
    max_twilio_length       INTEGER NOT NULL DEFAULT 1550,
    bulk_max_batch          INTEGER NOT NULL DEFAULT 500,
    bulk_daily_cap          INTEGER NOT NULL DEFAULT 1000,
    bulk_msg_delay_sec      NUMERIC(4,1) NOT NULL DEFAULT 1.5,
    extra                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 5. ASSISTANT CONFIGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS assistant_configs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
    openai_api_key         TEXT NOT NULL DEFAULT '',
    assistant_id           VARCHAR(100) NOT NULL DEFAULT '',
    model                  VARCHAR(100) NOT NULL DEFAULT 'gpt-4o',
    provider               VARCHAR(50) NOT NULL DEFAULT 'openai_assistants',
    max_poll_seconds       INTEGER NOT NULL DEFAULT 90,
    lock_expiry_seconds    INTEGER NOT NULL DEFAULT 300,
    max_tool_rounds        INTEGER NOT NULL DEFAULT 10,
    tools_enabled          JSONB NOT NULL DEFAULT '["escalate_to_human"]'::jsonb,
    sentiment_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    sentiment_model        VARCHAR(100) NOT NULL DEFAULT 'gpt-4o-mini',
    temperature            NUMERIC(3,2),
    instructions_override  TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 6. AUDIT LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     UUID REFERENCES tenants(id) ON DELETE SET NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action        VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id   TEXT,
    payload       JSONB,
    ip_address    INET,
    user_agent    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action    ON audit_logs(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_ts  ON audit_logs(actor_user_id, created_at DESC);

-- =============================================================================
-- 7. FEATURE FLAGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS feature_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    default_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS tenant_feature_flags (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    flag_name VARCHAR(100) NOT NULL REFERENCES feature_flags(name),
    enabled   BOOLEAN NOT NULL,
    PRIMARY KEY (tenant_id, flag_name)
);

-- =============================================================================
-- 8. USAGE EVENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS usage_events (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_type  VARCHAR(50) NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 1,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_type_ts
    ON usage_events(tenant_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_ts
    ON usage_events(tenant_id, created_at DESC);

-- =============================================================================
-- 9. MONTHLY USAGE SUMMARY
-- =============================================================================
CREATE TABLE IF NOT EXISTS monthly_usage_summary (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    month          DATE NOT NULL,
    event_type     VARCHAR(50) NOT NULL,
    total_quantity BIGINT NOT NULL DEFAULT 0,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, month, event_type)
);
CREATE INDEX IF NOT EXISTS idx_monthly_usage_tenant_month
    ON monthly_usage_summary(tenant_id, month DESC);

-- =============================================================================
-- 10. ONBOARDING STATE
-- =============================================================================
CREATE TABLE IF NOT EXISTS onboarding_state (
    tenant_id       UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    completed_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    current_step    VARCHAR(50) NOT NULL DEFAULT 'assistant',
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 11. ADD tenant_id TO EXISTING TABLES
-- =============================================================================

-- messages: add nullable tenant_id first
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);

-- user_threads: add nullable tenant_id first
ALTER TABLE user_threads ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);

-- =============================================================================
-- 12. BACKFILL EXISTING DATA WITH DEFAULT TENANT
-- =============================================================================
UPDATE messages
SET tenant_id = '00000000-0000-0000-0000-000000000001'::uuid
WHERE tenant_id IS NULL;

UPDATE user_threads
SET tenant_id = '00000000-0000-0000-0000-000000000001'::uuid
WHERE tenant_id IS NULL;

-- =============================================================================
-- 13. ENFORCE NOT NULL ON tenant_id
-- =============================================================================
ALTER TABLE messages ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE user_threads ALTER COLUMN tenant_id SET NOT NULL;

-- =============================================================================
-- 14. ADD TENANT-SCOPED INDEXES
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_messages_tenant_phone_ts
    ON messages(tenant_id, phone, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_tenant_ts
    ON messages(tenant_id, timestamp DESC);

-- =============================================================================
-- 15. CHANGE user_threads PRIMARY KEY → (tenant_id, user_id)
-- =============================================================================
-- Create the new composite unique constraint first (can run concurrently in pg 9.5+)
-- We use a regular UNIQUE INDEX here (not CONCURRENTLY) for simplicity in migration.
DO $$
BEGIN
    -- Only create the new unique index if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'user_threads'
          AND indexname = 'idx_user_threads_tenant_user'
    ) THEN
        CREATE UNIQUE INDEX idx_user_threads_tenant_user
            ON user_threads(tenant_id, user_id);
    END IF;
END $$;

-- Swap the primary key (requires brief exclusive lock — run during low traffic)
DO $$
BEGIN
    -- Check if the PK is still the old single-column one
    IF EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.conrelid = 'user_threads'::regclass
          AND c.contype = 'p'
          AND array_length(c.conkey, 1) = 1
          AND a.attname = 'user_id'
    ) THEN
        ALTER TABLE user_threads DROP CONSTRAINT user_threads_pkey;
        ALTER TABLE user_threads ADD PRIMARY KEY (tenant_id, user_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_user_threads_escalated
    ON user_threads(tenant_id, escalation_status)
    WHERE escalation_status = 'escalated';

CREATE INDEX IF NOT EXISTS idx_user_threads_last_accessed_tenant
    ON user_threads(tenant_id, last_accessed DESC);

-- =============================================================================
-- 16. MIGRATE admins → users  (idempotent via ON CONFLICT DO NOTHING)
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'admins'
    ) THEN
        INSERT INTO users (tenant_id, email, password_hash, role, email_verified, created_at)
        SELECT
            '00000000-0000-0000-0000-000000000001'::uuid,
            username,       -- username treated as email (may not be email format — that's OK)
            password_hash,
            'tenant',
            TRUE,           -- existing admins are pre-verified
            created_at
        FROM admins
        ON CONFLICT (tenant_id, email) DO NOTHING;
    END IF;
END $$;

-- =============================================================================
-- 17. SEED DEFAULT TENANT'S CONFIG ROWS
-- (Values are filled in by run_migration.py using current env vars)
-- =============================================================================
INSERT INTO tenant_configs (tenant_id)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid)
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO assistant_configs (tenant_id, openai_api_key, assistant_id)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid, '', '')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO onboarding_state (tenant_id, completed_steps, completed_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    '["assistant","whatsapp","calendar","branding","done"]'::jsonb,
    NOW()
)
ON CONFLICT (tenant_id) DO NOTHING;
