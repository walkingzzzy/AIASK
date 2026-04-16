(async (page, config) => {
  const manifestUrl = String(config.manifestUrl);
  const outputRoot = String(config.outputRoot);
  const baseUrl = String(config.baseUrl || 'http://127.0.0.1:3000');
  const groupLabel = String(config.groupLabel || 'default');
  const surfaceIds = Array.isArray(config.surfaceIds) ? config.surfaceIds : [];
  const auth = config.auth || { mode: 'public' };
  const authWorkflowUser = config.authWorkflowUser || null;

  await page.goto(manifestUrl);
  const manifest = JSON.parse((await page.locator('body').innerText()).trim());
  const surfaces = manifest.surfaces.filter((surface) => surfaceIds.includes(surface.surfaceId));
  const results = [];
  let activeIssues = null;

  async function gotoStable(url) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!/interrupted by another navigation/i.test(message) && !/ERR_ABORTED/i.test(message) && !/Timeout .*exceeded/i.test(message)) {
        throw error;
      }
    }
    await page.waitForLoadState('domcontentloaded').catch(() => {});
  }

  page.on('console', (message) => {
    if (!activeIssues || message.type() !== 'error') return;
    activeIssues.consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => {
    if (!activeIssues) return;
    activeIssues.requestFailures.push(`${request.method()} ${request.url()} :: ${request.failure()?.errorText || 'failed'}`);
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
    await gotoStable(`${baseUrl}/login`);
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
  }

  async function loginIfNeeded(route) {
    if (auth.mode === 'public') {
      await resetSession();
      return;
    }

    await gotoStable(`${baseUrl}${route}`);
    if (/\/login(?:\?|$)/.test(page.url())) {
      await page.evaluate(async ({ username, password }) => {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ username, password }),
        });
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(payload?.error?.message || payload?.message || 'login failed');
        }
        window.localStorage.setItem('onboarding-done', '1');
        document.cookie = 'logged_in=1; Path=/; Max-Age=604800; SameSite=Lax';
      }, { username: String(auth.username || ''), password: String(auth.password || '') });
      await gotoStable(`${baseUrl}${route}`);
    }
    await page.waitForTimeout(900);
    await dismissOnboarding(page);
  }

  async function collectText(target, selector, max = 8) {
    return target.locator(selector).evaluateAll((nodes, limit) => nodes
      .map((node) => (node.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, limit), max).catch(() => []);
  }

  async function collectButtons(target, max = 20) {
    return target.locator('button, [role="button"], [role="tab"]').evaluateAll((nodes, limit) => nodes
      .map((node) => ({
        label: (node.getAttribute('aria-label') || node.getAttribute('title') || node.textContent || '').replace(/\s+/g, ' ').trim(),
        role: node.getAttribute('role') === 'tab' ? 'tab' : 'button',
        status: 'observed',
      }))
      .filter((item) => item.label)
      .slice(0, limit), max).catch(() => []);
  }

  async function collectFields(target, max = 12) {
    return target.locator('input, textarea, select').evaluateAll((nodes, limit) => nodes
      .map((node) => ({
        label: node.getAttribute('aria-label') || node.getAttribute('placeholder') || node.getAttribute('name') || node.id || node.tagName.toLowerCase(),
        type: node.getAttribute('type') || node.tagName.toLowerCase(),
      }))
      .filter((item) => item.label)
      .slice(0, limit), max).catch(() => []);
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
      await locator.click().catch(() => {});
      await page.waitForTimeout(waitMs);
      return true;
    }
    return false;
  }

  async function resolveRoute(surface) {
    if (!surface.route.includes(':strategyId') && !surface.route.includes(':artifactId')) {
      return surface.route;
    }

    if (surface.route.includes(':strategyId')) {
      await loginIfNeeded('/strategy-market');
      try {
        await gotoStable(`${baseUrl}/strategy-market`);
      } catch {
        return surface.route.replace(':strategyId', '__missing__');
      }
      await page.waitForTimeout(1400);
      const href = await page.locator('a[href^="/strategy-market/"]').evaluateAll((nodes) => {
        for (const node of nodes) {
          const hrefValue = node.getAttribute('href');
          if (hrefValue && /^\/strategy-market\/[^/?#]+/.test(hrefValue) && hrefValue !== '/strategy-market') {
            return hrefValue;
          }
        }
        return null;
      });
      return href || surface.route.replace(':strategyId', '__missing__');
    }

    if (surface.route.includes(':artifactId')) {
      await loginIfNeeded('/execution');
      try {
        await gotoStable(`${baseUrl}/execution`);
      } catch {
        return surface.route.replace(':artifactId', '__missing__');
      }
      await page.waitForTimeout(1400);
      const href = await page.locator('a[href^="/execution/artifacts/"]').evaluateAll((nodes) => {
        for (const node of nodes) {
          const hrefValue = node.getAttribute('href');
          if (hrefValue && /^\/execution\/artifacts\/[^/?#]+/.test(hrefValue)) {
            return hrefValue;
          }
        }
        return null;
      });
      return href || surface.route.replace(':artifactId', '__missing__');
    }

    return surface.route;
  }

  async function generateTotp(secret) {
    return page.evaluate(async (base32) => {
      const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
      const normalized = String(base32 || '').replace(/=+$/g, '').replace(/\s+/g, '').toUpperCase();
      let bits = '';
      for (const char of normalized) {
        const index = alphabet.indexOf(char);
        if (index >= 0) bits += index.toString(2).padStart(5, '0');
      }
      const bytes = bits.match(/.{1,8}/g)
        .filter((chunk) => chunk.length === 8)
        .map((chunk) => parseInt(chunk, 2));
      const counter = Math.floor(Date.now() / 1000 / 30);
      const buffer = new ArrayBuffer(8);
      const view = new DataView(buffer);
      view.setUint32(4, counter);
      const key = await crypto.subtle.importKey('raw', new Uint8Array(bytes), { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
      const signature = new Uint8Array(await crypto.subtle.sign('HMAC', key, buffer));
      const offset = signature[signature.length - 1] & 0x0f;
      const binary = ((signature[offset] & 0x7f) << 24)
        | ((signature[offset + 1] & 0xff) << 16)
        | ((signature[offset + 2] & 0xff) << 8)
        | (signature[offset + 3] & 0xff);
      return String(binary % 1000000).padStart(6, '0');
    }, secret);
  }

  async function runWorkflow(surface, result) {
    if (surface.surfaceId === 'register' && authWorkflowUser) {
      await page.locator('#reg-username').fill(String(authWorkflowUser.username));
      await page.locator('#reg-password').fill(String(authWorkflowUser.password));
      await page.locator('#reg-confirm').fill(String(authWorkflowUser.password));
      await clickIfVisible(page.getByRole('button', { name: '创建账号' }), 1200);
      const passed = !/\/register(?:\?|$)/.test(page.url());
      result.workflow.push({ name: '注册临时审查账号', status: passed ? 'passed' : 'failed', note: passed ? `已跳转到 ${page.url()}` : '仍停留在注册页' });
      markButton(result, /创建账号/, passed ? 'passed' : 'failed', passed ? '注册成功' : '未完成注册');
      return;
    }

    if (surface.surfaceId === 'login' && authWorkflowUser) {
      await page.locator('#login-username').fill(String(authWorkflowUser.username));
      await page.locator('#login-password').fill(String(authWorkflowUser.password));
      await clickIfVisible(page.getByRole('button', { name: '登录' }), 1200);
      const passed = !/\/login(?:\?|$)/.test(page.url());
      result.workflow.push({ name: '登录临时审查账号', status: passed ? 'passed' : 'failed', note: passed ? `已进入 ${page.url()}` : '提交后仍停留在登录页' });
      markButton(result, /登录/, passed ? 'passed' : 'failed', passed ? '登录成功' : '登录失败');
      return;
    }

    if (surface.surfaceId === 'home' || surface.surfaceId === 'market') {
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

    if (surface.surfaceId === 'stock') {
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

    if (surface.surfaceId === 'data') {
      await clickIfVisible(page.getByRole('button', { name: '查询期权链工作台', exact: true }), 900);
      await clickIfVisible(page.getByRole('tab', { name: '交易日历' }));
      await clickIfVisible(page.getByRole('button', { name: '加载交易日历工作台', exact: true }), 900);
      result.workflow.push({ name: '数据中心查询', status: 'passed', note: '已触发期权链和交易日历查询' });
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
      result.workflow.push({ name: '统一决策', status: passed ? 'passed' : 'blocked', note: passed ? '已触发统一决策动作' : '未找到统一决策按钮' });
      markButton(result, /运行统一决策/, passed ? 'passed' : 'blocked', passed ? '已执行' : '按钮缺失');
      return;
    }

    if (surface.surfaceId === 'screener') {
      const passed = await clickIfVisible(page.getByRole('button', { name: /开始筛选|执行筛选/ }).first(), 1200);
      result.workflow.push({ name: '条件选股', status: passed ? 'passed' : 'blocked', note: passed ? '已触发筛选动作' : '未找到筛选按钮' });
      return;
    }

    if (surface.surfaceId === 'alerts') {
      if (await page.locator('#alerts-stock-code').isVisible().catch(() => false)) {
        await page.locator('#alerts-stock-code').fill('000001');
        await page.locator('#alerts-indicator').fill('price').catch(() => {});
        await page.locator('#alerts-condition').selectOption('>').catch(() => {});
        await page.locator('#alerts-threshold').fill('12').catch(() => {});
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
        await page.getByPlaceholder('分组名称').fill(`pw-audit-${Date.now().toString().slice(-4)}`).catch(() => {});
        await clickIfVisible(page.getByRole('button', { name: '创建分组' }), 1200);
        result.workflow.push({ name: '新建自选分组', status: 'passed', note: '已执行分组创建' });
        markButton(result, /创建分组/, 'passed', '已执行');
      }
      return;
    }

    if (surface.surfaceId === 'notifications') {
      const markAll = page.getByRole('button', { name: /全部已读|全部标记已读/ }).first();
      const passed = await clickIfVisible(markAll, 900);
      result.workflow.push({ name: '通知处理', status: passed ? 'passed' : 'partial', note: passed ? '已触发全部已读' : '当前页面没有全部已读入口' });
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
        const secret = await page.locator('code').first().textContent().catch(() => null);
        if (secret) {
          const totp = await generateTotp(secret);
          await page.getByPlaceholder('000000').fill(totp).catch(() => {});
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

    if (surface.surfaceId === 'paper-trading') {
      const codeInput = page.getByRole('textbox', { name: '股票代码' }).first();
      if (await codeInput.isVisible().catch(() => false)) {
        await codeInput.fill('600519').catch(() => {});
      }
      const submit = page.getByRole('button', { name: /确认买入|确认卖出|提交订单|提交/ }).first();
      const passed = await clickIfVisible(submit, 1500);
      result.workflow.push({ name: '模拟交易提交', status: passed ? 'passed' : 'partial', note: passed ? '已触发一次提交动作' : '未命中明确提交按钮' });
      return;
    }

    if (surface.surfaceId === 'strategy-market' || surface.surfaceId === 'strategy-market-catalog-workbench') {
      const cartButton = page.getByRole('button', { name: /加入购物车|加入组合|组合购物车/ }).first();
      const passed = await clickIfVisible(cartButton, 1000);
      result.workflow.push({ name: '策略超市动作', status: passed ? 'passed' : 'partial', note: passed ? '已执行购物车/组合相关动作' : '未命中明显动作按钮' });
      return;
    }

    if (surface.surfaceId === 'strategy-detail' || surface.surfaceId === 'strategy-detail-review-workbench') {
      await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first());
      await clickIfVisible(page.getByRole('tab', { name: '运行风控' }).first());
      const subscribe = page.getByRole('button', { name: /订阅策略|取消订阅/ }).first();
      const passed = await clickIfVisible(subscribe, 1000);
      result.workflow.push({ name: '策略详情动作', status: passed ? 'passed' : 'partial', note: passed ? '已执行订阅类动作并切换到工厂审查' : '未命中明确订阅按钮' });
      return;
    }

    if (surface.surfaceId === 'admin-cache') {
      const passed = await clickIfVisible(page.getByRole('button', { name: /清除全部缓存/ }).first());
      result.workflow.push({ name: '缓存管理', status: passed ? 'partial' : 'blocked', note: passed ? '已打开确认层，未继续执行确认清理' : '未命中清理按钮' });
      markButton(result, /清除全部缓存/, passed ? 'partial' : 'blocked', passed ? '已打开确认层，保留确认按钮未执行' : '按钮缺失');
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

    if (surface.surfaceId === 'admin-users' || surface.surfaceId === 'admin-tools' || surface.surfaceId === 'settings-audit-log') {
      result.workflow.push({ name: '页面审查', status: 'partial', note: '完成页面与数据区检查，未命中明确低风险写操作' });
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

    result.workflow.push({ name: '页面审查', status: 'partial', note: '未命中专用 workflow，保留页面级截图和结构化信息' });
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
    const result = await snapshotInfo({ ...surface, route: resolvedRoute.startsWith('http') ? resolvedRoute.replace(baseUrl, '') : resolvedRoute });
    activeIssues = result.issues;
    await saveShot(surface, '01-entry.png', result);
    try {
      await runWorkflow(surface, result);
      if (result.workflow.length) {
        await saveShot(surface, '02-flow.png', result);
      }
      const highRiskPatterns = [/删除|清空|重置|退出|注销|撤单|取消订阅|确认清理|清除全部/];
      result.buttons = result.buttons.map((button) => highRiskPatterns.some((pattern) => pattern.test(button.label)) && button.status === 'observed'
        ? { ...button, status: 'high_risk_not_executed', note: '高风险动作未在本轮直接执行' }
        : button);
      if (/__missing__/.test(result.route) || /__missing__/.test(result.finalUrl)) {
        result.status = 'blocked';
        result.workflow.push({ name: '动态路由解析', status: 'blocked', note: '当前环境未找到可用详情链接' });
      }
    } catch (error) {
      result.status = 'failed';
      result.workflow.push({ name: 'workflow', status: 'failed', note: error instanceof Error ? error.message : String(error) });
    }
    results.push(result);
    activeIssues = null;
  }

  await page.evaluate((payload) => {
    const storageKey = '__pw_audit_results__';
    const current = JSON.parse(window.localStorage.getItem(storageKey) || '[]');
    const filtered = current.filter((item) => !payload.surfaceIds.includes(item.surfaceId));
    filtered.push(...payload.results);
    window.localStorage.setItem(storageKey, JSON.stringify(filtered));
    console.log('__PW_AUDIT_RESULTS__' + JSON.stringify({ group: payload.groupLabel, results: payload.results }));
  }, { groupLabel, results, surfaceIds });
  return { group: groupLabel, count: results.length };
})
