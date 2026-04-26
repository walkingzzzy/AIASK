import test from 'node:test';
import assert from 'node:assert/strict';

const { buildStrategyCapabilityDiagnostics } = await import('../dist/strategy/strategy-capability-diagnostics.js');
const { STRATEGY_MANAGER_ACTIONS } = await import('@aiask/shared-types');

function byId(diagnostics) {
  return new Map(diagnostics.items.map((item) => [item.id, item]));
}

test('strategy capability diagnostics builds a four-layer gap table', () => {
  const diagnostics = buildStrategyCapabilityDiagnostics({
    generatedAt: '2026-04-24T00:00:00.000Z',
    mcpRuntime: {
      reachable: true,
      toolCount: 88,
      expectedTools: 88,
      matched: true,
      source: 'stdio',
      message: 'ok',
    },
  });

  assert.equal(diagnostics.dto_version, 'strategy_market.capability_diagnostics.v1');
  assert.deepEqual(diagnostics.layers, [
    'mcp_manager',
    'strategy_factory_artifacts',
    'bff_api',
    'frontend_surface',
  ]);
  assert.equal(diagnostics.generated_at, '2026-04-24T00:00:00.000Z');
  assert.equal(diagnostics.mcp_runtime.reachable, true);
  assert.equal(diagnostics.items.length, diagnostics.summary.total);
  assert.equal(diagnostics.summary.backend_without_frontend, 0);
  assert.equal(diagnostics.summary.naming_or_field_mismatch, 0);
  assert.equal(diagnostics.summary.frontend_without_backend, 0);
  assert.equal(diagnostics.critical_unmatched.length, 0);
});

test('diagnostics mark the former product gaps as connected or admin-only', () => {
  const diagnostics = buildStrategyCapabilityDiagnostics({ generatedAt: '2026-04-24T00:00:00.000Z' });
  const rows = byId(diagnostics);

  for (const id of [
    'favorites_alias',
    'factory_run_action_alias',
    'vector_governance',
    'runtime_governance',
    'ai_generation_and_experiments',
    'factory_artifact_direct_reads',
    'admin_lifecycle_controls',
    'frontend_workbench_promises',
  ]) {
    assert.equal(rows.get(id).issues.length, 0, `${id} should not report a critical gap`);
  }

  assert.equal(rows.get('favorites_alias').status, 'matched');
  assert.equal(rows.get('runtime_governance').status, 'matched');
  assert.equal(rows.get('vector_governance').status, 'matched');
  assert.equal(rows.get('frontend_workbench_promises').status, 'matched');
  assert.equal(rows.get('admin_lifecycle_controls').status, 'internal');
  assert.equal(rows.get('ai_generation_and_experiments').status, 'internal');
  assert.match(rows.get('frontend_workbench_promises').frontend.notes, /refresh\/open-workspace/);
  assert.match(rows.get('admin_lifecycle_controls').user_visible_impact, /发布|归档|生命周期扫描/);
});

test('diagnostics only reference registered strategy_manager actions', () => {
  const diagnostics = buildStrategyCapabilityDiagnostics({ generatedAt: '2026-04-24T00:00:00.000Z' });
  const actionSet = new Set(STRATEGY_MANAGER_ACTIONS);

  for (const row of diagnostics.items) {
    for (const action of row.mcp.manager_actions) {
      assert.equal(actionSet.has(action), true, `${row.id} references missing action ${action}`);
    }
    assert.equal(row.mcp.registered, row.mcp.manager_actions.length > 0 || row.mcp.workflow_tools.length > 0);
  }
  assert.equal(diagnostics.summary.p0, 0);
});
