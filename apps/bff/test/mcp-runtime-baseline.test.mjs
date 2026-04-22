import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function readExpectedTools(envPath) {
  const text = readFileSync(envPath, 'utf8');
  const match = text.match(/^MCP_EXPECTED_TOOLS=(\d+)$/m);
  assert.ok(match, `Missing MCP_EXPECTED_TOOLS in ${envPath}`);
  return Number(match[1]);
}

test('MCP expected tools baseline matches runtime registry export', () => {
  const repoRoot = resolve(import.meta.dirname, '..', '..', '..');
  const envExamplePath = resolve(repoRoot, 'apps/bff/.env.example');
  const envPath = resolve(repoRoot, 'apps/bff/.env');
  const pythonPath = resolve(repoRoot, 'packages/akshare-mcp/.venv/bin/python');

  const expectedFromExample = readExpectedTools(envExamplePath);
  assert.equal(expectedFromExample, 161);

  if (existsSync(envPath)) {
    const expectedFromEnv = readExpectedTools(envPath);
    assert.equal(expectedFromEnv, expectedFromExample);
  }

  assert.ok(existsSync(pythonPath), `Missing Python runtime: ${pythonPath}`);
  const output = execFileSync(
    pythonPath,
    [
      '-c',
      [
        'import json, sys',
        `sys.path.insert(0, ${JSON.stringify(resolve(repoRoot, 'packages/akshare-mcp/src'))})`,
        'from akshare_mcp.tool_registry import build_tool_registry, summarize_tool_registry',
        'summary = summarize_tool_registry(build_tool_registry())',
        'print(json.dumps(summary, ensure_ascii=False))',
      ].join('; '),
    ],
    {
      cwd: repoRoot,
      encoding: 'utf8',
    },
  );
  const summary = JSON.parse(output);
  assert.equal(Number(summary.tool_count ?? 0), expectedFromExample);
});
