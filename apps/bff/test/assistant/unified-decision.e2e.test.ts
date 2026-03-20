import { after, before, test } from 'node:test';
import * as assert from 'node:assert/strict';
import type { INestApplication } from '@nestjs/common';
import { validateContract } from '../contract/api-contracts';
import { assertJsonSnapshot } from '../helpers/snapshot';
import { createUnifiedDecisionTestApp } from '../helpers/unified-decision-test-app';

function sanitizeDynamicFields(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeDynamicFields(item));
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const next: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(record)) {
      if (key === 'comparedAt' || key === 'createdAt') {
        next[key] = '<timestamp>';
        continue;
      }
      if (key === 'auditId' || key === 'id') {
        next[key] = '<id>';
        continue;
      }
      next[key] = sanitizeDynamicFields(item);
    }
    return next;
  }
  return value;
}

function setCookieHeader(response: Response): string {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] };
  const setCookies = typeof headers.getSetCookie === 'function'
    ? headers.getSetCookie()
    : [response.headers.get('set-cookie')].filter(Boolean) as string[];

  return setCookies
    .map((value) => value.split(';', 1)[0])
    .join('; ');
}

let app: INestApplication;
let baseUrl = '';

before(async () => {
  app = await createUnifiedDecisionTestApp();
  await app.listen(0);
  baseUrl = await app.getUrl();
});

after(async () => {
  if (app) {
    await app.close();
  }
});

test('assistant unified decision flow supports login, authenticated HTTP, snapshots and diff logs', async () => {
  const unauthorized = await fetch(`${baseUrl}/api/assistant/unified-decision`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ code: '600519', investmentStyle: 'balanced' }),
  });
  assert.equal(unauthorized.status, 401);

  const login = await fetch(`${baseUrl}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password: 'demo123' }),
  });
  assert.equal(login.status, 201);
  const cookie = setCookieHeader(login);
  assert.match(cookie, /access_token=/);

  const summaryResp = await fetch(`${baseUrl}/api/assistant/unified-decision`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      cookie,
      'x-trace-id': 'e2e-summary',
    },
    body: JSON.stringify({ code: '600519', investmentStyle: 'balanced', legacyMode: true }),
  });
  const summaryBody = await summaryResp.json();
  assert.equal(summaryResp.status, 201);
  assert.equal(validateContract('POST /assistant/unified-decision', summaryBody).valid, true);
  assertJsonSnapshot(
    'assistant/unified-decision-summary.json',
    sanitizeDynamicFields(summaryBody),
  );

  const detailsResp = await fetch(`${baseUrl}/api/assistant/unified-decision/details`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      cookie,
      'x-trace-id': 'e2e-details',
    },
    body: JSON.stringify({ code: '600519', investmentStyle: 'balanced', legacyMode: true }),
  });
  const detailsBody = await detailsResp.json();
  assert.equal(detailsResp.status, 201);
  assert.equal(validateContract('POST /assistant/unified-decision/details', detailsBody).valid, true);
  assertJsonSnapshot(
    'assistant/unified-decision-details.json',
    sanitizeDynamicFields(detailsBody),
  );

  const logsResp = await fetch(`${baseUrl}/api/assistant/unified-decision/diff-logs?limit=5&code=600519`, {
    headers: {
      cookie,
      'x-trace-id': 'e2e-diff-logs',
    },
  });
  const logsBody = await logsResp.json();
  assert.equal(logsResp.status, 200);
  assert.equal(validateContract('GET /assistant/unified-decision/diff-logs', logsBody).valid, true);
  assertJsonSnapshot(
    'assistant/unified-decision-diff-logs.json',
    sanitizeDynamicFields(logsBody),
  );
});
