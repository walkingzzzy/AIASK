import { scryptSync, randomBytes } from 'node:crypto';

const PASSWORD_HASH_PREFIX = 'scrypt';
const PASSWORD_HASH_N = 16384;
const PASSWORD_HASH_R = 8;
const PASSWORD_HASH_P = 1;
const PASSWORD_HASH_KEYLEN = 64;
const PASSWORD_HASH_MAXMEM = 64 * 1024 * 1024;

function encodePasswordHash(salt, derived) {
  return [
    PASSWORD_HASH_PREFIX,
    String(PASSWORD_HASH_N),
    String(PASSWORD_HASH_R),
    String(PASSWORD_HASH_P),
    salt,
    derived.toString('base64url'),
  ].join('$');
}

function hashPasswordSync(password) {
  const salt = randomBytes(16).toString('base64url');
  const derived = scryptSync(password, salt, PASSWORD_HASH_KEYLEN, {
    N: PASSWORD_HASH_N,
    r: PASSWORD_HASH_R,
    p: PASSWORD_HASH_P,
    maxmem: PASSWORD_HASH_MAXMEM,
  });
  return encodePasswordHash(salt, derived);
}

export async function bootstrapBrowserEnvironment(runtime) {
  const adminPassword = runtime.baseEnv.APP_ADMIN_PASSWORD || 'admin123';
  const demoPassword = runtime.baseEnv.APP_DEMO_PASSWORD || 'demo123';

  const client = runtime.pgClientFactory();
  await client.connect();

  try {
    await client.query('BEGIN');

    await client.query(
      `INSERT INTO roles (id, code, name, active)
       VALUES ('role_admin', 'admin', '管理员', TRUE),
              ('role_user', 'user', '普通用户', TRUE)
       ON CONFLICT (code) DO UPDATE
         SET name = EXCLUDED.name,
             active = TRUE`,
    );

    await client.query(
      `INSERT INTO app_users (id, username, password_hash, active)
       VALUES ($1, $2, $3, TRUE)
       ON CONFLICT (username) DO UPDATE
         SET password_hash = EXCLUDED.password_hash,
             active = TRUE,
             updated_at = NOW()`,
      ['u_admin', 'admin', hashPasswordSync(adminPassword)],
    );

    await client.query(
      `INSERT INTO app_users (id, username, password_hash, active)
       VALUES ($1, $2, $3, TRUE)
       ON CONFLICT (username) DO UPDATE
         SET password_hash = EXCLUDED.password_hash,
             active = TRUE,
             updated_at = NOW()`,
      ['u_demo', 'demo', hashPasswordSync(demoPassword)],
    );

    await client.query(
      `INSERT INTO user_roles (user_id, role_id, active)
       VALUES ('u_admin', 'role_admin', TRUE)
       ON CONFLICT (user_id, role_id) DO UPDATE
         SET active = TRUE`,
    );
    await client.query(
      `INSERT INTO user_roles (user_id, role_id, active)
       VALUES ('u_demo', 'role_user', TRUE)
       ON CONFLICT (user_id, role_id) DO UPDATE
         SET active = TRUE`,
    );

    await client.query(
      `DELETE FROM app_sessions WHERE user_id IN ('u_admin', 'u_demo')`,
    );

    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    await client.end();
  }
}
