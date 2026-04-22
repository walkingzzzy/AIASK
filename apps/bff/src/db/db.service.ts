import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Pool, type PoolClient, type QueryResult, type QueryResultRow } from 'pg';
import { performance } from 'node:perf_hooks';
import { ObservabilityService } from '../observability/observability.service';

type DbFailureStage =
  | 'database_disabled'
  | 'db_connect_failed'
  | 'db_schema_not_ready'
  | 'db_pool_error'
  | 'db_query_failed';

const MCP_SCHEMA_OWNER = 'mcp' as const;
const APP_CORE_REQUIRED_MIGRATIONS = [
  '001_p0_auth_audit',
  '002_user_preferences',
  '003_unified_decision_diff_audit',
  '004_session_mfa_verified',
  '005_frontend_behavior_events',
] as const;

@Injectable()
export class DbService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(DbService.name);
  private pool: Pool | null = null;
  private _healthy = false;
  private lastError: string | null = null;
  private lastLatencyMs: number | null = null;
  private lastCheckedAt: string | null = null;
  private lastFailureStage: DbFailureStage | null = null;
  private schemaOwner = MCP_SCHEMA_OWNER;
  private schemaReady = false;
  private schemaTrackingTablePresent = false;
  private schemaAppliedKeys: string[] = [];
  private schemaMissingKeys: string[] = [...APP_CORE_REQUIRED_MIGRATIONS];
  private schemaCheckedAt: string | null = null;

  constructor(
    private readonly configService: ConfigService,
    private readonly observability: ObservabilityService,
  ) {
    const url = this.configService.get<string>('DATABASE_URL', '').trim();
    if (!url) {
      this.logger.warn('未配置 DATABASE_URL，数据库持久化能力已禁用（回退内存模式）');
      this.lastFailureStage = 'database_disabled';
      this.observability.setDependencyState('postgres', 'degraded');
      return;
    }

    const max = Math.max(1, Number(this.configService.get<string>('DATABASE_POOL_MAX', '10')));
    const idleTimeoutMillis = Math.max(1000, Number(this.configService.get<string>('DATABASE_POOL_IDLE_TIMEOUT_MS', '30000')));
    const connectionTimeoutMillis = Math.max(500, Number(this.configService.get<string>('DATABASE_POOL_CONNECTION_TIMEOUT_MS', '5000')));
    const maxUses = Math.max(0, Number(this.configService.get<string>('DATABASE_POOL_MAX_USES', '0')));
    const applicationName = this.configService.get<string>('DATABASE_POOL_APP_NAME', 'aiask-bff');

    this.pool = new Pool({
      connectionString: url,
      max,
      idleTimeoutMillis,
      connectionTimeoutMillis,
      application_name: applicationName,
      ...(maxUses > 0 ? { maxUses } : {}),
    });
    this.logger.log(
      `PostgreSQL 连接池已配置 max=${max}, idleTimeout=${idleTimeoutMillis}ms, connectTimeout=${connectionTimeoutMillis}ms${maxUses > 0 ? `, maxUses=${maxUses}` : ''}`,
    );
    this.pool.on('error', (error: Error) => {
      this.logger.error(`PostgreSQL 连接池错误: ${error.message}`);
      this._healthy = false;
      this.lastError = error.message;
      this.lastCheckedAt = new Date().toISOString();
      this.lastFailureStage = 'db_pool_error';
      this.observability.setDependencyState('postgres', false);
    });
  }

  get enabled(): boolean {
    return !!this.pool;
  }

  get healthy(): boolean {
    return this._healthy;
  }

  getHealthSnapshot() {
    return {
      enabled: this.enabled,
      healthy: this._healthy,
      lastError: this.lastError,
      lastLatencyMs: this.lastLatencyMs,
      lastCheckedAt: this.lastCheckedAt,
      lastFailureStage: this.lastFailureStage,
      schemaOwner: this.schemaOwner,
      schemaReady: this.schemaReady,
      schemaTrackingTablePresent: this.schemaTrackingTablePresent,
      schemaAppliedKeys: this.schemaAppliedKeys,
      schemaMissingKeys: this.schemaMissingKeys,
      schemaCheckedAt: this.schemaCheckedAt,
    };
  }

  async onModuleInit(): Promise<void> {
    if (!this.pool) return;

    // 1. 连通性检查
    try {
      const startedAt = performance.now();
      await this.pool.query('SELECT 1');
      this.logger.log('✓ 数据库连接正常');
      this.lastError = null;
      this.lastLatencyMs = Number((performance.now() - startedAt).toFixed(2));
      this.lastCheckedAt = new Date().toISOString();
      this.lastFailureStage = null;
      this.observability.setDependencyState('postgres', true);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.logger.error(`✗ 数据库连接失败: ${msg}`);
      this._healthy = false;
      this.lastError = msg;
      this.lastLatencyMs = null;
      this.lastCheckedAt = new Date().toISOString();
      this.lastFailureStage = 'db_connect_failed';
      this.observability.setDependencyState('postgres', false);
      return;
    }

    try {
      await this.verifySchemaReadiness();
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.logger.error(`✗ MCP schema readiness 检查失败: ${msg}`);
      this._healthy = false;
      this.lastError = msg;
      this.lastCheckedAt = new Date().toISOString();
      this.lastFailureStage = 'db_schema_not_ready';
      this.observability.setDependencyState('postgres', false);
    }
  }

  private async verifySchemaReadiness(): Promise<void> {
    if (!this.pool) return;
    const checkedAt = new Date().toISOString();
    const tableResult = await this.pool.query<{ present: boolean }>(
      "SELECT to_regclass('public.mcp_schema_migrations') IS NOT NULL AS present",
    );
    const trackingTablePresent = Boolean(tableResult.rows[0]?.present);
    this.schemaTrackingTablePresent = trackingTablePresent;
    this.schemaCheckedAt = checkedAt;

    if (!trackingTablePresent) {
      this.schemaAppliedKeys = [];
      this.schemaMissingKeys = [...APP_CORE_REQUIRED_MIGRATIONS];
      this.schemaReady = false;
      this._healthy = false;
      this.lastError = 'MCP schema migration tracking table is missing';
      this.lastFailureStage = 'db_schema_not_ready';
      this.lastCheckedAt = checkedAt;
      this.observability.setDependencyState('postgres', 'degraded');
      this.logger.warn('✗ MCP schema migration tracking table 缺失，BFF 保持只读 readiness 检查模式');
      return;
    }

    const rows = await this.pool.query<{ migration_key: string }>(
      `SELECT migration_key
         FROM mcp_schema_migrations
        WHERE namespace = $1
        ORDER BY migration_key ASC`,
      ['app_core'],
    );
    this.schemaAppliedKeys = rows.rows.map((row) => String(row.migration_key));
    this.schemaMissingKeys = APP_CORE_REQUIRED_MIGRATIONS
      .filter((key) => !this.schemaAppliedKeys.includes(key));
    this.schemaReady = this.schemaMissingKeys.length === 0;
    this._healthy = this.schemaReady;
    this.lastCheckedAt = checkedAt;
    this.lastFailureStage = this.schemaReady ? null : 'db_schema_not_ready';
    this.lastError = this.schemaReady
      ? null
      : `MCP schema not ready, missing keys: ${this.schemaMissingKeys.join(', ')}`;
    this.observability.setDependencyState('postgres', this.schemaReady ? 'normal' : 'degraded');
    if (this.schemaReady) {
      this.logger.log('✓ MCP schema readiness 校验通过，BFF 仅执行连接与 readiness 检查');
      return;
    }
    this.logger.warn(`✗ MCP schema readiness 未通过，缺少 migration keys: ${this.schemaMissingKeys.join(', ')}`);
  }

  async query<T extends QueryResultRow = QueryResultRow>(
    sql: string,
    params: unknown[] = [],
  ): Promise<QueryResult<T>> {
    if (!this.pool) {
      throw new Error('DATABASE_DISABLED');
    }
    const startedAt = performance.now();
    try {
      const result = await this.pool.query<T>(sql, params);
      this._healthy = this.schemaReady;
      this.lastError = this.schemaReady ? null : this.lastError;
      this.lastLatencyMs = Number((performance.now() - startedAt).toFixed(2));
      this.lastCheckedAt = new Date().toISOString();
      this.lastFailureStage = this.schemaReady ? null : 'db_schema_not_ready';
      this.observability.recordDbQuery({
        operation: sql.split(/\s+/)[0] || 'query',
        durationMs: performance.now() - startedAt,
        errored: false,
      });
      this.observability.setDependencyState('postgres', this.schemaReady ? 'normal' : 'degraded');
      return result;
    } catch (error) {
      this.observability.recordDbQuery({
        operation: sql.split(/\s+/)[0] || 'query',
        durationMs: performance.now() - startedAt,
        errored: true,
      });
      this._healthy = false;
      this.lastError = error instanceof Error ? error.message : String(error);
      this.lastLatencyMs = Number((performance.now() - startedAt).toFixed(2));
      this.lastCheckedAt = new Date().toISOString();
      this.lastFailureStage = 'db_query_failed';
      this.observability.setDependencyState('postgres', false);
      throw error;
    }
  }

  async withClient<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
    if (!this.pool) {
      throw new Error('DATABASE_DISABLED');
    }

    const client = await this.pool.connect();
    try {
      return await fn(client);
    } finally {
      client.release();
    }
  }

  async tx<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
    return this.withClient(async (client) => {
      await client.query('BEGIN');
      try {
        const result = await fn(client);
        await client.query('COMMIT');
        return result;
      } catch (error) {
        await client.query('ROLLBACK');
        throw error;
      }
    });
  }

  async onModuleDestroy(): Promise<void> {
    if (!this.pool) return;
    await this.pool.end();
  }
}
