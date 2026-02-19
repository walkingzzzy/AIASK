-- P0: auth/rbac/audit 基础表

CREATE TABLE IF NOT EXISTS app_users (
  id VARCHAR(64) PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARCHAR(128) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
  id VARCHAR(64) PRIMARY KEY,
  code VARCHAR(32) NOT NULL UNIQUE,
  name VARCHAR(64) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS permissions (
  id VARCHAR(64) PRIMARY KEY,
  code VARCHAR(64) NOT NULL UNIQUE,
  name VARCHAR(128) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_roles (
  id BIGSERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES app_users(id),
  role_id VARCHAR(64) NOT NULL REFERENCES roles(id),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, role_id)
);

CREATE TABLE IF NOT EXISTS app_sessions (
  id BIGSERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES app_users(id),
  access_jti VARCHAR(64) NOT NULL UNIQUE,
  refresh_token_hash VARCHAR(128) NOT NULL UNIQUE,
  access_expires_at TIMESTAMPTZ NOT NULL,
  refresh_expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id BIGSERIAL PRIMARY KEY,
  trace_id VARCHAR(64) NOT NULL,
  method VARCHAR(16) NOT NULL,
  path TEXT NOT NULL,
  status INT NOT NULL,
  duration_ms INT NOT NULL,
  user_id VARCHAR(64),
  username VARCHAR(64),
  user_role VARCHAR(32),
  ts TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_user_id ON app_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_app_sessions_access_jti ON app_sessions(access_jti);
CREATE INDEX IF NOT EXISTS idx_app_sessions_refresh_hash ON app_sessions(refresh_token_hash);
CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(ts DESC);

INSERT INTO roles (id, code, name)
VALUES ('role_admin', 'admin', '管理员'), ('role_user', 'user', '普通用户')
ON CONFLICT (code) DO NOTHING;

INSERT INTO app_users (id, username, password_hash)
VALUES
  ('u_admin', 'admin', '240be518fabd2724ddb6f04eebf2ef9f20f3f854de3ec7d00ed284aa9f0c45c0'),
  ('u_demo', 'demo',  'd3ad9315a6d2ce241e7ef31f85a048760a8aa2f96f5c85ca9f1f295f82bc4ab8')
ON CONFLICT (username) DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
VALUES ('u_admin', 'role_admin'), ('u_demo', 'role_user')
ON CONFLICT (user_id, role_id) DO NOTHING;

