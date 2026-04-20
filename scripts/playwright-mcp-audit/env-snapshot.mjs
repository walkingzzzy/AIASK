import fs from 'node:fs/promises';
import path from 'node:path';

import { ensureDir, readEnvFile } from './browser-common.mjs';
import { runCommand } from './process-common.mjs';

function parseArgs(argv) {
  const args = {
    outputDir: null,
    postgresContainer: process.env.PW_AUDIT_PG_CONTAINER || 'akshare-timescaledb',
    redisContainer: process.env.PW_AUDIT_REDIS_CONTAINER || 'aiask-redis',
    envFile: path.join(process.cwd(), '.env'),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--postgres-container' && argv[index + 1]) {
      args.postgresContainer = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--redis-container' && argv[index + 1]) {
      args.redisContainer = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--env-file' && argv[index + 1]) {
      args.envFile = path.resolve(argv[index + 1]);
      index += 1;
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

function parseDatabaseUrl(databaseUrl) {
  const url = new URL(databaseUrl);
  return {
    username: decodeURIComponent(url.username || 'postgres'),
    password: decodeURIComponent(url.password || ''),
    database: decodeURIComponent(url.pathname.replace(/^\//, '') || 'postgres'),
    host: url.hostname,
    port: url.port || '5432',
  };
}

function parseRedisUrl(redisUrl) {
  const url = new URL(redisUrl);
  return {
    password: decodeURIComponent(url.password || ''),
    host: url.hostname,
    port: url.port || '6379',
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const envValues = await readEnvFile(args.envFile);
  const db = parseDatabaseUrl(envValues.DATABASE_URL || 'postgresql://postgres:postgres@127.0.0.1:5432/stockdb');
  const redis = parseRedisUrl(envValues.REDIS_URL || 'redis://:redis_secret@127.0.0.1:6379');
  const rawDir = await ensureDir(path.join(args.outputDir, 'raw'));
  const envDir = await ensureDir(path.join(rawDir, 'env'));
  const postgresDumpPath = path.join(envDir, 'postgres.dump');
  const redisSnapshotDir = path.join(envDir, 'redis-data');
  const metadataPath = path.join(rawDir, 'env-snapshot.json');
  const remoteDumpPath = '/tmp/frontend-audit-postgres.dump';

  await fs.rm(postgresDumpPath, { force: true }).catch(() => {});
  await fs.rm(redisSnapshotDir, { recursive: true, force: true }).catch(() => {});

  await runCommand('docker', [
    'exec',
    args.postgresContainer,
    'sh',
    '-lc',
    `PGPASSWORD='${db.password.replace(/'/g, "'\\''")}' pg_dump -Fc -U '${db.username}' -d '${db.database}' -f '${remoteDumpPath}'`,
  ]);
  await runCommand('docker', ['cp', `${args.postgresContainer}:${remoteDumpPath}`, postgresDumpPath]);
  await runCommand('docker', ['exec', args.postgresContainer, 'rm', '-f', remoteDumpPath], { allowFailure: true });

  await runCommand('docker', [
    'exec',
    args.redisContainer,
    'sh',
    '-lc',
    `redis-cli -a '${redis.password.replace(/'/g, "'\\''")}' SAVE`,
  ]);
  await runCommand('docker', ['cp', `${args.redisContainer}:/data`, redisSnapshotDir]);

  const metadata = {
    generatedAt: new Date().toISOString(),
    postgres: {
      container: args.postgresContainer,
      dumpPath: postgresDumpPath,
      remoteDumpPath,
      database: db.database,
      host: db.host,
      port: db.port,
      username: db.username,
      password: db.password,
    },
    redis: {
      container: args.redisContainer,
      snapshotDir: redisSnapshotDir,
      host: redis.host,
      port: redis.port,
      password: redis.password,
    },
  };

  await fs.writeFile(metadataPath, JSON.stringify(metadata, null, 2), 'utf8');
  process.stdout.write(`${metadataPath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
