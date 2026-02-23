import { Injectable, Logger, UnauthorizedException, ConflictException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHash, createHmac, randomUUID, timingSafeEqual } from 'crypto';
import { DbService } from '../db/db.service';

type Role = 'admin' | 'user';

type AppUser = {
  id: string;
  username: string;
  passwordHash: string;
  role: Role;
};

type Session = {
  user: Omit<AppUser, 'passwordHash'>;
  accessJti: string;
  refreshToken: string;
  accessExpiresAt: number;
  refreshExpiresAt: number;
  revoked: boolean;
};

type AccessPayload = {
  sub: string;
  username: string;
  role: Role;
  jti: string;
  typ: 'access';
  exp: number;
  iat: number;
};

@Injectable()
export class AuthService {
  private readonly logger = new Logger(AuthService.name);
  private readonly accessTtlSec: number;
  private readonly refreshTtlSec: number;
  private readonly jwtSecret: string;

  private readonly users: AppUser[];
  private readonly sessionsByRefresh = new Map<string, Session>();
  private readonly accessJtiToRefresh = new Map<string, string>();

  constructor(
    private readonly configService: ConfigService,
    private readonly dbService: DbService,
  ) {
    this.accessTtlSec = Math.max(60, Number(this.configService.get('APP_ACCESS_TOKEN_TTL_SECONDS', 7200)));
    this.refreshTtlSec = Math.max(300, Number(this.configService.get('APP_REFRESH_TOKEN_TTL_SECONDS', 604800)));
    this.jwtSecret = this.configService.get<string>('APP_JWT_SECRET', 'dev-secret-change-me');

    if (this.jwtSecret === 'dev-secret-change-me') {
      this.logger.warn('APP_JWT_SECRET 使用默认值，请在生产环境中设置强随机密钥');
    }

    const adminPassword = this.configService.get<string>('APP_ADMIN_PASSWORD', 'admin');
    this.users = [
      { id: 'u_admin', username: 'admin', passwordHash: this.hash(adminPassword), role: 'admin' },
      { id: 'u_demo', username: 'demo', passwordHash: this.hash('demo123'), role: 'user' },
    ];
  }

  async login(username: string, password: string) {
    this.cleanupExpired();
    const user = await this.verifyCredential(username, password);
    const now = Date.now();
    const accessJti = this.newJti();

    const payload: AccessPayload = {
      sub: user.id,
      username: user.username,
      role: user.role,
      jti: accessJti,
      typ: 'access',
      iat: Math.floor(now / 1000),
      exp: Math.floor(now / 1000) + this.accessTtlSec,
    };

    const accessToken = this.signJwt(payload);
    const refreshToken = this.newRefreshToken();

    const session: Session = {
      user,
      accessJti,
      refreshToken,
      accessExpiresAt: now + this.accessTtlSec * 1000,
      refreshExpiresAt: now + this.refreshTtlSec * 1000,
      revoked: false,
    };

    if (this.dbService.enabled) {
      await this.dbService.query(
        `INSERT INTO app_sessions
         (user_id, access_jti, refresh_token_hash, access_expires_at, refresh_expires_at, revoked_at, updated_at)
         VALUES ($1,$2,$3,to_timestamp($4),to_timestamp($5),NULL,NOW())`,
        [user.id, accessJti, this.hash(refreshToken), payload.exp, Math.floor(session.refreshExpiresAt / 1000)],
      );
    } else {
      this.sessionsByRefresh.set(session.refreshToken, session);
      this.accessJtiToRefresh.set(session.accessJti, session.refreshToken);
    }

    return {
      user,
      accessToken,
      refreshToken,
      expiresIn: this.accessTtlSec,
    };
  }

  async register(username: string, password: string) {
    const normalized = username.trim();
    if (!normalized) throw new ConflictException('用户名不能为空');

    if (this.dbService.enabled) {
      const existing = await this.dbService.query<{ id: string }>(
        `SELECT id FROM app_users WHERE username = $1 LIMIT 1`,
        [normalized],
      );
      if (existing.rows.length > 0) {
        throw new ConflictException('用户名已存在');
      }
      const userId = `u_${randomUUID().replace(/-/g, '').slice(0, 12)}`;
      const passwordHash = this.hash(password);
      await this.dbService.query(
        `INSERT INTO app_users (id, username, password_hash, active) VALUES ($1, $2, $3, TRUE)`,
        [userId, normalized, passwordHash],
      );
    } else {
      const exists = this.users.find((u) => u.username === normalized);
      if (exists) throw new ConflictException('用户名已存在');
      const userId = `u_${randomUUID().replace(/-/g, '').slice(0, 12)}`;
      this.users.push({
        id: userId,
        username: normalized,
        passwordHash: this.hash(password),
        role: 'user',
      });
    }

    return this.login(normalized, password);
  }

  async refresh(refreshToken: string) {
    this.cleanupExpired();

    let user: { id: string; username: string; role: Role };
    let sessionId: number | null = null;
    const refreshHash = this.hash(refreshToken);
    const nowSec = Math.floor(Date.now() / 1000);

    if (this.dbService.enabled) {
      const found = await this.dbService.query<{
        id: number;
        user_id: string;
        username: string;
        role: string;
        refresh_expires_at: Date;
      }>(
        `SELECT s.id, s.user_id, u.username,
                COALESCE(r.code, 'user') AS role,
                s.refresh_expires_at
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
      sessionId = row.id;
      user = {
        id: row.user_id,
        username: row.username,
        role: (row.role === 'admin' ? 'admin' : 'user') as Role,
      };
    } else {
      const session = this.sessionsByRefresh.get(refreshToken);
      if (!session || session.revoked || session.refreshExpiresAt <= Date.now()) {
        throw new UnauthorizedException('refresh token 无效或已过期');
      }
      this.accessJtiToRefresh.delete(session.accessJti);
      user = session.user;
    }

    const nextJti = this.newJti();
    const payload: AccessPayload = {
      sub: user.id,
      username: user.username,
      role: user.role,
      jti: nextJti,
      typ: 'access',
      iat: nowSec,
      exp: nowSec + this.accessTtlSec,
    };
    const accessToken = this.signJwt(payload);

    if (this.dbService.enabled) {
      await this.dbService.query(
        `UPDATE app_sessions
            SET access_jti = $1,
                access_expires_at = to_timestamp($2),
                updated_at = NOW()
          WHERE id = $3`,
        [nextJti, payload.exp, sessionId],
      );
    } else {
      const session = this.sessionsByRefresh.get(refreshToken)!;
      session.accessJti = nextJti;
      session.accessExpiresAt = payload.exp * 1000;
      this.accessJtiToRefresh.set(nextJti, refreshToken);
    }

    return {
      user,
      accessToken,
      refreshToken,
      expiresIn: this.accessTtlSec,
    };
  }

  async logout(params: { accessToken?: string; refreshToken?: string }) {
    const { accessToken, refreshToken } = params;

    if (refreshToken) {
      await this.revokeByRefresh(refreshToken);
    }
    if (accessToken) {
      await this.revokeByAccess(accessToken);
    }

    return { success: true };
  }

  async verifyAccessToken(accessToken: string) {
    this.cleanupExpired();

    const payload = this.verifyJwt(accessToken);
    if (!payload || payload.typ !== 'access') {
      throw new UnauthorizedException('access token 无效');
    }

    if (this.dbService.enabled) {
      const found = await this.dbService.query<{ user_id: string; username: string; role: string }>(
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
      };
    }

    const refresh = this.accessJtiToRefresh.get(payload.jti);
    if (!refresh) throw new UnauthorizedException('access token 无效');
    const session = this.sessionsByRefresh.get(refresh);
    if (!session || session.revoked || session.accessExpiresAt <= Date.now() || session.user.id !== payload.sub) {
      throw new UnauthorizedException('access token 已过期');
    }
    return session.user;
  }

  private async revokeByRefresh(refreshToken: string) {
    if (this.dbService.enabled) {
      await this.dbService.query(
        `UPDATE app_sessions SET revoked_at = NOW(), updated_at = NOW()
          WHERE refresh_token_hash = $1 AND revoked_at IS NULL`,
        [this.hash(refreshToken)],
      );
      return;
    }

    const session = this.sessionsByRefresh.get(refreshToken);
    if (!session) return;
    session.revoked = true;
    this.accessJtiToRefresh.delete(session.accessJti);
    this.sessionsByRefresh.delete(refreshToken);
  }

  private async revokeByAccess(accessToken: string) {
    const payload = this.verifyJwt(accessToken);
    if (!payload) return;

    if (this.dbService.enabled) {
      await this.dbService.query(
        `UPDATE app_sessions SET revoked_at = NOW(), updated_at = NOW()
          WHERE access_jti = $1 AND revoked_at IS NULL`,
        [payload.jti],
      );
      return;
    }

    const refresh = this.accessJtiToRefresh.get(payload.jti);
    if (!refresh) return;
    await this.revokeByRefresh(refresh);
  }

  private cleanupExpired() {
    const now = Date.now();
    for (const [refresh, session] of this.sessionsByRefresh.entries()) {
      if (session.revoked || session.refreshExpiresAt <= now) {
        this.accessJtiToRefresh.delete(session.accessJti);
        this.sessionsByRefresh.delete(refresh);
      }
    }
  }

  private newJti() {
    return randomUUID().replace(/-/g, '');
  }

  private newRefreshToken() {
    return `rtk_${randomUUID().replace(/-/g, '')}`;
  }

  private signJwt(payload: AccessPayload): string {
    const header = this.base64Url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const body = this.base64Url(JSON.stringify(payload));
    const message = `${header}.${body}`;
    const signature = createHmac('sha256', this.jwtSecret).update(message).digest('base64url');
    return `${message}.${signature}`;
  }

  private verifyJwt(token: string): AccessPayload | null {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const [header, body, signature] = parts;
    const message = `${header}.${body}`;
    const expected = createHmac('sha256', this.jwtSecret).update(message).digest('base64url');
    if (!this.safeEqual(signature, expected)) return null;

    try {
      const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf-8')) as AccessPayload;
      if (!payload || payload.typ !== 'access') return null;
      if (!payload.exp || payload.exp <= Math.floor(Date.now() / 1000)) return null;
      if (!payload.sub || !payload.jti || !payload.username || !payload.role) return null;
      return payload;
    } catch {
      return null;
    }
  }

  private async verifyCredential(username: string, password: string): Promise<{ id: string; username: string; role: Role }> {
    const normalized = username.trim();
    const passwordHash = this.hash(password);

    if (this.dbService.enabled) {
      const found = await this.dbService.query<{ id: string; username: string; password_hash: string; role: string }>(
        `SELECT u.id, u.username, u.password_hash, COALESCE(r.code, 'user') AS role
           FROM app_users u
      LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.active = TRUE
      LEFT JOIN roles r ON r.id = ur.role_id AND r.active = TRUE
          WHERE u.username = $1 AND u.active = TRUE
          ORDER BY u.id
          LIMIT 1`,
        [normalized],
      );
      const row = found.rows[0];
      if (!row || row.password_hash !== passwordHash) {
        throw new UnauthorizedException('用户名或密码错误');
      }
      return { id: row.id, username: row.username, role: (row.role === 'admin' ? 'admin' : 'user') as Role };
    }

    const found = this.users.find((u) => u.username === normalized && u.passwordHash === passwordHash);
    if (!found) throw new UnauthorizedException('用户名或密码错误');
    return { id: found.id, username: found.username, role: found.role };
  }

  private hash(text: string): string {
    return createHash('sha256').update(text).digest('hex');
  }

  private safeEqual(a: string, b: string): boolean {
    const ab = Buffer.from(a);
    const bb = Buffer.from(b);
    if (ab.length !== bb.length) return false;
    return timingSafeEqual(ab, bb);
  }

  private base64Url(text: string): string {
    return Buffer.from(text).toString('base64url');
  }
}

