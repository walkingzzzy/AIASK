import fs from 'node:fs/promises';
import path from 'node:path';

import { ensureDir } from './browser-common.mjs';
import { runCommand } from './process-common.mjs';

function parseArgs(argv) {
  const args = {
    outputDir: null,
    metadataPath: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--metadata' && argv[index + 1]) {
      args.metadataPath = path.resolve(argv[index + 1]);
      index += 1;
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const metadataPath = args.metadataPath || path.join(args.outputDir, 'raw', 'env-snapshot.json');
  const metadata = JSON.parse(await fs.readFile(metadataPath, 'utf8'));
  const restorePath = path.join(args.outputDir, 'raw', 'env-restore.json');
  const rawDir = await ensureDir(path.join(args.outputDir, 'raw'));
  const remoteDumpPath = metadata.postgres.remoteDumpPath || '/tmp/frontend-audit-postgres.dump';
  const localListPath = path.join(rawDir, 'env-restore.list');
  const remoteListPath = '/tmp/frontend-audit-postgres.list';
  const redisSnapshotDir = metadata.redis.snapshotDir;
  const redisCopySource = await fs
    .access(path.join(redisSnapshotDir, 'dump.rdb'))
    .then(() => redisSnapshotDir)
    .catch(async () => {
      const nested = path.join(redisSnapshotDir, 'data');
      await fs.access(nested);
      return nested;
    });

  await runCommand('docker', ['cp', metadata.postgres.dumpPath, `${metadata.postgres.container}:${remoteDumpPath}`]);
  const listOutput = await runCommand('docker', [
    'exec',
    metadata.postgres.container,
    'sh',
    '-lc',
    `pg_restore -l '${remoteDumpPath}'`,
  ]);
  const filteredList = listOutput.stdout
    .split(/\r?\n/)
    .filter(
      (line) =>
        !/EXTENSION - timescaledb|COMMENT - EXTENSION timescaledb/i.test(line) &&
        !/TABLE DATA public audit_logs|SEQUENCE SET public audit_logs_id_seq/i.test(line),
    )
    .join('\n');
  await fs.writeFile(localListPath, `${filteredList}\n`, 'utf8');
  await runCommand('docker', ['cp', localListPath, `${metadata.postgres.container}:${remoteListPath}`]);
  let restoreWarnings = '';
  try {
    await runCommand('docker', [
      'exec',
      metadata.postgres.container,
      'sh',
      '-lc',
      [
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' psql -U '${metadata.postgres.username}' -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${metadata.postgres.database}' AND pid <> pg_backend_pid();"`,
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' dropdb -U '${metadata.postgres.username}' --if-exists '${metadata.postgres.database}'`,
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' createdb -U '${metadata.postgres.username}' '${metadata.postgres.database}'`,
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' psql -X -U '${metadata.postgres.username}' -d '${metadata.postgres.database}' -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"`,
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' psql -X -U '${metadata.postgres.username}' -d '${metadata.postgres.database}' -c "SELECT timescaledb_pre_restore();"`,
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' pg_restore --clean --if-exists --no-owner --no-privileges --use-list '${remoteListPath}' -U '${metadata.postgres.username}' -d '${metadata.postgres.database}' '${remoteDumpPath}'`,
        `PGPASSWORD='${(metadata.postgres.password || 'postgres').replace(/'/g, "'\\''")}' psql -X -U '${metadata.postgres.username}' -d '${metadata.postgres.database}' -c "SELECT timescaledb_post_restore();"`,
        `rm -f '${remoteDumpPath}' '${remoteListPath}'`,
      ].join(' && '),
    ]);
  } catch (error) {
    const stderr = error?.result?.stderr || error?.message || String(error);
    if (!/errors ignored on restore/i.test(stderr)) {
      throw error;
    }
    restoreWarnings = stderr;
  }

  await runCommand('docker', [
    'exec',
    metadata.redis.container,
    'sh',
    '-lc',
    "redis-cli FLUSHALL >/dev/null 2>&1 || true; rm -rf /data/* /data/.[!.]* /data/..?* || true",
  ]);
  await runCommand('docker', ['cp', `${redisCopySource}/.`, `${metadata.redis.container}:/data`]);
  await runCommand('docker', ['restart', metadata.redis.container]);

  await runCommand('docker', [
    'exec',
    metadata.postgres.container,
    'sh',
    '-lc',
    `pg_isready -U '${metadata.postgres.username}' -d '${metadata.postgres.database}'`,
  ]);
  await runCommand('docker', [
    'exec',
    metadata.redis.container,
    'sh',
    '-lc',
    `redis-cli -a '${(metadata.redis.password || 'redis_secret').replace(/'/g, "'\\''")}' PING`,
  ]);

  const restoreInfo = {
    restoredAt: new Date().toISOString(),
    metadataPath,
    postgres: {
      container: metadata.postgres.container,
      database: metadata.postgres.database,
      dumpPath: metadata.postgres.dumpPath,
      status: restoreWarnings ? 'restored_with_warnings' : 'restored',
      warnings: restoreWarnings || null,
    },
    redis: {
      container: metadata.redis.container,
      snapshotDir: metadata.redis.snapshotDir,
      status: 'restored',
    },
  };

  await fs.writeFile(path.join(rawDir, path.basename(restorePath)), JSON.stringify(restoreInfo, null, 2), 'utf8');
  process.stdout.write(`${restorePath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
