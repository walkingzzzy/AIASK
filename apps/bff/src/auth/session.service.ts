import { BadRequestException, UnauthorizedException } from '@nestjs/common';
import { randomUUID } from 'crypto';
import type { DbService } from '../db/db.service';
import type { AccessPayload, Role, Session } from './auth.types';
import { hash, newJti, newRefreshToken, signJwt, verifyJwt } from './jwt.service';

// ---------------------------------------------------------------------------
// In-memory session stores (used when DB is not enabled)
// ---------------------------------------------------------------------------

export class SessionStore {
  readonly sessionsByRefresh = new Map<string, Session>();
  readonly accessJtiToRefresh = new Map<string, string>();

  cleanup(): void {
    const now = Date.now();
    for (const [refresh, session] of this.sessionsByRefresh.entries()) {
      if (session.revoked || session.refreshExpiresAt <= now) {
        this.accessJtiToRefresh.delete(session.accessJti);
        this.sessionsByRefresh.delete(refresh);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Session CRUD functions
// ---------------------------------------------------------------------------

export async function createSession(
  store: SessionStore,
  dbService: DbService,
  user: { id: string; username: string; role: Role },
  accessTtlSec: number,
  refreshTtlSec: number,
  jwtSecret: string,
  options: { mfaVerified?: boolean } = {},
): Promise<{ accessToken: string; refreshToken: string; expiresIn: number }> {
  const now = Date.now();
  const accessJti = newJti();
  const mfaVerified = options.mfaVerified === true;

  const payload: AccessPayload = {
    sub: user.id,
    username: user.username,
    role: user.role,
    jti: accessJti,
    mfa: mfaVerified,
    typ: 'access',
    iat: Math.floor(now / 1000),
    exp: Math.floor(now / 1000) + accessTtlSec,
  };

  const accessToken = signJwt(payload, jwtSecret);
  const refreshToken = newRefreshToken();
  const sessionId = `sess_${randomUUID().replace(/-/g, '').slice(0, 16)}`;

  const session: Session = {
    id: sessionId,
    user,
    accessJti,
    refreshToken,
    mfaVerified,
    accessExpiresAt: now + accessTtlSec * 1000,
    refreshExpiresAt: now + refreshTtlSec * 1000,
    revoked: false,
    createdAt: now,
    updatedAt: now,
  };

  if (dbService.enabled) {
    await dbService.query(
      `INSERT INTO app_sessions
       (user_id, access_jti, refresh_token_hash, mfa_verified_at, access_expires_at, refresh_expires_at, revoked_at, updated_at)
       VALUES ($1,$2,$3,$4,to_timestamp($5),to_timestamp($6),NULL,NOW())`,
      [
        user.id,
        accessJti,
        hash(refreshToken),
        mfaVerified ? new Date(now).toISOString() : null,
        payload.exp,
        Math.floor(session.refreshExpiresAt / 1000),
      ],
    );
  } else {
    store.sessionsByRefresh.set(session.refreshToken, session);
    store.accessJtiToRefresh.set(session.accessJti, session.refreshToken);
  }

  return { accessToken, refreshToken, expiresIn: accessTtlSec };
}

export async function listSessions(
  store: SessionStore,
  dbService: DbService,
  userId: string,
  currentAccessJti?: string,
) {
  if (dbService.enabled) {
    const result = await dbService.query<{
      id: number;
      access_jti: string;
      access_expires_at: Date;
      refresh_expires_at: Date;
      created_at: Date;
    }>(
      `SELECT id, access_jti, access_expires_at, refresh_expires_at, created_at
         FROM app_sessions
        WHERE user_id = $1 AND revoked_at IS NULL
        ORDER BY id DESC
        LIMIT 20`,
      [userId],
    );

    return result.rows.map((row) => ({
      id: String(row.id),
      current: row.access_jti === currentAccessJti,
      status: new Date(row.refresh_expires_at).getTime() > Date.now() ? 'active' : 'expired',
      createdAt: new Date(row.created_at).toISOString(),
      accessExpiresAt: new Date(row.access_expires_at).toISOString(),
      refreshExpiresAt: new Date(row.refresh_expires_at).toISOString(),
    }));
  }

  return Array.from(store.sessionsByRefresh.values())
    .filter((session) => !session.revoked && session.user.id === userId)
    .sort((a, b) => b.createdAt - a.createdAt)
    .map((session) => ({
      id: session.id,
      current: session.accessJti === currentAccessJti,
      status: session.refreshExpiresAt > Date.now() ? 'active' : 'expired',
      createdAt: new Date(session.createdAt).toISOString(),
      accessExpiresAt: new Date(session.accessExpiresAt).toISOString(),
      refreshExpiresAt: new Date(session.refreshExpiresAt).toISOString(),
    }));
}

export async function revokeSession(
  store: SessionStore,
  dbService: DbService,
  userId: string,
  sessionId: string,
  currentAccessJti?: string,
) {
  const sessions = await listSessions(store, dbService, userId, currentAccessJti);
  const target = sessions.find((item) => item.id === sessionId);
  if (!target) throw new BadRequestException('会话不存在');
  if (target.current) throw new BadRequestException('不能吊销当前会话');

  if (dbService.enabled) {
    await dbService.query(
      'UPDATE app_sessions SET revoked_at = NOW(), updated_at = NOW() WHERE id = $1::bigint AND user_id = $2 AND revoked_at IS NULL',
      [sessionId, userId],
    );
    return { success: true };
  }

  for (const [refresh, session] of store.sessionsByRefresh.entries()) {
    if (session.user.id !== userId || session.id !== sessionId) continue;
    store.accessJtiToRefresh.delete(session.accessJti);
    store.sessionsByRefresh.delete(refresh);
    return { success: true };
  }

  throw new BadRequestException('会话不存在');
}

export async function revokeByRefresh(
  store: SessionStore,
  dbService: DbService,
  refreshToken: string,
) {
  if (dbService.enabled) {
    await dbService.query(
      `UPDATE app_sessions SET revoked_at = NOW(), updated_at = NOW()
        WHERE refresh_token_hash = $1 AND revoked_at IS NULL`,
      [hash(refreshToken)],
    );
    return;
  }

  const session = store.sessionsByRefresh.get(refreshToken);
  if (!session) return;
  session.revoked = true;
  store.accessJtiToRefresh.delete(session.accessJti);
  store.sessionsByRefresh.delete(refreshToken);
}

export async function revokeByAccess(
  store: SessionStore,
  dbService: DbService,
  accessToken: string,
  jwtSecret: string,
) {
  const payload = verifyJwt(accessToken, jwtSecret);
  if (!payload) return;

  if (dbService.enabled) {
    await dbService.query(
      `UPDATE app_sessions SET revoked_at = NOW(), updated_at = NOW()
        WHERE access_jti = $1 AND revoked_at IS NULL`,
      [payload.jti],
    );
    return;
  }

  const refresh = store.accessJtiToRefresh.get(payload.jti);
  if (!refresh) return;
  await revokeByRefresh(store, dbService, refresh);
}

export async function refreshSession(
  store: SessionStore,
  dbService: DbService,
  refreshToken: string,
  accessTtlSec: number,
  jwtSecret: string,
  options: { requireMfa?: boolean } = {},
): Promise<{ user: { id: string; username: string; role: Role }; accessToken: string; refreshToken: string; expiresIn: number }> {
  const refreshHash = hash(refreshToken);
  const nowSec = Math.floor(Date.now() / 1000);
  const requireMfa = options.requireMfa === true;

  let user: { id: string; username: string; role: Role };
  let sessionId: number | null = null;
  let mfaVerified = false;

  if (dbService.enabled) {
    const found = await dbService.query<{
      id: number;
      user_id: string;
      username: string;
      role: string;
      refresh_expires_at: Date;
      mfa_verified_at: Date | null;
    }>(
      `SELECT s.id, s.user_id, u.username,
              COALESCE(r.code, 'user') AS role,
              s.refresh_expires_at,
              s.mfa_verified_at
         FROM app_sessions s
         JOIN app_users u ON u.id = s.user_id
    LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.active = TRUE
    LEFT JOIN roles r ON r.id = ur.role_id AND r.active = TRUE
        WHERE s.refresh_token_hash = $1
          AND s.revoked_at IS NULL
          AND u.active = TRUE
        ORDER BY s.id DESC
        LIMIT 1`,
      [refreshHash],
    );

    const row = found.rows[0];
    if (!row || new Date(row.refresh_expires_at).getTime() <= Date.now()) {
      throw new UnauthorizedException('refresh token 无效或已过期');
    }
    mfaVerified = row.mfa_verified_at != null;
    if (requireMfa && !mfaVerified) {
      throw new UnauthorizedException('当前会话尚未完成 2FA 验证，请重新登录');
    }
    sessionId = row.id;
    user = {
      id: row.user_id,
      username: row.username,
      role: (row.role === 'admin' ? 'admin' : 'user') as Role,
    };
  } else {
    const session = store.sessionsByRefresh.get(refreshToken);
    if (!session || session.revoked || session.refreshExpiresAt <= Date.now()) {
      throw new UnauthorizedException('refresh token 无效或已过期');
    }
    if (requireMfa && !session.mfaVerified) {
      throw new UnauthorizedException('当前会话尚未完成 2FA 验证，请重新登录');
    }
    store.accessJtiToRefresh.delete(session.accessJti);
    mfaVerified = session.mfaVerified;
    user = session.user;
  }

  const nextJti = newJti();
  const payload: AccessPayload = {
    sub: user.id,
    username: user.username,
    role: user.role,
    jti: nextJti,
    mfa: mfaVerified,
    typ: 'access',
    iat: nowSec,
    exp: nowSec + accessTtlSec,
  };
  const accessToken = signJwt(payload, jwtSecret);

  if (dbService.enabled) {
    await dbService.query(
      `UPDATE app_sessions
          SET access_jti = $1,
              access_expires_at = to_timestamp($2),
              updated_at = NOW()
        WHERE id = $3`,
      [nextJti, payload.exp, sessionId],
    );
  } else {
    const session = store.sessionsByRefresh.get(refreshToken)!;
    session.accessJti = nextJti;
    session.mfaVerified = mfaVerified;
    session.accessExpiresAt = payload.exp * 1000;
    session.updatedAt = Date.now();
    store.accessJtiToRefresh.set(nextJti, refreshToken);
  }

  return { user, accessToken, refreshToken, expiresIn: accessTtlSec };
}

export async function inspectRefreshSession(
  store: SessionStore,
  dbService: DbService,
  refreshToken: string,
): Promise<{ user: { id: string; username: string; role: Role }; mfaVerified: boolean }> {
  const refreshHash = hash(refreshToken);

  if (dbService.enabled) {
    const found = await dbService.query<{
      user_id: string;
      username: string;
      role: string;
      refresh_expires_at: Date;
      mfa_verified_at: Date | null;
    }>(
      `SELECT s.user_id, u.username,
              COALESCE(r.code, 'user') AS role,
              s.refresh_expires_at,
              s.mfa_verified_at
         FROM app_sessions s
         JOIN app_users u ON u.id = s.user_id
    LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.active = TRUE
    LEFT JOIN roles r ON r.id = ur.role_id AND r.active = TRUE
        WHERE s.refresh_token_hash = $1
          AND s.revoked_at IS NULL
          AND u.active = TRUE
        ORDER BY s.id DESC
        LIMIT 1`,
      [refreshHash],
    );

    const row = found.rows[0];
    if (!row || new Date(row.refresh_expires_at).getTime() <= Date.now()) {
      throw new UnauthorizedException('refresh token 无效或已过期');
    }

    return {
      user: {
        id: row.user_id,
        username: row.username,
        role: (row.role === 'admin' ? 'admin' : 'user') as Role,
      },
      mfaVerified: row.mfa_verified_at != null,
    };
  }

  const session = store.sessionsByRefresh.get(refreshToken);
  if (!session || session.revoked || session.refreshExpiresAt <= Date.now()) {
    throw new UnauthorizedException('refresh token 无效或已过期');
  }

  return {
    user: session.user,
    mfaVerified: session.mfaVerified,
  };
}

export async function markSessionMfaVerified(
  store: SessionStore,
  dbService: DbService,
  accessJti: string,
) {
  if (!accessJti) {
    return;
  }

  if (dbService.enabled) {
    await dbService.query(
      `UPDATE app_sessions
          SET mfa_verified_at = COALESCE(mfa_verified_at, NOW()),
              updated_at = NOW()
        WHERE access_jti = $1
          AND revoked_at IS NULL`,
      [accessJti],
    );
    return;
  }

  const refresh = store.accessJtiToRefresh.get(accessJti);
  if (!refresh) {
    return;
  }
  const session = store.sessionsByRefresh.get(refresh);
  if (!session) {
    return;
  }
  session.mfaVerified = true;
  session.updatedAt = Date.now();
}

export async function verifyAccessTokenSession(
  store: SessionStore,
  dbService: DbService,
  accessToken: string,
  jwtSecret: string,
): Promise<{ id: string; username: string; role: Role; jti: string }> {
  const payload = verifyJwt(accessToken, jwtSecret);
  if (!payload || payload.typ !== 'access') {
    throw new UnauthorizedException('access token 无效');
  }

  if (dbService.enabled) {
    const found = await dbService.query<{ user_id: string; username: string; role: string }>(
      `SELECT s.user_id, u.username, COALESCE(r.code, 'user') AS role
         FROM app_sessions s
         JOIN app_users u ON u.id = s.user_id
    LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.active = TRUE
    LEFT JOIN roles r ON r.id = ur.role_id AND r.active = TRUE
        WHERE s.access_jti = $1
          AND s.user_id = $2
          AND s.revoked_at IS NULL
          AND s.access_expires_at > NOW()
          AND u.active = TRUE
        ORDER BY s.id DESC
        LIMIT 1`,
      [payload.jti, payload.sub],
    );

    const row = found.rows[0];
    if (!row) {
      throw new UnauthorizedException('access token 已过期');
    }
    return {
      id: row.user_id,
      username: row.username,
      role: (row.role === 'admin' ? 'admin' : 'user') as Role,
      jti: payload.jti,
    };
  }

  const refresh = store.accessJtiToRefresh.get(payload.jti);
  if (!refresh) throw new UnauthorizedException('access token 无效');
  const session = store.sessionsByRefresh.get(refresh);
  if (!session || session.revoked || session.accessExpiresAt <= Date.now() || session.user.id !== payload.sub) {
    throw new UnauthorizedException('access token 已过期');
  }
  return { ...session.user, jti: payload.jti };
}
