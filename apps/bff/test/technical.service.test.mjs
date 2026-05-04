import test from 'node:test';
import assert from 'node:assert/strict';

const { TechnicalService } = await import('../dist/technical/technical.service.js');

test('TechnicalService rejects MCP transport failures instead of returning a successful empty shell', async () => {
  const service = new TechnicalService({
    callTool: async () => {
      throw new Error('technical MCP timeout');
    },
  });

  await assert.rejects(
    () => service.calculateIndicators({ code: '000001', indicators: ['RSI'] }),
    (error) => {
      const response = typeof error?.getResponse === 'function' ? error.getResponse() : {};
      assert.equal(response.success, false);
      assert.equal(response.acceptanceStatus, 'degraded');
      assert.match(String(response.detail ?? ''), /technical MCP timeout/);
      return true;
    },
  );
});
