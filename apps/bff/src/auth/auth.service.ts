import { ConflictException, Injectable, Logger, OnModuleInit, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { randomUUID } from 'crypto';
import { DbService } from '../db/db.service';
import { PreferencesService } from './preferences.service';
import type { AppUser, Role } from './auth.types';
import {
  hashPassword,
  hashPasswordSync,
  isLegacyPasswordHash,
  verifyPassword,
} from './jwt.service';
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
export class AuthService implements OnModuleInit {
  private static readonly DEFAULT_JWT_SECRET = 'dev-secret-change-me';
  private static readonly DEFAULT_ADMIN_PASSWORD = 'admin';
  private static readonly DEFAULT_DEMO_PASSWORD = 'demo123';

  private readonly logger = new Logger(AuthService.name);
  private readonly accessTtlSec: number;
  private readonly refreshTtlSec: number;
  private readonly jwtSecret: string;
  private readonly adminPassword: string;
  private readonly demoPassword: string;
  private readonly demoUserEnabled: boolean;

  private readonly users: AppUser[];
  private readonly store = new SessionStore();

  constructor(
    private readonly configService: ConfigService,
    private readonly dbService: DbService,
    private readonly preferencesService: PreferencesService,
  ) {
    this.accessTtlSec = Math.max(60, Number(this.configService.get('APP_ACCESS_TOKEN_TTL_SECONDS', 7200)));
    this.refreshTtlSec = Math.max(300, Number(this.configService.get('APP_REFRESH_TOKEN_TTL_SECONDS', 604800)));
    this.jwtSecret = this.configService.get<string>('APP_JWT_SECRET', AuthService.DEFAULT_JWT_SECRET);

    this.adminPassword = this.configService.get<string>('APP_ADMIN_PASSWORD', AuthService.DEFAULT_ADMIN_PASSWORD);
    this.demoPassword = this.configService.get<string>('APP_DEMO_PASSWORD', AuthService.DEFAULT_DEMO_PASSWORD);
    const isProduction = this.isProductionEnv();
    this.demoUserEnabled = this.readBooleanConfig('APP_ENABLE_DEMO_USER', !isProduction);

    if (this.isWeakJwtSecret(this.jwtSecret)) {
      if (isProduction) {
        throw new Error('APP_JWT_SECRET 不能在生产环境中使用默认值或弱密钥');
      }
      this.logger.warn('APP_JWT_SECRET 使用默认值或弱密钥，仅适合本地开发环境');
    }

    if (isProduction && this.isWeakAdminPassword(this.adminPassword)) {
      throw new Error('APP_ADMIN_PASSWORD 不能在生产环境中使用默认值或弱密码');
    }
    if (isProduction && this.demoUserEnabled) {
      throw new Error('生产环境默认禁用 demo 用户，请设置 APP_ENABLE_DEMO_USER=false');
    }

    const users: AppUser[] = [
      { id: 'u_admin', username: 'admin', passwordHash: hashPasswordSync(this.adminPassword), role: 'admin' },
    ];
    if (this.demoUserEnabled) {
      users.push({
        id: 'u_demo',
        username: 'demo',
        passwordHash: hashPasswordSync(this.demoPassword),
        role: 'user',
      });
    }
    this.users = users;
  }

  async onModuleInit(): Promise<void> {
    if (!this.dbService.enabled) {
      return;
    }
    await this.hardenSeedUsers();
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
      const passwordHash = await hashPassword(password);
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
        passwordHash: await hashPassword(password),
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
    if (!(await verifyPassword(oldPassword, user.passwordHash))) {
      throw new UnauthorizedException('旧密码错误');
    }
    const passwordHash = await hashPassword(newPassword);

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
      if (!row || !(await verifyPassword(password, row.password_hash))) {
        throw new UnauthorizedException('用户名或密码错误');
      }
      await this.upgradeLegacyPasswordHashIfNeeded(row.id, row.password_hash, password);
      return { id: row.id, username: row.username, role: (row.role === 'admin' ? 'admin' : 'user') as Role };
    }

    const found = this.users.find((u) => u.username === normalized);
    if (!found || !(await verifyPassword(password, found.passwordHash))) {
      throw new UnauthorizedException('用户名或密码错误');
    }
    if (isLegacyPasswordHash(found.passwordHash)) {
      found.passwordHash = await hashPassword(password);
    }
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

  private isProductionEnv(): boolean {
    return String(this.configService.get<string>('NODE_ENV', process.env.NODE_ENV ?? 'development')).trim().toLowerCase() === 'production';
  }

  private readBooleanConfig(key: string, fallback: boolean): boolean {
    const raw = String(this.configService.get<string>(key, fallback ? 'true' : 'false')).trim().toLowerCase();
    if (['1', 'true', 'yes', 'y', 'on'].includes(raw)) return true;
    if (['0', 'false', 'no', 'n', 'off'].includes(raw)) return false;
    return fallback;
  }

  private isWeakJwtSecret(secret: string): boolean {
    const normalized = String(secret || '').trim();
    return !normalized || normalized === AuthService.DEFAULT_JWT_SECRET || normalized.length < 32;
  }

  private isWeakAdminPassword(password: string): boolean {
    const normalized = String(password || '').trim();
    return !normalized || normalized === AuthService.DEFAULT_ADMIN_PASSWORD || normalized.length < 12;
  }

  private async upgradeLegacyPasswordHashIfNeeded(userId: string, currentHash: string, password: string): Promise<void> {
    if (!isLegacyPasswordHash(currentHash)) {
      return;
    }

    try {
      const upgradedHash = await hashPassword(password);
      await this.dbService.query('UPDATE app_users SET password_hash = $2 WHERE id = $1', [userId, upgradedHash]);
      this.logger.log(`已将用户 ${userId} 的旧版密码哈希升级为 scrypt`);
    } catch (error) {
      this.logger.warn(`升级用户 ${userId} 的旧版密码哈希失败: ${String(error)}`);
    }
  }

  private async hardenSeedUsers(): Promise<void> {
    try {
      const result = await this.dbService.query<{
        id: string;
        username: string;
        password_hash: string;
        active: boolean;
      }>(
        `SELECT id, username, password_hash, active
           FROM app_users
          WHERE username = ANY($1::text[])`,
        [['admin', 'demo']],
      );

      for (const row of result.rows) {
        if (row.username === 'admin') {
          const usesDefaultAdminPassword = await verifyPassword(AuthService.DEFAULT_ADMIN_PASSWORD, row.password_hash);
          if (usesDefaultAdminPassword && this.adminPassword !== AuthService.DEFAULT_ADMIN_PASSWORD) {
            await this.dbService.query(
              'UPDATE app_users SET password_hash = $2 WHERE id = $1',
              [row.id, await hashPassword(this.adminPassword)],
            );
            this.logger.warn('检测到数据库中的 admin 账户仍使用默认密码，已按 APP_ADMIN_PASSWORD 自动升级');
          }
        }

        if (row.username === 'demo' && row.active && !this.demoUserEnabled) {
          await this.dbService.query('UPDATE app_users SET active = FALSE WHERE id = $1', [row.id]);
          this.logger.warn('已自动停用数据库中的 demo 账户');
        }
      }
    } catch (error) {
      this.logger.warn(`启动时检查默认账户失败: ${String(error)}`);
    }
  }
}
