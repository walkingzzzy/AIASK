CREATE TABLE IF NOT EXISTS unified_decision_diff_audit (
    id BIGSERIAL PRIMARY KEY,
    trace_id VARCHAR(64),
    user_id VARCHAR(64),
    stock_code VARCHAR(16) NOT NULL,
    investment_style VARCHAR(16) NOT NULL,
    unified_action VARCHAR(24) NOT NULL,
    action_alignment VARCHAR(16) NOT NULL,
    legacy_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    disagreements JSONB NOT NULL DEFAULT '[]'::jsonb,
    diff_summary TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unified_decision_diff_audit_user_created
    ON unified_decision_diff_audit(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_unified_decision_diff_audit_stock_created
    ON unified_decision_diff_audit(stock_code, created_at DESC);
