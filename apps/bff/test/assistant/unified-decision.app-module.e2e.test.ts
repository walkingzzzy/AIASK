import { after, before, test } from 'node:test';
import * as assert from 'node:assert/strict';
import * as cookieParser from 'cookie-parser';
import { ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { AppModule } from '../../src/app.module';
import { validateContract } from '../contract/api-contracts';
import { buildMockMcp } from '../helpers/unified-decision-test-app';
import { McpGatewayService } from '../../src/mcp-gateway/mcp-gateway.service';
import { DbService } from '../../src/db/db.service';
import { CommonCacheService } from '../../src/common/cache.service';
import { GlobalHttpExceptionFilter } from '../../src/common/global-http-exception.filter';

function setCookieHeader(response: Response): string {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] };
  const setCookies = typeof headers.getSetCookie === 'function'
    ? headers.getSetCookie()
    : [response.headers.get('set-cookie')].filter(Boolean) as string[];

  return setCookies
    .map((value) => value.split(';', 1)[0])
    .join('; ');
}

function createDbMock(): Pick<DbService, 'enabled' | 'healthy' | 'query'> {
  return {
    enabled: false,
    healthy: false,
    async query() {
      throw new Error('DATABASE_DISABLED');
    },
  };
}

function createCacheMock(): Pick<
  CommonCacheService,
  'get' | 'getWithMeta' | 'set' | 'del' | 'resolveTtl' | 'getStats'
> {
  return {
    async get() {
      return null;
    },
    async getWithMeta() {
      return {
        value: null,
        meta: { hit: false, backend: 'none' as const },
      };
    },
    async set() {
      return undefined;
    },
    async del() {
      return undefined;
    },
    resolveTtl(_scope: string, fallbackSeconds: number) {
      return fallbackSeconds;
    },
    getStats() {
      return {
        requests: 0,
        hits: 0,
        misses: 0,
        sets: 0,
        redisHits: 0,
        memoryHits: 0,
        redisSets: 0,
        memorySets: 0,
        errors: 0,
        hitRate: 0,
        redisReady: false,
        memorySize: 0,
        ttl: {
          defaultSeconds: 0,
          overrides: {},
        },
      };
    },
  };
}

let app: INestApplication;
let baseUrl = '';

before(async () => {
  const moduleRef = await Test.createTestingModule({
    imports: [AppModule],
  })
    .overrideProvider(McpGatewayService)
    .useValue(buildMockMcp())
    .overrideProvider(DbService)
    .useValue(createDbMock())
    .overrideProvider(CommonCacheService)
    .useValue(createCacheMock())
    .compile();

  app = moduleRef.createNestApplication();
  app.use(cookieParser());
  app.setGlobalPrefix('api');
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  app.useGlobalFilters(new GlobalHttpExceptionFilter());

  await app.listen(0, '127.0.0.1');
  baseUrl = await app.getUrl();
});

after(async () => {
  if (app) {
    await app.close();
  }
});

test('AppModule boots and serves authenticated unified decision flow with real HTTP', async () => {
  const healthResp = await fetch(`${baseUrl}/api/health`);
  const healthBody = await healthResp.json();
  assert.equal(healthResp.status, 200);
  assert.equal(healthBody.success, true);
  assert.equal(healthBody.status, 'ok');
  assert.equal(healthBody.db?.enabled, false);

  const loginResp = await fetch(`${baseUrl}/api/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password: 'demo123' }),
  });
  const loginBody = await loginResp.json();
  assert.equal(loginResp.status, 201);
  assert.equal(loginBody.success, true);
  const cookie = setCookieHeader(loginResp);
  assert.match(cookie, /access_token=/);

  const summaryResp = await fetch(`${baseUrl}/api/assistant/unified-decision`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      cookie,
      'x-trace-id': 'appmodule-summary',
    },
    body: JSON.stringify({ code: '600519', investmentStyle: 'balanced', legacyMode: true }),
  });
  const summaryBody = await summaryResp.json();
  assert.equal(summaryResp.status, 201);
  assert.equal(summaryResp.headers.get('x-trace-id'), 'appmodule-summary');
  assert.equal(validateContract('POST /assistant/unified-decision', summaryBody).valid, true);
  assert.equal(summaryBody.data.card.action, 'buy');
  assert.equal(summaryBody.data.legacyComparison?.auditLogged, true);

  const detailsResp = await fetch(`${baseUrl}/api/assistant/unified-decision/details`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      cookie,
      'x-trace-id': 'appmodule-details',
    },
    body: JSON.stringify({ code: '600519', investmentStyle: 'balanced', legacyMode: true }),
  });
  const detailsBody = await detailsResp.json();
  assert.equal(detailsResp.status, 201);
  assert.equal(detailsResp.headers.get('x-trace-id'), 'appmodule-details');
  assert.equal(validateContract('POST /assistant/unified-decision/details', detailsBody).valid, true);
  assert.equal(detailsBody.data.card.finalScore, 81);

  const diffLogsResp = await fetch(`${baseUrl}/api/assistant/unified-decision/diff-logs?limit=10&code=600519`, {
    headers: {
      cookie,
      'x-trace-id': 'appmodule-diff-logs',
    },
  });
  const diffLogsBody = await diffLogsResp.json();
  assert.equal(diffLogsResp.status, 200);
  assert.equal(diffLogsResp.headers.get('x-trace-id'), 'appmodule-diff-logs');
  assert.equal(validateContract('GET /assistant/unified-decision/diff-logs', diffLogsBody).valid, true);
  assert.equal(diffLogsBody.data.total, 2);
  assert.deepEqual(
    diffLogsBody.data.items.map((item: { traceId: string }) => item.traceId),
    ['appmodule-details', 'appmodule-summary'],
  );
});
