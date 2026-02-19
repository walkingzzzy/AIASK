-- 002: User preferences extension
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS risk_level VARCHAR(16) DEFAULT 'moderate';
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';
