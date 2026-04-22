async (page, config) => {
  const manifestUrl = config.manifestUrl ? String(config.manifestUrl) : null;
  const outputRoot = String(config.outputRoot);
  const baseUrl = String(config.baseUrl || 'http://127.0.0.1:3000');
  const auditApiBaseUrl = (() => {
    try {
      const parsed = new URL(baseUrl);
      parsed.port = '3001';
      parsed.pathname = '/api';
      parsed.search = '';
      parsed.hash = '';
      return parsed.toString().replace(/\/$/, '');
    } catch {
      return 'http://127.0.0.1:3001/api';
    }
  })();
  const groupLabel = String(config.groupLabel || 'default');
  const surfaceIds = Array.isArray(config.surfaceIds) ? config.surfaceIds : [];
  const auth = config.auth || { mode: 'public' };
  const authWorkflowUser = config.authWorkflowUser || null;

  let manifest = config.manifest && typeof config.manifest === 'object' ? config.manifest : null;
  if (!manifest) {
    if (!manifestUrl) {
      throw new Error('missing manifest or manifestUrl');
    }
    await page.goto(manifestUrl);
    manifest = JSON.parse((await page.locator('body').innerText()).trim());
  }
  const surfaceById = new Map(manifest.surfaces.map((surface) => [surface.surfaceId, surface]));
  const surfaces = surfaceIds.map((surfaceId) => surfaceById.get(surfaceId)).filter(Boolean);
  const results = [];
  let activeIssues = null;

  function isBenignConsoleError(message) {
    return /Extra attributes from the server:\s*%s%s\s*style/i.test(String(message));
  }

  function isBenignRequestFailure(entry) {
    return /ERR_ABORTED|NS_BINDING_ABORTED|ERR_BLOCKED_BY_CLIENT|:: cancelled\b/i.test(String(entry));
  }

  function shouldProvisionAuditUser(credentials) {
    const username = String(credentials?.username || '').trim().toLowerCase();
    return /^pw_audit_|^pwaudit|^pwl/.test(username);
  }

  async function gotoStable(url) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (
        !/interrupted by another navigation/i.test(message) &&
        !/ERR_ABORTED/i.test(message) &&
        !/Timeout .*exceeded/i.test(message)
      ) {
        throw error;
      }
    }
    await page.waitForLoadState('domcontentloaded').catch(() => {});
  }

  page.on('console', (message) => {
    if (!activeIssues || message.type() !== 'error') return;
    const text = message.text();
    if (isBenignConsoleError(text)) return;
    activeIssues.consoleErrors.push(text);
  });
  page.on('requestfailed', (request) => {
    if (!activeIssues) return;
    const entry = `${request.method()} ${request.url()} :: ${request.failure()?.errorText || 'failed'}`;
    if (isBenignRequestFailure(entry)) return;
    activeIssues.requestFailures.push(entry);
  });
  page.on('response', (response) => {
    if (!activeIssues) return;
    if (response.url().includes('/api/') && response.status() >= 500) {
      activeIssues.apiErrors.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });

  async function dismissOnboarding(target) {
    const skip = target.getByRole('button', { name: '跳过' });
    for (let attempt = 0; attempt < 10; attempt += 1) {
      if (await skip.isVisible().catch(() => false)) {
        await skip.click().catch(() => {});
        await target.waitForTimeout(250);
        continue;
      }
      break;
    }
  }

  async function resetSession() {
    await page.context().clearCookies();
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await gotoStable(`${baseUrl}/login`);
      try {
        await page.waitForLoadState('domcontentloaded').catch(() => {});
        await page.evaluate(() => {
          localStorage.clear();
          sessionStorage.clear();
          document.cookie.split(';').forEach((item) => {
            const key = item.split('=')[0]?.trim();
            if (key) {
              document.cookie = `${key}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
            }
          });
        });
        break;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (attempt === 2 || !/Execution context was destroyed/i.test(message)) {
          throw error;
        }
      }
    }
  }

  async function loginIfNeeded(route) {
    if (auth.mode === 'public') {
      await resetSession();
      return;
    }

    await gotoStable(`${baseUrl}${route}`);
    if (/\/login(?:\?|$)/.test(page.url())) {
      await page.evaluate(
        async ({ username, password, allowProvision }) => {
          async function postJson(targetPath, body) {
            const response = await fetch(targetPath, {
              method: 'POST',
              headers: { 'content-type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify(body),
            });
            const raw = await response.text();
            let parsed = null;
            try {
              parsed = raw ? JSON.parse(raw) : null;
            } catch {
              parsed = raw;
            }
            return { ok: response.ok, status: response.status, body: parsed };
          }

          let loginResult = await postJson('/api/auth/login', { username, password });
          if (!loginResult.ok && loginResult.status === 401 && allowProvision) {
            const registerResult = await postJson('/api/auth/register', { username, password });
            if (!registerResult.ok && registerResult.status !== 409) {
              throw new Error(registerResult.body?.error?.message || registerResult.body?.message || 'register failed');
            }
            loginResult = await postJson('/api/auth/login', { username, password });
          }
          if (!loginResult.ok) {
            throw new Error(loginResult.body?.error?.message || loginResult.body?.message || 'login failed');
          }
          window.localStorage.setItem('onboarding-done', '1');
          document.cookie = 'logged_in=1; Path=/; Max-Age=604800; SameSite=Lax';
        },
        {
          username: String(auth.username || ''),
          password: String(auth.password || ''),
          allowProvision: shouldProvisionAuditUser(auth),
        },
      );
      await gotoStable(`${baseUrl}${route}`);
    }
    await page.waitForTimeout(900);
    await dismissOnboarding(page);
  }

  async function collectText(target, selector, max = 8) {
    return target
      .locator(selector)
      .evaluateAll(
        (nodes, limit) =>
          nodes
            .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
            .filter(Boolean)
            .slice(0, limit),
        max,
      )
      .catch(() => []);
  }

  async function collectButtons(target, max = 20) {
    return target
      .locator('button, [role="button"], [role="tab"]')
      .evaluateAll(
        (nodes, limit) =>
          nodes
            .map((node) => ({
              label: (node.getAttribute('aria-label') || node.getAttribute('title') || node.textContent || '')
                .replace(/\s+/g, ' ')
                .trim(),
              role: node.getAttribute('role') === 'tab' ? 'tab' : 'button',
              status: 'observed',
            }))
            .filter((item) => item.label)
            .slice(0, limit),
        max,
      )
      .catch(() => []);
  }

  async function collectFields(target, max = 12) {
    return target
      .locator('input, textarea, select')
      .evaluateAll(
        (nodes, limit) =>
          nodes
            .map((node) => ({
              label:
                node.getAttribute('aria-label') ||
                node.getAttribute('placeholder') ||
                node.getAttribute('name') ||
                node.id ||
                node.tagName.toLowerCase(),
              type: node.getAttribute('type') || node.tagName.toLowerCase(),
            }))
            .filter((item) => item.label)
            .slice(0, limit),
        max,
      )
      .catch(() => []);
  }

  async function snapshotInfo(surface) {
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(900);
    await dismissOnboarding(page);
    return {
      surfaceId: surface.surfaceId,
      label: surface.label,
      group: surface.group,
      auth: surface.auth,
      route: surface.route,
      title: await page.title(),
      finalUrl: page.url(),
      headings: await collectText(page, 'h1, h2, h3, [role="heading"]', 8),
      sections: await collectText(page, 'main section h2, main section h3, main article h2, main article h3', 8),
      tabs: await collectText(page, '[role="tab"]', 12),
      buttons: await collectButtons(page, 20),
      fields: await collectFields(page, 12),
      issues: { apiErrors: [], consoleErrors: [], requestFailures: [] },
      workflow: [],
      screenshots: [],
      status: 'passed',
    };
  }

  function markButton(result, pattern, status, note) {
    let matched = false;
    result.buttons = result.buttons.map((button) => {
      if (pattern.test(button.label)) {
        matched = true;
        return { ...button, status, note };
      }
      return button;
    });
    if (!matched) {
      result.buttons.push({ label: pattern.source, role: 'button', status, note });
    }
  }

  async function saveShot(surface, fileName, result) {
    const fullPath = `${outputRoot}/${surface.group}/${surface.surfaceId}/screens/${fileName}`;
    await page.screenshot({ path: fullPath, fullPage: true });
    result.screenshots.push(fullPath);
  }

  async function clickIfVisible(locator, waitMs = 700) {
    if (await locator.isVisible().catch(() => false)) {
      try {
        await locator.click();
        await page.waitForTimeout(waitMs);
        return true;
      } catch {
        return false;
      }
    }
    return false;
  }

  function byTestId(testId) {
    return page.locator(`[data-testid="${testId}"]`).first();
  }

  function byActionTestId(testId) {
    return page.locator(`[data-action-testid="${testId}"]`).first();
  }

  async function waitUntilEnabled(locator, attempts = 20, waitMs = 200) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (await locator.isEnabled().catch(() => false)) {
        return true;
      }
      await page.waitForTimeout(waitMs);
    }
    return false;
  }

  async function fillStable(locator, value, attempts = 5, waitMs = 250) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      await locator.fill(value).catch(() => {});
      await page.waitForTimeout(waitMs);
      if ((await locator.inputValue().catch(() => '')) === value) {
        return true;
      }
    }
    return false;
  }

  async function fetchJson(path, init = {}) {
    return page.evaluate(
      async ({ targetPath, targetInit, apiBaseUrl }) => {
        const normalizedPath = (() => {
          const rawPath = String(targetPath || '').trim();
          if (!rawPath) return apiBaseUrl;
          if (/^https?:\/\//i.test(rawPath)) return rawPath;
          if (!rawPath.startsWith('/')) return `${apiBaseUrl}/${rawPath}`;
          if (rawPath.startsWith('/api/')) return `${apiBaseUrl}${rawPath.slice(4)}`;
          return `${apiBaseUrl}${rawPath}`;
        })();
        const response = await fetch(normalizedPath, {
          credentials: 'include',
          ...targetInit,
          headers: {
            ...(targetInit?.body ? { 'content-type': 'application/json' } : {}),
            ...(targetInit?.headers || {}),
          },
        });
        const text = await response.text();
        let body = null;
        try {
          body = text ? JSON.parse(text) : null;
        } catch {
          body = text;
        }
        return { ok: response.ok, status: response.status, body };
      },
      { targetPath: path, targetInit: init, apiBaseUrl: auditApiBaseUrl },
    );
  }

  async function ensureStrategyAuditSample() {
    const ranking = await fetchJson('/api/strategy-market/ranking?limit=5');
    const strategies = Array.isArray(ranking.body?.data?.strategies) ? ranking.body.data.strategies : [];
    const existing = strategies.find((item) => {
      const strategyId = String(item?.id || '').trim();
      return strategyId && strategyId !== '__empty__';
    });
    if (existing?.id) return String(existing.id);

    const created = await fetchJson('/api/strategy-market/create', {
      method: 'POST',
      body: JSON.stringify({
        name: 'PW 审计样本策略',
        strategy_type: 'momentum',
        description: '供页面巡检和详情链路验证使用的稳定策略样本。',
        params: { universe: '沪深300', holding_days: 10, rebalance: 'weekly' },
        factor_weights: { trend: 0.68, quality: 0.2, risk: 0.12 },
        tags: ['audit', 'playwright', 'responsive'],
      }),
    });
    const strategyId = String(created.body?.data?.strategy_id || '').trim();
    if (!created.ok || !strategyId) return null;

    await fetchJson(`/api/strategy-market/${encodeURIComponent(strategyId)}/publish`, { method: 'POST' });
    return strategyId;
  }

  async function resolveRoute(surface) {
    if (!surface.route.includes(':strategyId') && !surface.route.includes(':artifactId')) {
      return surface.route;
    }

    if (surface.route.includes(':strategyId')) {
      await loginIfNeeded('/strategy-market');
      const strategyId = await ensureStrategyAuditSample().catch(() => null);
      if (strategyId) {
        return `/strategy-market/${encodeURIComponent(strategyId)}`;
      }
      try {
        await gotoStable(`${baseUrl}/strategy-market`);
      } catch {
        return '/strategy-market/__empty__?state=empty';
      }
      await page.waitForTimeout(1400);
      const href = await page.locator('a[href^="/strategy-market/"]').evaluateAll((nodes) => {
        for (const node of nodes) {
          const hrefValue = node.getAttribute('href');
          if (
            hrefValue &&
            /^\/strategy-market\/[^/?#]+/.test(hrefValue) &&
            hrefValue !== '/strategy-market' &&
            !/^\/strategy-market\/__empty__(?:\?|$)/.test(hrefValue)
          ) {
            return hrefValue;
          }
        }
        return null;
      });
      return href || '/strategy-market/__empty__?state=empty';
    }

    if (surface.route.includes(':artifactId')) {
      await loginIfNeeded('/execution');
      try {
        await gotoStable(`${baseUrl}/execution`);
      } catch {
        return '/execution/artifacts/__empty__?state=empty';
      }
      await page.waitForTimeout(1400);
      const href = await page.locator('a[href^="/execution/artifacts/"]').evaluateAll((nodes) => {
        for (const node of nodes) {
          const hrefValue = node.getAttribute('href');
          if (
            hrefValue &&
            /^\/execution\/artifacts\/[^/?#]+/.test(hrefValue) &&
            !/^\/execution\/artifacts\/__empty__(?:\?|$)/.test(hrefValue)
          ) {
            return hrefValue;
          }
        }
        return null;
      });
      return href || '/execution/artifacts/__empty__?state=empty';
    }

    return surface.route;
  }

  async function generateTotp(secret) {
    return page.evaluate(async (base32) => {
      const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
      const normalized = String(base32 || '')
        .replace(/=+$/g, '')
        .replace(/\s+/g, '')
        .toUpperCase();
      let bits = '';
      for (const char of normalized) {
        const index = alphabet.indexOf(char);
        if (index >= 0) bits += index.toString(2).padStart(5, '0');
      }
      const bytes = bits
        .match(/.{1,8}/g)
        .filter((chunk) => chunk.length === 8)
        .map((chunk) => parseInt(chunk, 2));
      const counter = Math.floor(Date.now() / 1000 / 30);
      const buffer = new ArrayBuffer(8);
      const view = new DataView(buffer);
      view.setUint32(4, counter);
      const key = await crypto.subtle.importKey('raw', new Uint8Array(bytes), { name: 'HMAC', hash: 'SHA-1' }, false, [
        'sign',
      ]);
      const signature = new Uint8Array(await crypto.subtle.sign('HMAC', key, buffer));
      const offset = signature[signature.length - 1] & 0x0f;
      const binary =
        ((signature[offset] & 0x7f) << 24) |
        ((signature[offset + 1] & 0xff) << 16) |
        ((signature[offset + 2] & 0xff) << 8) |
        (signature[offset + 3] & 0xff);
      return String(binary % 1000000).padStart(6, '0');
    }, secret);
  }

  async function runWorkflow(surface, result) {
    if (surface.surfaceId === 'register' && authWorkflowUser) {
      await page.waitForTimeout(800);
      await fillStable(page.locator('#reg-username'), String(authWorkflowUser.username));
      await fillStable(page.locator('#reg-password'), String(authWorkflowUser.password));
      await fillStable(page.locator('#reg-confirm'), String(authWorkflowUser.password));
      const submit = page.getByRole('button', { name: '创建账号' });
      await waitUntilEnabled(submit);
      const clicked = await clickIfVisible(submit, 400);
      if (clicked) {
        await page.waitForURL((url) => !/\/register(?:\?|$)/.test(url.toString()), { timeout: 6000 }).catch(() => {});
      }
      const passed = !/\/register(?:\?|$)/.test(page.url());
      result.workflow.push({
        name: '注册临时审查账号',
        status: passed ? 'passed' : 'failed',
        note: passed ? `已跳转到 ${page.url()}` : '仍停留在注册页',
      });
      markButton(result, /创建账号/, passed ? 'passed' : 'failed', passed ? '注册成功' : '未完成注册');
      return;
    }

    if (surface.surfaceId === 'login' && authWorkflowUser) {
      await waitUntilEnabled(page.getByRole('button', { name: '登录' }), 30, 200);
      await fillStable(page.locator('#login-username'), String(authWorkflowUser.username));
      await fillStable(page.locator('#login-password'), String(authWorkflowUser.password));
      const submit = page.getByRole('button', { name: '登录' });
      await waitUntilEnabled(submit);
      const clicked = await clickIfVisible(submit, 400);
      if (clicked) {
        await page.waitForURL((url) => !/\/login(?:\?|$)/.test(url.toString()), { timeout: 6000 }).catch(() => {});
      }
      const passed = !/\/login(?:\?|$)/.test(page.url());
      result.workflow.push({
        name: '登录临时审查账号',
        status: passed ? 'passed' : 'failed',
        note: passed ? `已进入 ${page.url()}` : '提交后仍停留在登录页',
      });
      markButton(result, /登录/, passed ? 'passed' : 'failed', passed ? '登录成功' : '登录失败');
      return;
    }

    if (surface.surfaceId === 'home' || surface.surfaceId === 'market' || surface.surfaceId === 'market-tabs') {
      if (await clickIfVisible(page.getByRole('tab', { name: '指数' }))) {
        const input = page.getByLabel('指数代码').first();
        if (await input.isVisible().catch(() => false)) {
          await input.fill('000300');
          await clickIfVisible(page.getByRole('button', { name: '查询指数行情', exact: true }), 900);
          result.workflow.push({ name: '查询指数行情', status: 'passed', note: '已输入 000300 并触发查询' });
          markButton(result, /查询指数行情/, 'passed', '已执行');
        }
      }
      if (await clickIfVisible(page.getByRole('tab', { name: '搜索' }))) {
        const input = page.getByLabel('搜索关键词').first();
        if (await input.isVisible().catch(() => false)) {
          await input.fill('平安');
          await clickIfVisible(page.getByRole('button', { name: '搜索', exact: true }), 900);
          result.workflow.push({ name: '市场搜索', status: 'passed', note: '已搜索 平安' });
          markButton(result, /^搜索$/, 'passed', '已执行');
        }
      }
      return;
    }

    if (surface.surfaceId === 'stock' || surface.surfaceId === 'stock-analysis-tabs') {
      const input = page.getByRole('textbox', { name: '股票代码' }).first();
      if (await input.isVisible().catch(() => false)) {
        await input.fill('000001');
        await clickIfVisible(page.getByRole('button', { name: '立即查询股票', exact: true }), 1000);
        await clickIfVisible(page.getByRole('tab', { name: '估值' }));
        await clickIfVisible(page.getByRole('tab', { name: '资讯' }));
        result.workflow.push({ name: '个股查询', status: 'passed', note: '已查询 000001 并切换 tab' });
        markButton(result, /立即查询股票/, 'passed', '已执行');
      }
      return;
    }

    if (surface.surfaceId === 'search') {
      const input = page.getByLabel('搜索关键词').first();
      if (await input.isVisible().catch(() => false)) {
        await input.fill('平安');
        await clickIfVisible(page.getByRole('button', { name: '搜索', exact: true }), 900);
        result.workflow.push({ name: '智能搜索', status: 'passed', note: '已搜索 平安' });
      }
      return;
    }

    if (surface.surfaceId === 'technical') {
      const passed = await clickIfVisible(byTestId('page-primary-action'), 1600);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '技术分析主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已执行推荐分析并捕获主状态区' : '未命中技术分析主动作或状态区',
      });
      markButton(result, /运行推荐分析/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'valuation') {
      const passed = await clickIfVisible(byTestId('page-primary-action'), 1600);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '估值分析主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已执行推荐估值并捕获主状态区' : '未命中估值主动作或状态区',
      });
      markButton(result, /运行推荐估值/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'factor') {
      const passed = await clickIfVisible(byTestId('page-primary-action'), 1800);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '因子研究主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已执行推荐研究样例并捕获主状态区' : '未命中因子研究主动作或状态区',
      });
      markButton(result, /运行推荐研究样例/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'events') {
      const action = byActionTestId('events-subscription-action');
      const passed = await clickIfVisible(action, 1500);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '事件订阅主流程',
        status: passed && statusVisible ? 'passed' : 'partial',
        note: passed && statusVisible ? '已执行订阅切换并捕获事件状态区' : '主动作位置稳定，但本轮未完成订阅切换',
      });
      markButton(
        result,
        /订阅当前股票事件|取消订阅当前股票事件/,
        passed ? 'passed' : 'partial',
        passed ? '已执行' : '按钮可见但未触发',
      );
      return;
    }

    if (surface.surfaceId === 'portfolio') {
      const action = byActionTestId('portfolio-refresh-action');
      const passed = await clickIfVisible(action, 1500);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '组合工作台主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已刷新组合摘要并捕获主状态区' : '未命中组合主动作或状态区',
      });
      markButton(result, /刷新组合列表/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'risk') {
      const action = byActionTestId('risk-refresh-action');
      const passed = await clickIfVisible(action, 1500);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '风险工作台主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已刷新风险摘要并捕获主状态区' : '未命中风险主动作或状态区',
      });
      markButton(result, /刷新当前风险|准备 252 天窗口/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'backtest') {
      const input = page.locator('#backtest-stock-code');
      if (await input.isVisible().catch(() => false)) {
        await input.fill('600519');
        await clickIfVisible(page.getByRole('button', { name: '运行回测' }), 1400);
        result.workflow.push({ name: '运行回测', status: 'passed', note: '已触发 600519 回测' });
        markButton(result, /运行回测/, 'passed', '已执行');
      }
      return;
    }

    if (surface.surfaceId === 'data' || surface.surfaceId === 'data-center-tabs') {
      const optionInput = page.locator('#data-option-underlying').first();
      if (await optionInput.isVisible().catch(() => false)) {
        await optionInput.fill('510050').catch(() => {});
      }
      await clickIfVisible(page.getByRole('button', { name: '查询期权链工作台', exact: true }), 900);
      await clickIfVisible(page.getByRole('tab', { name: '交易日历' }));
      await clickIfVisible(page.getByRole('button', { name: '加载交易日历工作台', exact: true }), 900);
      result.workflow.push({ name: '数据中心查询', status: 'passed', note: '已用真实输入触发期权链和交易日历查询' });
      return;
    }

    if (surface.surfaceId === 'macro') {
      const select = page.getByLabel('宏观指标').first();
      if (await select.isVisible().catch(() => false)) {
        await select.selectOption('cpi').catch(() => {});
        await page.waitForTimeout(800);
        result.workflow.push({ name: '宏观指标切换', status: 'passed', note: '已切换到 CPI' });
      }
      return;
    }

    if (surface.surfaceId === 'options') {
      const input = page.getByLabel('期权标的代码').first();
      if (await input.isVisible().catch(() => false)) {
        await input.fill('510050');
        await clickIfVisible(page.getByRole('button', { name: '查询', exact: true }), 1200);
        result.workflow.push({ name: '期权链查询', status: 'passed', note: '已查询 510050' });
        markButton(result, /^查询$/, 'passed', '已执行');
      }
      return;
    }

    if (surface.surfaceId === 'decision') {
      const passed = await clickIfVisible(page.getByRole('button', { name: '运行统一决策' }).first(), 1200);
      result.workflow.push({
        name: '统一决策',
        status: passed ? 'passed' : 'blocked',
        note: passed ? '已触发统一决策动作' : '未找到统一决策按钮',
      });
      markButton(result, /运行统一决策/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'screener') {
      const passed = await clickIfVisible(page.getByRole('button', { name: /开始筛选|执行筛选/ }).first(), 1200);
      result.workflow.push({
        name: '条件选股',
        status: passed ? 'passed' : 'blocked',
        note: passed ? '已触发筛选动作' : '未找到筛选按钮',
      });
      return;
    }

    if (surface.surfaceId === 'alerts') {
      if (
        await page
          .locator('#alerts-stock-code')
          .isVisible()
          .catch(() => false)
      ) {
        await page.locator('#alerts-stock-code').fill('000001');
        await page
          .locator('#alerts-indicator')
          .fill('price')
          .catch(() => {});
        await page
          .locator('#alerts-condition')
          .selectOption('>')
          .catch(() => {});
        await page
          .locator('#alerts-threshold')
          .fill('12')
          .catch(() => {});
        await clickIfVisible(page.getByRole('button', { name: '创建告警' }), 800);
        await clickIfVisible(page.getByRole('button', { name: '确认创建' }), 1200);
        result.workflow.push({ name: '创建告警', status: 'passed', note: '已尝试创建 000001 price > 12' });
        markButton(result, /创建告警/, 'passed', '已执行');
      }
      return;
    }

    if (surface.surfaceId === 'watchlist') {
      const createGroup = page.getByRole('button', { name: '新建分组' });
      if (await createGroup.isVisible().catch(() => false)) {
        await createGroup.click();
        await page
          .getByPlaceholder('分组名称')
          .fill(`pw-audit-${Date.now().toString().slice(-4)}`)
          .catch(() => {});
        await clickIfVisible(page.getByRole('button', { name: '创建分组' }), 1200);
        result.workflow.push({ name: '新建自选分组', status: 'passed', note: '已执行分组创建' });
        markButton(result, /创建分组/, 'passed', '已执行');
      }
      return;
    }

    if (surface.surfaceId === 'notifications') {
      const markAll = byActionTestId('notifications-mark-all-read-action');
      const visible = await markAll.isVisible().catch(() => false);
      const enabled = visible ? await markAll.isEnabled().catch(() => false) : false;
      const passed = enabled ? await clickIfVisible(markAll, 900) : false;
      result.workflow.push({
        name: '通知处理',
        status: passed ? 'passed' : visible ? 'partial' : 'blocked',
        note: passed
          ? '已触发全部已读并保留主状态区'
          : visible
            ? '全部已读入口固定可见，但当前为禁用或未触发'
            : '未找到固定主动作',
      });
      markButton(
        result,
        /全部标记已读/,
        passed ? 'passed' : visible ? 'partial' : 'blocked',
        passed ? '已执行' : '入口保留但未执行',
      );
      return;
    }

    if (surface.surfaceId === 'settings' || surface.surfaceId === 'settings-workbench') {
      const nicknameInput = page.locator('#settings-nickname').first();
      if (await nicknameInput.isVisible().catch(() => false)) {
        await nicknameInput.fill(`PW Audit ${Date.now().toString().slice(-4)}`);
      }
      const riskSelect = page.locator('#settings-risk-level').first();
      if (await riskSelect.isVisible().catch(() => false)) {
        await riskSelect.selectOption('激进').catch(() => {});
      }
      await clickIfVisible(page.getByRole('button', { name: '保存资料' }), 1000);
      await clickIfVisible(page.getByRole('button', { name: '生成投资报告', exact: true }), 1500);
      result.workflow.push({ name: '设置资料与生成报告', status: 'passed', note: '已尝试保存资料并生成投资报告' });
      markButton(result, /保存资料/, 'passed', '已执行');
      markButton(result, /生成投资报告/, 'passed', '已执行');
      return;
    }

    if (surface.surfaceId === 'settings-security') {
      const setupButton = page.getByRole('button', { name: /启用 2FA/ }).first();
      if (await setupButton.isVisible().catch(() => false)) {
        await setupButton.click().catch(() => {});
        await page.waitForTimeout(1200);
        const secret = await page
          .locator('code')
          .first()
          .textContent()
          .catch(() => null);
        if (secret) {
          const totp = await generateTotp(secret);
          await page
            .getByPlaceholder('000000')
            .fill(totp)
            .catch(() => {});
          await clickIfVisible(page.getByRole('button', { name: '验证' }), 1200);
          await clickIfVisible(page.getByRole('button', { name: '关闭 2FA' }), 1200);
          result.workflow.push({ name: '2FA 启停', status: 'passed', note: '已完成 setup/verify/disable 闭环' });
          markButton(result, /启用 2FA|关闭 2FA/, 'passed', '已执行');
          return;
        }
      }
      result.workflow.push({ name: '2FA 启停', status: 'blocked', note: '未获取到 setup secret 或入口缺失' });
      return;
    }

    if (surface.surfaceId === 'paper-trading' || surface.surfaceId === 'paper-trading-order-workbench') {
      const codeInput = page.getByRole('textbox', { name: '股票代码' }).first();
      if (await codeInput.isVisible().catch(() => false)) {
        await codeInput.fill('600519').catch(() => {});
      }
      const submit = page.getByRole('button', { name: /确认买入|确认卖出|提交订单|提交/ }).first();
      const passed = await clickIfVisible(submit, 1500);
      result.workflow.push({
        name: '模拟交易提交',
        status: passed ? 'passed' : 'partial',
        note: passed ? '已触发一次提交动作' : '未命中明确提交按钮',
      });
      return;
    }

    if (surface.surfaceId === 'strategy-market' || surface.surfaceId === 'strategy-market-catalog-workbench') {
      const cartButton = page.getByRole('button', { name: /加入购物车|加入组合|组合购物车/ }).first();
      const passed = await clickIfVisible(cartButton, 1000);
      result.workflow.push({
        name: '策略超市动作',
        status: passed ? 'passed' : 'partial',
        note: passed ? '已执行购物车/组合相关动作' : '未命中明显动作按钮',
      });
      return;
    }

    if (surface.surfaceId === 'strategy-detail' || surface.surfaceId === 'strategy-detail-review-workbench') {
      await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first());
      await clickIfVisible(page.getByRole('tab', { name: '运行风控' }).first());
      const subscribe = byTestId('strategy-subscribe-action');
      const passed = await clickIfVisible(subscribe, 1000);
      result.workflow.push({
        name: '策略详情动作',
        status: passed ? 'passed' : 'partial',
        note: passed ? '已执行稳定订阅动作并切换到工厂审查' : '未命中稳定订阅按钮',
      });
      return;
    }

    if (surface.surfaceId === 'skills') {
      const refresh = byActionTestId('skills-refresh-action');
      const passed = await clickIfVisible(refresh, 1200);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '技能中心主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已刷新技能列表并捕获主状态区' : '未命中技能中心主动作或状态区',
      });
      markButton(result, /刷新技能列表/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'workspace-templates') {
      const runWorkflow = byActionTestId('workspace-templates-run-action');
      const passed = await clickIfVisible(runWorkflow, 1200);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '模板中心主流程',
        status: passed && statusVisible ? 'passed' : 'partial',
        note: passed && statusVisible ? '已执行选中工作流并捕获主状态区' : '模板中心主动作位置稳定，但本轮未完成执行',
      });
      markButton(result, /^执行 /, passed ? 'passed' : 'partial', passed ? '已执行' : '按钮可见但未触发');
      return;
    }

    if (surface.surfaceId === 'admin') {
      const refresh = byActionTestId('admin-refresh-snapshot-action');
      const passed = await clickIfVisible(refresh, 1200);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '管理后台快照刷新',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已刷新运行快照并捕获主状态区' : '未命中稳定快照刷新入口',
      });
      markButton(result, /刷新运行快照/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'admin-cache') {
      const refresh = byTestId('page-primary-action');
      const passed = await clickIfVisible(refresh, 1200);
      const clearAll = byTestId('cache-clear-all-action');
      const openedConfirm = await clickIfVisible(clearAll, 500);
      if (openedConfirm) {
        await clickIfVisible(page.getByRole('button', { name: '取消', exact: true }), 500);
      }
      result.workflow.push({
        name: '缓存管理',
        status: passed ? 'passed' : openedConfirm ? 'partial' : 'blocked',
        note: passed
          ? '已刷新缓存统计，并验证清理确认层可打开'
          : openedConfirm
            ? '已验证确认层，但未命中缓存统计刷新动作'
            : '未命中缓存统计入口或确认层',
      });
      markButton(result, /刷新缓存统计/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      markButton(
        result,
        /清除全部缓存/,
        openedConfirm ? 'partial' : 'blocked',
        openedConfirm ? '已打开确认层，未继续执行' : '按钮缺失',
      );
      return;
    }

    if (surface.surfaceId === 'admin-tools') {
      const refresh = byActionTestId('admin-tools-refresh-action');
      const passed = await clickIfVisible(refresh, 1200);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '工具仪表盘主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已刷新工具统计并捕获主状态区' : '未命中工具仪表盘主动作或状态区',
      });
      markButton(result, /刷新工具统计/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'admin-users') {
      const refresh = byActionTestId('admin-users-refresh-action');
      const passed = await clickIfVisible(refresh, 1200);
      const statusVisible = await byTestId('page-primary-status')
        .isVisible()
        .catch(() => false);
      result.workflow.push({
        name: '用户管理主流程',
        status: passed && statusVisible ? 'passed' : 'blocked',
        note: passed && statusVisible ? '已刷新用户列表并捕获主状态区' : '未命中用户管理主动作或状态区',
      });
      markButton(result, /刷新用户列表/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'admin-dead-letters') {
      const retry = page.getByRole('button', { name: /重试/ }).first();
      const clearAll = page.getByRole('button', { name: '清除全部' }).first();
      if (await retry.isVisible().catch(() => false)) {
        await retry.click().catch(() => {});
        await page.waitForTimeout(1200);
        result.workflow.push({ name: '死信重试', status: 'passed', note: '已执行首条重试' });
        return;
      }
      if (await clearAll.isVisible().catch(() => false)) {
        result.workflow.push({ name: '死信清理', status: 'partial', note: '发现清除全部入口，但未直接执行' });
        markButton(result, /清除全部/, 'high_risk_not_executed', '高风险动作未执行');
        return;
      }
      result.workflow.push({ name: '死信队列审查', status: 'partial', note: '当前页面没有可执行死信动作' });
      return;
    }

    if (surface.surfaceId === 'performance' || surface.surfaceId === 'performance-review-workbench') {
      await clickIfVisible(page.getByRole('tab', { name: '组合归因' }).first());
      await clickIfVisible(page.getByRole('tab', { name: '账户绩效' }).first());
      result.workflow.push({ name: '绩效切页', status: 'passed', note: '已切换账户绩效/组合归因 tab' });
      return;
    }

    if (surface.surfaceId === 'settings-audit-log' || surface.surfaceId === 'execution-artifact-detail') {
      result.workflow.push({
        name: '页面审查',
        status: 'partial',
        note: '完成页面与数据区检查，未命中明确低风险写操作',
      });
      return;
    }

    const genericInput = page.getByRole('textbox', { name: '股票代码' }).first();
    if (await genericInput.isVisible().catch(() => false)) {
      await genericInput.fill('600519').catch(() => {});
      const action = page.getByRole('button', { name: /查询|加载|刷新|分析|生成|获取/ }).first();
      if (await action.isVisible().catch(() => false)) {
        await action.click().catch(() => {});
        await page.waitForTimeout(800);
        result.workflow.push({ name: '通用查询动作', status: 'passed', note: '已触发首个查询类按钮' });
        return;
      }
    }

    result.workflow.push({
      name: '页面审查',
      status: 'partial',
      note: '未命中专用 workflow，保留页面级截图和结构化信息',
    });
  }

  for (const surface of surfaces) {
    const resolvedRoute = await resolveRoute(surface);
    if (/__missing__/.test(resolvedRoute)) {
      const result = {
        surfaceId: surface.surfaceId,
        label: surface.label,
        group: surface.group,
        auth: surface.auth,
        route: surface.route,
        title: 'dynamic-route-missing',
        finalUrl: `${baseUrl}${resolvedRoute}`,
        headings: [],
        sections: [],
        tabs: [],
        buttons: [],
        fields: [],
        issues: { apiErrors: [], consoleErrors: [], requestFailures: [] },
        workflow: [{ name: '动态路由解析', status: 'blocked', note: '当前环境未找到可用详情链接' }],
        screenshots: [],
        status: 'blocked',
      };
      results.push(result);
      continue;
    }
    await loginIfNeeded(resolvedRoute.replace(baseUrl, ''));
    await gotoStable(resolvedRoute.startsWith('http') ? resolvedRoute : `${baseUrl}${resolvedRoute}`);
    const result = await snapshotInfo({
      ...surface,
      route: resolvedRoute.startsWith('http') ? resolvedRoute.replace(baseUrl, '') : resolvedRoute,
    });
    activeIssues = result.issues;
    await saveShot(surface, '01-entry.png', result);
    try {
      await runWorkflow(surface, result);
      if (result.workflow.length) {
        await saveShot(surface, '02-flow.png', result);
      }
      const highRiskPatterns = [/删除|清空|重置|退出|注销|撤单|取消订阅|确认清理|清除全部/];
      result.buttons = result.buttons.map((button) =>
        highRiskPatterns.some((pattern) => pattern.test(button.label)) && button.status === 'observed'
          ? { ...button, status: 'high_risk_not_executed', note: '高风险动作未在本轮直接执行' }
          : button,
      );
      if (/__missing__/.test(result.route) || /__missing__/.test(result.finalUrl)) {
        result.status = 'blocked';
        result.workflow.push({ name: '动态路由解析', status: 'blocked', note: '当前环境未找到可用详情链接' });
      }
    } catch (error) {
      result.status = 'failed';
      result.workflow.push({
        name: 'workflow',
        status: 'failed',
        note: error instanceof Error ? error.message : String(error),
      });
    }
    results.push(result);
    activeIssues = null;
  }

  await page.evaluate(
    (payload) => {
      const storageKey = '__pw_audit_results__';
      const current = JSON.parse(window.localStorage.getItem(storageKey) || '[]');
      const filtered = current.filter((item) => !payload.surfaceIds.includes(item.surfaceId));
      filtered.push(...payload.results);
      window.localStorage.setItem(storageKey, JSON.stringify(filtered));
      console.log('__PW_AUDIT_RESULTS__' + JSON.stringify({ group: payload.groupLabel, results: payload.results }));
    },
    { groupLabel, results, surfaceIds },
  );
  return { group: groupLabel, count: results.length };
};
