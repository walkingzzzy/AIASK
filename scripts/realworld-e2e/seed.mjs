import fs from 'node:fs/promises';
import path from 'node:path';
import Redis from 'ioredis';
import { SessionClient, asArray, ensureDir, firstString, readPath } from './shared.mjs';

function normalizeList(value, ...keys) {
  for (const key of keys) {
    const candidate = readPath(value, key);
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  return Array.isArray(value) ? value : [];
}

function firstId(...values) {
  const value = firstString(...values);
  if (!value) {
    throw new Error('expected id in seed payload');
  }
  return value;
}

async function seedNotifications(redis, runtime, userId) {
  const notificationIds = [
    `notif_${runtime.browser}_alert`,
    `notif_${runtime.browser}_trade`,
    `notif_${runtime.browser}_system`,
  ];
  const createdAt = new Date().toISOString();
  const payload = [
    {
      id: notificationIds[0],
      userId,
      type: 'alert',
      level: 'warn',
      title: '价格阈值触发',
      body: '600519 已接近你设置的价格阈值，请检查告警规则。',
      source: 'e2e-seed',
      read: false,
      createdAt,
    },
    {
      id: notificationIds[1],
      userId,
      type: 'trade',
      level: 'info',
      title: '模拟订单已写入',
      body: '你的一笔模拟订单已生成执行回执，可继续去执行中心复盘。',
      source: 'e2e-seed',
      read: false,
      createdAt,
    },
    {
      id: notificationIds[2],
      userId,
      type: 'system',
      level: 'info',
      title: '专用 E2E 环境已就绪',
      body: '当前浏览器运行使用独立数据库、Redis 与 MCP runtime。',
      source: 'e2e-seed',
      read: true,
      createdAt,
    },
  ];
  await redis.set(`bff:cache:notifications:${userId}`, JSON.stringify(payload), 'EX', 604800);
  return notificationIds;
}

async function seedCacheKeys(redis, runtime) {
  const cacheKeys = [
    `bff:cache:e2e:${runtime.runId}:${runtime.browser}:market`,
    `bff:cache:e2e:${runtime.runId}:${runtime.browser}:portfolio`,
  ];
  await redis.set(cacheKeys[0], JSON.stringify({ scope: 'market', browser: runtime.browser }), 'EX', 3600);
  await redis.set(cacheKeys[1], JSON.stringify({ scope: 'portfolio', browser: runtime.browser }), 'EX', 3600);
  return cacheKeys;
}

async function seedDeadLetters(runtime) {
  const deadLetterDir = path.join(runtime.mcpRuntimeDir, '.mcp_cache', 'dead_letters');
  await ensureDir(deadLetterDir);
  const deadLetterPath = path.join(deadLetterDir, 'kline_save_failures.jsonl');
  const deadLetterIds = [`dlq_${runtime.browser}_${runtime.runId}_001`];
  const rows = [
    {
      id: deadLetterIds[0],
      kind: 'save_failure',
      stock_code: '600519',
      retry: 2,
      enqueued_at: Math.floor(Date.now() / 1000) - 60,
      failed_at: Math.floor(Date.now() / 1000),
      error: 'e2e seeded dead letter for admin workflow validation',
      klines_count: 3,
      sample_dates: ['2026-04-10', '2026-04-11', '2026-04-12'],
    },
  ];
  await fs.writeFile(deadLetterPath, `${rows.map((row) => JSON.stringify(row)).join('\n')}\n`, 'utf8');
  return deadLetterIds;
}

export async function seedBrowserEnvironment(runtime) {
  const admin = new SessionClient(runtime.bffBaseUrl);
  const demo = new SessionClient(runtime.bffBaseUrl);
  const browserClient = new SessionClient(runtime.bffBaseUrl);
  const strategyName = `E2E 策略 ${runtime.browser}`;
  const portfolioName = `E2E 组合 ${runtime.browser}`;

  await admin.login('admin', runtime.baseEnv.APP_ADMIN_PASSWORD || 'admin123');
  try {
    await demo.login('demo', runtime.baseEnv.APP_DEMO_PASSWORD || 'demo123');
  } catch {
    // demo user may be disabled
  }

  const browserUser = {
    username: runtime.browserUsername,
    password: runtime.browserPassword,
  };
  const browserProfile = await browserClient.register(browserUser.username, browserUser.password);
  const browserUserId = firstId(
    readPath(browserProfile, 'user', 'id'),
    readPath(browserProfile, 'id'),
  );

  const strategyCreated = await admin.post('/strategy-market/create', {
    name: strategyName,
    strategy_type: 'momentum',
    description: 'realworld-e2e seeded strategy',
    params: { lookback: 20, threshold: 0.02 },
    factor_weights: { momentum: 0.6, quality: 0.4 },
    tags: ['e2e', runtime.browser],
  });
  let strategyId = firstString(
    readPath(strategyCreated, 'id'),
    readPath(strategyCreated, 'strategy_id'),
    readPath(strategyCreated, 'strategyId'),
    readPath(strategyCreated, 'strategy', 'id'),
    readPath(strategyCreated, 'strategy', 'strategy_id'),
  );
  if (!strategyId) {
    const strategyListPayload = await admin.get('/strategy-market/list?status=all&limit=50');
    const strategies = normalizeList(strategyListPayload, 'strategies', 'items', 'data');
    const strategyMatch = strategies.find((item) => (
      readPath(item, 'name') === strategyName
      || readPath(item, 'strategy', 'name') === strategyName
    ));
    strategyId = firstString(
      readPath(strategyMatch, 'id'),
      readPath(strategyMatch, 'strategy_id'),
      readPath(strategyMatch, 'strategyId'),
      readPath(strategyMatch, 'strategy', 'id'),
      readPath(strategyMatch, 'strategy', 'strategy_id'),
    );
    if (!strategyId) {
      await fs.writeFile(
        path.join(runtime.outputDir, 'strategy-debug.json'),
        JSON.stringify({
          strategyName,
          strategyCreated,
          strategyListPayload,
        }, null, 2),
        'utf8',
      );
    }
  }
  if (!strategyId) {
    throw new Error('unable to resolve strategy id from seeded strategy');
  }
  await admin.post(`/strategy-market/${encodeURIComponent(strategyId)}/publish`, {});
  await admin.post(`/strategy-market/${encodeURIComponent(strategyId)}/update-metrics`, {
    period: '30d',
    metrics: {
      total_return: 0.18,
      sharpe: 1.52,
      max_drawdown: -0.08,
      hit_rate: 0.62,
      turnover: 0.21,
    },
  }).catch(() => null);
  await admin.post('/strategy-market/ranking/refresh', {
    strategy_types: ['all', 'momentum'],
    limits: [20],
  }).catch(() => null);

  const portfolioCreated = await browserClient.post('/portfolio/create', {
    name: portfolioName,
    description: 'realworld-e2e seeded portfolio',
    initialCapital: '100000',
    strategies: [{ strategyId, weight: 1 }],
  });
  let portfolioId = firstString(
    readPath(portfolioCreated, 'portfolioId'),
    readPath(portfolioCreated, 'id'),
  );
  if (!portfolioId) {
    const portfolioListPayload = await browserClient.get('/portfolio/list');
    const portfolios = normalizeList(portfolioListPayload, 'items', 'portfolios', 'data');
    const portfolioMatch = portfolios.find((item) => readPath(item, 'name') === portfolioName);
    portfolioId = firstString(
      readPath(portfolioMatch, 'portfolioId'),
      readPath(portfolioMatch, 'id'),
    );
  }
  if (!portfolioId) {
    throw new Error('unable to resolve portfolio id from seeded portfolio');
  }
  await browserClient.post('/portfolio/add-holding', {
    portfolioId,
    code: '600519',
    shares: '100',
    costPrice: '1680',
  }).catch(() => null);

  const groupId = `e2e_${runtime.browser}_${runtime.shortRunId}`;
  const groupName = `E2E分组-${runtime.browser}`;
  await browserClient.post('/watchlist/groups/create', {
    id: groupId,
    name: groupName,
    color: '#0b6bcb',
  });
  await browserClient.post('/watchlist/stocks/add', {
    group: groupId,
    groupName,
    codes: ['600519', '000001'],
  });

  const alertCreated = await browserClient.post('/alerts/create', {
    code: '600519',
    indicator: 'price',
    condition: '>',
    value: '1800',
  });
  let alertId = firstString(
    readPath(alertCreated, 'id'),
    readPath(alertCreated, 'alertId'),
  );
  if (!alertId) {
    const alertsPayload = await browserClient.get('/alerts/list?status=active');
    const alerts = normalizeList(alertsPayload, 'alerts', 'items', 'data');
    const alertMatch = alerts.find((item) => (
      readPath(item, 'code') === '600519'
      && String(readPath(item, 'indicator') || '') === 'price'
    ));
    alertId = firstString(
      readPath(alertMatch, 'id'),
      readPath(alertMatch, 'alertId'),
    );
  }
  if (!alertId) {
    throw new Error('unable to resolve alert id from seeded alert');
  }

  const artifactId = `art_rw_${runtime.browser}_${runtime.shortRunId}`;
  const executionSeed = await browserClient.post('/paper-trading/route-execution', {
    code: '000001',
    direction: 'buy',
    quantity: 100,
    order_type: 'market',
    urgency: 'high',
    artifact_id: artifactId,
    idempotency_key: `seed-route-${runtime.browser}-${runtime.shortRunId}`,
  });

  const accountsPayload = await browserClient.get('/paper-trading/accounts');
  const accounts = normalizeList(accountsPayload, 'accounts', 'items', 'data');
  const accountId = firstId(
    readPath(accounts[0], 'id'),
    readPath(accounts[0], 'account_id'),
    readPath(accounts[0], 'accountId'),
    readPath(executionSeed, 'order', 'account_id'),
    readPath(executionSeed, 'order', 'accountId'),
    readPath(accountsPayload, 'account_id'),
  );

  await browserClient.post('/paper-trading/order', {
    code: '000001',
    direction: 'buy',
    quantity: 100,
    order_type: 'limit',
    price: 1,
    account_id: accountId,
    idempotency_key: `seed-pending-${runtime.browser}-${runtime.shortRunId}`,
  }).catch(() => null);
  await browserClient.post('/paper-trading/update-prices', {
    account_id: accountId,
  }).catch(() => null);
  await browserClient.get(`/paper-trading/performance?account_id=${encodeURIComponent(accountId)}&days=30`).catch(() => null);

  let executionId = firstString(
    readPath(executionSeed, 'execution', 'task_id'),
    readPath(executionSeed, 'execution', 'taskId'),
    readPath(executionSeed, 'execution', 'execution_id'),
    readPath(executionSeed, 'executionId'),
  );

  if (!executionId) {
    const artifactPayload = await browserClient.get(`/execution/artifact/${encodeURIComponent(artifactId)}?account_id=${encodeURIComponent(accountId)}`);
    executionId = firstString(
      readPath(artifactPayload, 'detail', 'taskId'),
      readPath(artifactPayload, 'latestTaskId'),
    );
  }
  if (!executionId) {
    throw new Error('unable to resolve execution id from seeded artifact');
  }

  const redis = new Redis(runtime.redisUrl, { lazyConnect: true });
  await redis.connect();
  const notificationIds = await seedNotifications(redis, runtime, browserUserId);
  const cacheKeys = await seedCacheKeys(redis, runtime);
  await redis.quit();

  const deadLetterIds = await seedDeadLetters(runtime);

  return {
    runId: runtime.runId,
    envName: runtime.envName,
    browser: runtime.browser,
    resetMode: runtime.resetMode,
    baseUrl: runtime.webBaseUrl,
    apiBaseUrl: runtime.bffBaseUrl,
    wsUrl: runtime.wsUrl,
    users: {
      admin: {
        username: 'admin',
        password: runtime.baseEnv.APP_ADMIN_PASSWORD || 'admin123',
        userId: 'u_admin',
      },
      demo: {
        username: 'demo',
        password: runtime.baseEnv.APP_DEMO_PASSWORD || 'demo123',
        userId: 'u_demo',
      },
      browser: {
        username: browserUser.username,
        password: browserUser.password,
        userId: browserUserId,
      },
    },
    strategy: {
      id: strategyId,
      route: `/strategy-market/${encodeURIComponent(strategyId)}`,
      name: `E2E 策略 ${runtime.browser}`,
    },
    execution: {
      artifactId,
      executionId,
      accountId,
    },
    portfolio: {
      portfolioId,
      name: `E2E 组合 ${runtime.browser}`,
    },
    watchlist: {
      groupId,
      groupName,
      codes: ['600519', '000001'],
    },
    alerts: {
      alertId,
      code: '600519',
    },
    notifications: {
      userId: browserUserId,
      ids: notificationIds,
    },
    admin: {
      deadLetterIds,
      cacheKeys,
    },
  };
}
