import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const { AdminService } = await import('../dist/admin/admin.service.js');

function createService(callTool) {
  return new AdminService(
    {
      callTool,
    },
    {},
    {},
  );
}

async function withTempRepo(run) {
  const originalCwd = process.cwd();
  const tempRoot = await mkdtemp(join(tmpdir(), 'aiask-admin-dead-letters-'));
  const appCwd = join(tempRoot, 'apps', 'bff');
  await mkdir(appCwd, { recursive: true });
  process.chdir(appCwd);
  try {
    await run({ tempRoot, appCwd });
  } finally {
    process.chdir(originalCwd);
    await rm(tempRoot, { recursive: true, force: true });
  }
}

test('AdminService.getDeadLetters falls back to local dead letter file when MCP returns empty', async () => {
  await withTempRepo(async ({ tempRoot }) => {
    const file = join(tempRoot, 'packages', 'akshare-mcp', '.mcp_cache', 'dead_letters', 'kline_save_failures.jsonl');
    await mkdir(join(file, '..'), { recursive: true });
    await writeFile(
      file,
      `${JSON.stringify({
        id: 'pw-audit-dead-letter-1',
        stock_code: '600519',
        retry: 3,
        failed_at: 1778145168,
        error: 'sample',
      })}\n`,
      'utf-8',
    );
    const service = createService(async () => ({
      records: [],
      path: '.mcp_cache/dead_letters/kline_save_failures.jsonl',
      count: 0,
    }));

    const result = await service.getDeadLetters();

    assert.equal(result.count, 1);
    assert.equal(result.items.length, 1);
    assert.equal(result.path, '.mcp_cache/dead_letters/kline_save_failures.jsonl');
    assert.equal(result.items[0].id, 'pw-audit-dead-letter-1');
    assert.equal(result.items[0].retries, 3);
  });
});

test('AdminService.clearDeadLetters removes local fallback dead letter files when MCP remove count is empty', async () => {
  await withTempRepo(async ({ tempRoot }) => {
    const file = join(tempRoot, 'packages', 'akshare-mcp', '.mcp_cache', 'dead_letters', 'kline_save_failures.jsonl');
    await mkdir(join(file, '..'), { recursive: true });
    await writeFile(
      file,
      [
        JSON.stringify({ id: 'pw-audit-dead-letter-1', stock_code: '600519', retry: 3, failed_at: 1778145168, error: 'sample-a' }),
        JSON.stringify({ id: 'pw-audit-dead-letter-2', stock_code: '000001', retry: 1, failed_at: 1778145228, error: 'sample-b' }),
      ].join('\n') + '\n',
      'utf-8',
    );
    const service = createService(async (name) => {
      if (name === 'get_dead_letters') {
        return {
          records: [],
          path: '.mcp_cache/dead_letters/kline_save_failures.jsonl',
          count: 0,
        };
      }
      if (name === 'clear_dead_letters') {
        return { removed: 0 };
      }
      throw new Error(`unexpected tool ${name}`);
    });

    const result = await service.clearDeadLetters();

    assert.equal(result.removed, 2);
    assert.equal(existsSync(file), false);
  });
});
