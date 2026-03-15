import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Pool, type PoolClient, type QueryResult, type QueryResultRow } from 'pg';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

@Injectable()
export class DbService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(DbService.name);
  private pool: Pool | null = null;
  private _healthy = false;

  constructor(private readonly configService: ConfigService) {
    const url = this.configService.get<string>('DATABASE_URL', '').trim();
    if (!url) {
      this.logger.warn('未配置 DATABASE_URL，数据库持久化能力已禁用（回退内存模式）');
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
    });
  }

  get enabled(): boolean {
    return !!this.pool;
  }

  get healthy(): boolean {
    return this._healthy;
  }

  // ------------------------------------------------------------------
  // Lifecycle: 启动时自动校验 + 迁移
  // ------------------------------------------------------------------
  async onModuleInit(): Promise<void> {
    if (!this.pool) return;

    // 1. 连通性检查
    try {
      await this.pool.query('SELECT 1');
      this.logger.log('✓ 数据库连接正常');
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.logger.error(`✗ 数据库连接失败: ${msg}`);
      return;
    }

    // 2. 自动执行迁移
    try {
      await this.runMigrations();
      this._healthy = true;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.logger.error(`✗ 数据库迁移失败: ${msg}`);
      // 迁移失败仍标记为 unhealthy 但不阻塞启动
    }
  }

  // ------------------------------------------------------------------
  // 自动迁移（复用 migrate.mjs 逻辑）
  // ------------------------------------------------------------------
  private async runMigrations(): Promise<void> {
    if (!this.pool) return;

    const migrationsDir = join(__dirname, '..', '..', 'migrations');

    // 确保迁移记录表存在
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS app_schema_migrations (
        id BIGSERIAL PRIMARY KEY,
        filename VARCHAR(255) NOT NULL UNIQUE,
        checksum VARCHAR(64) NOT NULL,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    `);

    let files: string[];
    try {
      files = (await readdir(migrationsDir))
        .filter((name) => name.toLowerCase().endsWith('.sql'))
        .sort((a, b) => a.localeCompare(b));
    } catch {
      this.logger.log('迁移目录不存在或不可读，跳过自动迁移');
      return;
    }

    if (!files.length) {
      this.logger.log('无待执行的迁移文件');
      return;
    }

    for (const file of files) {
      const full = join(migrationsDir, file);
      const sql = await readFile(full, 'utf8');
      const checksum = createHash('sha256').update(sql).digest('hex');

      const existing = await this.pool.query(
        'SELECT checksum FROM app_schema_migrations WHERE filename = $1 LIMIT 1',
        [file],
      );

      if (existing.rowCount && existing.rows[0].checksum === checksum) {
        continue; // 已执行且内容未变
      }

      if (existing.rowCount && existing.rows[0].checksum !== checksum) {
        this.logger.error(`迁移文件已变更: ${file}，请创建新迁移文件`);
        throw new Error(`Migration checksum mismatch: ${file}`);
      }

      this.logger.log(`执行迁移: ${file}`);
      const client = await this.pool.connect();
      try {
        await client.query('BEGIN');
        await client.query(sql);
        await client.query(
          'INSERT INTO app_schema_migrations (filename, checksum) VALUES ($1, $2)',
          [file, checksum],
        );
        await client.query('COMMIT');
      } catch (error) {
        await client.query('ROLLBACK');
        throw error;
      } finally {
        client.release();
      }
    }

    this.logger.log('✓ 数据库迁移完成');
  }

  async query<T extends QueryResultRow = QueryResultRow>(
    sql: string,
    params: unknown[] = [],
  ): Promise<QueryResult<T>> {
    if (!this.pool) {
      throw new Error('DATABASE_DISABLED');
    }
    return this.pool.query<T>(sql, params);
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

