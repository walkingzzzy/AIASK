#!/usr/bin/env node

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const serviceDist = resolve(process.cwd(), 'apps/bff/dist/mcp-gateway/mcp-gateway.service.js');

if (!existsSync(serviceDist)) {
  throw new Error('缺少 apps/bff/dist 构建产物，请先执行 npm run build -w apps/bff');
}

const { McpGatewayService } = require(serviceDist);

function createConfigService() {
  return {
    get: (_key, fallback) => fallback,
  };
}

function main() {
  const service = new McpGatewayService(createConfigService());

  const structured = service.normalizeToolResult({
    structuredContent: {
      success: true,
      source: 'tushare_pro',
      backend_requested: 'native_bridge',
    },
  });
  assert.equal(structured.backend_requested, 'native_bridge');
  assert.equal(structured.backend_used, 'tushare_pro');
  assert.equal(structured.fallback_used, true);
  assert.equal(structured.fallback_reason, null);
  assert.equal(structured.latency_ms, 0);

  const textPayload = service.normalizeToolResult({
    content: [
      {
        type: 'text',
        text: JSON.stringify({ success: true, source: 'akshare' }),
      },
    ],
  });
  assert.equal(textPayload.backend_requested, 'akshare');
  assert.equal(textPayload.backend_used, 'akshare');
  assert.equal(textPayload.fallback_used, false);
  assert.equal(textPayload.fallback_reason, null);
  assert.equal(textPayload.latency_ms, 0);

  const plain = service.normalizeToolResult({ success: true, data: [] });
  assert.deepEqual(plain, { success: true, data: [] });

  console.log('MCP_FALLBACK_META_CHECK_OK');
  console.log(JSON.stringify({ structured, textPayload, plain }, null, 2));
}

try {
  main();
} catch (error) {
  console.error('MCP_FALLBACK_META_CHECK_FAIL');
  console.error(error);
  process.exit(1);
}
