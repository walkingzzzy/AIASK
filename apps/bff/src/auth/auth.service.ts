import { ConflictException, Injectable, Logger, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { randomUUID } from 'crypto';
import { DbService } from '../db/db.service';
import { PreferencesService } from './preferences.service';
import type { AppUser, Role } from './auth.types';
import { hash } from './jwt.service';
import {
  SessionStore,
  createSession,
  listSessions,
  revokeSession,
  revokeByRefresh,
  revokeByAccess,
  refreshSession,
  verifyAccessTokenSession,
} from './session.service';

@Injectable()
export class AuthService {
  private readonly logger = new Logger(AuthService.name);
  private readonly accessTtlSec: number;
  private readonly refreshTtlSec: number;
  private readonly jwtSecret: string;

  private readonly users: AppUser[];
  private readonly store = new SessionStore();

  constructor(
    private readonly configService: ConfigService,
    private readonly dbService: DbService,
    private readonly preferencesService: PreferencesService,
  ) {
    this.accessTtlSec = Math.max(60, Number(this.configService.get('APP_ACCESS_TOKEN_TTL_SECONDS', 7200)));
    this.refreshTtlSec = Math.max(300, Number(this.configService.get('APP_REFRESH_TOKEN_TTL_SECONDS', 604800)));
    this.jwtSecret = this.configService.get<string>('APP_JWT_SECRET', 'dev-secret-change-me');

    if (this.jwtSecret === 'dev-secret-change-me') {
      this.logger.warn('APP_JWT_SECRET 使用默认值，请在生产环境中设置强随机密钥');
    }

    const adminPassword = this.configService.get<string>('APP_ADMIN_PASSWORD', 'admin');
    this.users = [
      { id: 'u_admin', username: 'admin', passwordHash: hash(adminPassword), role: 'admin' },
      { id: 'u_demo', username: 'demo', passwordHash: hash('demo123'), role: 'user' },
    ];
  }

  async login(username: string, password: string) {
    this.store.cleanup();
    const user = await this.verifyCredential(username, password);
    const { accessToken, refreshToken, expiresIn } = await createSession(
      this.store, this.dbService, user, this.accessTtlSec, this.refreshTtlSec, this.jwtSecret,
    );
    return {
      user: await this.getProfile(user.id),
      accessToken,
      refreshToken,
      expiresIn,
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
      const passwordHash = hash(password);
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
        passwordHash: hash(password),
        role: 'user',
      });
    }

    return this.login(normalized, password);
  }

  async getProfile(userId: string) {
    const user = await this.findUserById(userId);
    const prefs = await this.preferencesService.getUserPreferences(userId);
    return this.buildProfile(user, prefs);
  }

  /** List users for admin panel (id, username, role, active, createdAt). */
  async listUsersForAdmin(): Promise<Array<{ id: string; username: string; role: Role; active: boolean; createdAt?: string }>> {
    if (this.dbService.enabled) {
      const result = await this.dbService.query<{
        id: string;
        username: string;
        role: string;
        active: boolean;
        created_at: Date;
      }>(
        `SELECT u.id, u.username, COALESCE(r.code, 'user') AS role, u.active, u.created_at
           FROM app_users u
      LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.active = TRUE
      LEFT JOIN roles r ON r.id = ur.role_id AND r.active = TRUE
          ORDER BY u.created_at DESC`,
      );
      return result.rows.map((row) => ({
        id: row.id,
        username: row.username,
        role: (row.role === 'admin' ? 'admin' : 'user') as Role,
        active: row.active,
        createdAt: new Date(row.created_at).toISOString(),
      }));
    }
    return this.users.map((u) => ({
      id: u.id,
      username: u.username,
      role: u.role,
      active: true,
    }));
  }

  async updateProfile(
    userId: string,
    updates: { riskLevel?: string; nickname?: string; avatarUrl?: string; preferences?: Record<string, unknown> },
  ) {
    const user = await this.findUserById(userId);
    const current = await this.preferencesService.getUserPreferences(userId);
    const next: Record<string, unknown> = { ...current, ...(updates.preferences ?? {}) };

    if (updates.riskLevel !== undefined) next.riskLevel = this.normalizeOptionalText(updates.riskLevel) ?? '稳健';
    if (updates.nickname !== undefined) {
      const nickname = this.normalizeOptionalText(updates.nickname);
      if (nickname) next.nickname = nickname;
      else delete next.nickname;
    }
    if (updates.avatarUrl !== undefined) {
      const avatarUrl = this.normalizeOptionalText(updates.avatarUrl);
      if (avatarUrl) next.avatarUrl = avatarUrl;
      else delete next.avatarUrl;
    }

    await this.preferencesService.setUserPreferences(userId, next);
    return this.buildProfile(user, next);
  }

  async changePassword(userId: string, oldPassword: string, newPassword: string) {
    const user = await this.findUserById(userId, true);
    if (user.passwordHash !== hash(oldPassword)) {
      throw new UnauthorizedException('旧密码错误');
    }
    const passwordHash = hash(newPassword);

    if (this.dbService.enabled) {
      await this.dbService.query('UPDATE app_users SET password_hash = $2 WHERE id = $1', [userId, passwordHash]);
      await this.dbService.query('UPDATE app_sessions SET revoked_at = NOW(), updated_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL', [userId]);
    } else {
      const current = this.users.find((item) => item.id === userId);
      if (!current) throw new UnauthorizedException('用户不存在');
      current.passwordHash = passwordHash;
      for (const [refresh, session] of this.store.sessionsByRefresh.entries()) {
        if (session.user.id !== userId) continue;
        this.store.accessJtiToRefresh.delete(session.accessJti);
        this.store.sessionsByRefresh.delete(refresh);
      }
    }

    return { success: true };
  }

  async listSessions(userId: string, currentAccessJti?: string) {
    return listSessions(this.store, this.dbService, userId, currentAccessJti);
  }

  async revokeSession(userId: string, sessionId: string, currentAccessJti?: string) {
    return revokeSession(this.store, this.dbService, userId, sessionId, currentAccessJti);
  }

  async refresh(refreshToken: string) {
    this.store.cleanup();
    const result = await refreshSession(this.store, this.dbService, refreshToken, this.accessTtlSec, this.jwtSecret);
    return {
      user: await this.getProfile(result.user.id),
      accessToken: result.accessToken,
      refreshToken: result.refreshToken,
      expiresIn: result.expiresIn,
    };
  }

  async logout(params: { accessToken?: string; refreshToken?: string }) {
    const { accessToken, refreshToken } = params;

    if (refreshToken) {
      await revokeByRefresh(this.store, this.dbService, refreshToken);
    }
    if (accessToken) {
      await revokeByAccess(this.store, this.dbService, accessToken, this.jwtSecret);
    }

    return { success: true };
  }

  async verifyAccessToken(accessToken: string) {
    this.store.cleanup();
    return verifyAccessTokenSession(this.store, this.dbService, accessToken, this.jwtSecret);
  }

  // ---------------------------------------------------------------------------
  // Private helpers (user lookup & profile building)
  // ---------------------------------------------------------------------------

  private async verifyCredential(username: string, password: string): Promise<{ id: string; username: string; role: Role }> {
    const normalized = username.trim();
    const passwordHash = hash(password);

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
        this.logger.debug(`Login debug for ${username}. found_id: ${row?.id}, db_hash: ${row?.password_hash}, input_hash: ${passwordHash}, matched: ${row?.password_hash === passwordHash}`);
        throw new UnauthorizedException('用户名或密码错误');
      }
      return { id: row.id, username: row.username, role: (row.role === 'admin' ? 'admin' : 'user') as Role };
    }

    const found = this.users.find((u) => u.username === normalized && u.passwordHash === passwordHash);
    if (!found) throw new UnauthorizedException('用户名或密码错误');
    return { id: found.id, username: found.username, role: found.role };
  }

  private async findUserById(userId: string, withPassword = false): Promise<AppUser> {
    if (this.dbService.enabled) {
      const found = await this.dbService.query<{ id: string; username: string; password_hash: string; role: string }>(
        `SELECT u.id, u.username, u.password_hash, COALESCE(r.code, 'user') AS role
           FROM app_users u
      LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.active = TRUE
      LEFT JOIN roles r ON r.id = ur.role_id AND r.active = TRUE
          WHERE u.id = $1 AND u.active = TRUE
          ORDER BY u.id
          LIMIT 1`,
        [userId],
      );
      const row = found.rows[0];
      if (!row) throw new UnauthorizedException('用户不存在');
      return {
        id: row.id,
        username: row.username,
        passwordHash: row.password_hash,
        role: (row.role === 'admin' ? 'admin' : 'user') as Role,
      };
    }

    const user = this.users.find((item) => item.id === userId);
    if (!user) throw new UnauthorizedException('用户不存在');
    if (withPassword) return user;
    return { ...user };
  }

  private buildProfile(user: { id: string; username: string; role: Role }, prefs: Record<string, unknown>) {
    const riskLevel = this.normalizeOptionalText(prefs.riskLevel) ?? '稳健';
    const nickname = this.normalizeOptionalText(prefs.nickname);
    const avatarUrl = this.normalizeOptionalText(prefs.avatarUrl);
    return {
      id: user.id,
      username: user.username,
      role: user.role,
      riskLevel,
      nickname: nickname ?? null,
      avatarUrl: avatarUrl ?? null,
      preferences: prefs,
    };
  }

  private normalizeOptionalText(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
}
