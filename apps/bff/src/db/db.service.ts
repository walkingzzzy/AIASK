import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Pool, type PoolClient, type QueryResult, type QueryResultRow } from 'pg';

@Injectable()
export class DbService implements OnModuleDestroy {
  private readonly logger = new Logger(DbService.name);
  private pool: Pool | null = null;

  constructor(private readonly configService: ConfigService) {
    const url = this.configService.get<string>('DATABASE_URL', '').trim();
    if (!url) {
      this.logger.warn('未配置 DATABASE_URL，数据库持久化能力已禁用（回退内存模式）');
      return;
    }

    this.pool = new Pool({ connectionString: url, max: 10 });
    this.pool.on('error', (error: Error) => {
      this.logger.error(`PostgreSQL 连接池错误: ${error.message}`);
    });
  }

  get enabled(): boolean {
    return !!this.pool;
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

