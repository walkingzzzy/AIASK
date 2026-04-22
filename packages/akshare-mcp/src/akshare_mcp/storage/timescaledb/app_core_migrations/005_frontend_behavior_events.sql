CREATE TABLE IF NOT EXISTS frontend_behavior_events (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES app_users(id),
    session_id VARCHAR(128) NOT NULL,
    page_key VARCHAR(128) NOT NULL,
    route TEXT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    target_type VARCHAR(64),
    target_label TEXT,
    target_id VARCHAR(255),
    target_testid VARCHAR(255),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(128) NOT NULL DEFAULT 'web',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_frontend_behavior_events_user_created_at
    ON frontend_behavior_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_frontend_behavior_events_session_created_at
    ON frontend_behavior_events(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_frontend_behavior_events_page_key_created_at
    ON frontend_behavior_events(page_key, created_at DESC);
