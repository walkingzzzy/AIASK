import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { Pool } from 'pg';

const databaseUrl = (process.env.DATABASE_URL || '').trim();
if (!databaseUrl) {
  console.error('[migrate] 缺少 DATABASE_URL，无法执行迁移');
  process.exit(1);
}

const migrationsDir = join(process.cwd(), 'migrations');
const pool = new Pool({ connectionString: databaseUrl });

async function ensureSchemaTable() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS app_schema_migrations (
      id BIGSERIAL PRIMARY KEY,
      filename VARCHAR(255) NOT NULL UNIQUE,
      checksum VARCHAR(64) NOT NULL,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
}

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  console.log(`[migrate] start${dryRun ? ' (dry-run)' : ''}`);

  await ensureSchemaTable();

  const files = (await readdir(migrationsDir))
    .filter((name) => name.toLowerCase().endsWith('.sql'))
    .sort((a, b) => a.localeCompare(b));

  if (!files.length) {
    console.log('[migrate] 未找到 SQL 迁移文件，已完成');
    return;
  }

  for (const file of files) {
    const full = join(migrationsDir, file);
    const sql = await readFile(full, 'utf8');
    const checksum = sha256(sql);

    const existing = await pool.query(
      'SELECT checksum FROM app_schema_migrations WHERE filename = $1 LIMIT 1',
      [file],
    );

    if (existing.rowCount && existing.rows[0].checksum === checksum) {
      console.log(`[migrate] 跳过 ${file}（已执行）`);
      continue;
    }

    if (existing.rowCount && existing.rows[0].checksum !== checksum) {
      throw new Error(`迁移文件已执行且内容发生变化: ${file}，请创建新迁移文件`);
    }

    if (dryRun) {
      console.log(`[migrate] 计划执行 ${file}`);
      continue;
    }

    console.log(`[migrate] 执行 ${file}`);
    const client = await pool.connect();
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

  console.log('[migrate] done');
}

main()
  .catch((error) => {
    console.error('[migrate] failed:', error?.message || error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await pool.end();
  });

