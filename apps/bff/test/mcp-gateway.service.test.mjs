import test from 'node:test';
import assert from 'node:assert/strict';
import { delimiter, resolve } from 'node:path';

const { buildIsolatedPythonPath } = await import('../dist/mcp-gateway/mcp-gateway.service.js');

test('buildIsolatedPythonPath ignores ambient PYTHONPATH and keeps only configured plus repo roots', () => {
  const cwd = '/repo/packages/akshare-mcp';
  const configured = ['relative-extra', '/repo/packages/akshare-mcp/src'].join(delimiter);
  const ambient = [
    '/repo/.claude/worktrees/agent-aec932a8/packages/akshare-mcp/src',
    '/tmp/foreign-pythonpath',
  ].join(delimiter);
  const value = buildIsolatedPythonPath({
    cwd,
    configured,
    ambient,
    exists: () => true,
  });

  assert.deepEqual(value.split(delimiter), [
    resolve(cwd, 'relative-extra'),
    resolve(cwd, 'src'),
    resolve(cwd, '..', 'strategy-factory', 'src'),
  ]);
});
