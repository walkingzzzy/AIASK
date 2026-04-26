import test from 'node:test';
import assert from 'node:assert/strict';

const {
  addToolTraceItem,
  createChatToolTrace,
  finalizeToolTrace,
  finishToolTraceItem,
  summarizeToolInput,
  summarizeToolResult,
} = await import('../dist/chat/tool-trace.js');

test('tool trace summarizes MCP calls without exposing user or secret inputs', () => {
  const trace = createChatToolTrace({
    mode: 'copilot',
    pageKey: 'stock',
    stockCode: '600519',
  });

  const item = addToolTraceItem(trace, {
    kind: 'mcp',
    toolName: 'get_realtime_quote',
    args: {
      stock_code: '600519',
      user_id: 'u_demo',
      api_key: 'sk-test-secret',
      period: 'daily',
    },
  });

  finishToolTraceItem(trace, item.id, {
    success: true,
    data: {
      price: 1688.5,
      pct_chg: 2.1,
      rows: [{ code: '600519', name: '贵州茅台' }],
    },
    meta: {
      audit_event_id: 'audit:get_realtime_quote:20260426000000:abcd',
      source_chain: ['akshare'],
    },
  });
  finalizeToolTrace(trace, '实时行情显示上涨 [T1]');

  assert.equal(trace.status, 'completed');
  assert.equal(trace.evidenceMode, 'mcp_supported');
  assert.equal(trace.advisoryOnly, false);
  assert.equal(trace.answerReferences.length, 1);
  assert.equal(trace.answerReferences[0].referenceLabel, 'T1');
  assert(trace.items[0].inputSummary.some((line) => line.includes('stock_code: 600519')));
  assert(!trace.items[0].inputSummary.some((line) => /user_id|api_key|secret/i.test(line)));
  assert(trace.items[0].outputSummary.some((line) => /price|audit_event_id|pct_chg/.test(line)));
});

test('tool trace marks page-context answers and pure advice separately', () => {
  const pageTrace = createChatToolTrace({ mode: 'copilot', pageKey: 'strategy-market' });
  finalizeToolTrace(pageTrace, '基于当前策略详情页给出建议', { hasPageContextEvidence: true });
  assert.equal(pageTrace.evidenceMode, 'page_context_supported');
  assert.equal(pageTrace.advisoryOnly, false);

  const advisoryTrace = createChatToolTrace({ mode: 'copilot' });
  finalizeToolTrace(advisoryTrace, '这是通用建议');
  assert.equal(advisoryTrace.evidenceMode, 'advisory_only');
  assert.equal(advisoryTrace.advisoryOnly, true);
});

test('tool trace result summaries classify failed tools', () => {
  const input = summarizeToolInput({ code: '000001', password: 'hidden', query: '低估值银行股' });
  assert.deepEqual(input, ['code: 000001', 'query: 低估值银行股']);

  const result = summarizeToolResult({ success: false, error: { message: 'MCP timeout' } });
  assert.equal(result.success, false);
  assert.equal(result.errorMessage, 'MCP timeout');
  assert(result.summary[0].includes('错误'));
});
