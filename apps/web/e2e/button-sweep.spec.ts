import { expect, test, type Page } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertNoHorizontalOverflow,
  assertProtectedShell,
  createPageIssueCollector,
  dismissOnboarding,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';

test.setTimeout(240_000);

type SweepRoute = {
  name: string;
  path: string;
  heading?: string | RegExp;
  allowEmptyTargets?: boolean;
  allowApi5xx?: RegExp[];
  allowConsoleErrors?: RegExp[];
  allowPageErrors?: RegExp[];
  allowRequestFailures?: RegExp[];
  settleDelayMs?: number;
};

type RawSweepTarget = {
  context: string;
  scanId: number;
  role: 'button' | 'tab';
  label: string;
};

type SweepTarget = RawSweepTarget & {
  key: string;
};

type IssueCollector = ReturnType<typeof createPageIssueCollector>;

type IssueSnapshot = {
  api5xx: number;
  httpErrors: number;
  consoleErrors: number;
  pageErrors: number;
  requestFailures: number;
};

const ROUTES: SweepRoute[] = [
  { name: '首页', path: '/', settleDelayMs: 1_400 },
  { name: '行情看板', path: '/market?code=600519', heading: /贵州茅台|600519/ },
  { name: '个股详情', path: '/stock?code=600519', heading: /股票详情|\d{6}/ },
  { name: '基本面分析', path: '/fundamental?code=600519', heading: /基本面分析(?:工作台)?/ },
  { name: '技术分析', path: '/technical?code=600519', heading: /技术分析(?:工作台)?/ },
  { name: '资金流向', path: '/fund-flow?code=600519', heading: /资金流向(?:工作台)?/ },
  { name: '情绪分析', path: '/sentiment?code=600519', heading: /情绪分析(?:工作台)?/ },
  { name: '研报公告', path: '/research?code=600519', heading: /研究工作台|研报公告/ },
  { name: '估值分析', path: '/valuation?code=600519', heading: /估值分析(?:工作台)?/ },
  { name: '回测分析', path: '/backtest?code=600519', heading: /回测分析(?:工作台)?/ },
  { name: '因子研究', path: '/factor', heading: /因子研究(?:工作台)?/ },
  { name: '因子分析', path: '/factor-analysis?code=600519', heading: /因子洞察工作台|因子分析/ },
  { name: '事件工作台', path: '/events?code=600519&days=7&type=all', heading: /事件日历(?:工作台)?/ },
  { name: '执行中心', path: '/execution?code=600519', heading: /执行工作台|执行中心/ },
  { name: '绩效中心', path: '/performance?mode=account&days=30', heading: /绩效复盘工作台|绩效中心/ },
  { name: '条件选股', path: '/screener', heading: '条件选股' },
  { name: '模拟交易', path: '/paper-trading?code=600519', heading: /模拟交易(?:工作台)?/ },
  { name: '投资组合', path: '/portfolio', heading: /组合管理工作台|投资组合|组合管理/ },
  { name: '风险分析', path: '/risk?lookbackDays=252', heading: /风险分析(?:工作台)?/ },
  { name: '告警中心', path: '/alerts?code=600519', heading: /告警中心(?:工作台)?/ },
  { name: '通知中心', path: '/notifications', heading: /通知中心/ },
  { name: '统一决策', path: '/decision?code=600519', heading: '统一决策工作台' },
  { name: '智能助手', path: '/assistant?code=600519', heading: /AI 中心|AI 深度诊断报告生成器/ },
  { name: 'AI 对话', path: '/chat', heading: /AI 中心|AI 对话/ },
  { name: '智能搜索', path: '/search?code=600519', heading: '智能搜索' },
  { name: '数据中心', path: '/data?code=600519', heading: '数据中心' },
  { name: '宏观分析', path: '/macro', heading: /宏观经济数据分析/ },
  { name: '期权分析', path: '/options?underlying=510050', heading: /期权全景分析/ },
  { name: '我的自选', path: '/watchlist', heading: /自选股工作台|我的自选/ },
  { name: '用户中心', path: '/user', heading: /用户中心(?:工作台)?/ },
  { name: '设置中心', path: '/settings', heading: '设置中心' },
  { name: '安全设置', path: '/settings/security', heading: /安全设置/, allowEmptyTargets: true },
  { name: '审计日志', path: '/settings/audit-log', heading: /操作审计日志/ },
  { name: '策略工作台', path: '/strategy', heading: '策略工作台' },
  { name: '策略超市', path: '/strategy-market', heading: /先看筛选结果|策略超市/ },
  { name: '管理后台', path: '/admin', heading: '管理后台概览', allowEmptyTargets: true },
  { name: 'MCP 工具页', path: '/admin/tools', heading: /MCP 工具仪表盘/, allowEmptyTargets: true },
  { name: '缓存管理', path: '/admin/cache', heading: /缓存管理/, allowEmptyTargets: true },
  { name: '死信队列', path: '/admin/dead-letters', heading: /死信队列/, allowEmptyTargets: true },
  { name: '用户管理', path: '/admin/users', heading: /用户管理/, allowEmptyTargets: true },
  { name: '策略模板中心', path: '/workspace-templates', heading: '模板中心' },
  { name: '技能中心', path: '/skills', heading: '技能中心' },
];

const GLOBAL_SKIP_PATTERNS: RegExp[] = [
  /展开导航|收起导航|打开 Copilot|收起 Copilot|通知/,
  /当前: .*点击切换|切换左侧导航栏显示状态|打开右侧 Copilot 面板/,
  /跳转到|打开自选股|查看工作区模板与编排入口/,
  /新会话|去配置模型/,
  /打开重点股票研究|总结账户表现、持仓和待处理订单|刷新风险汇总和 VaR 数据/,
  /先选择一个组合，再评估配置和风险/,
  /订阅当前事件|取消事件订阅|订阅当前股票事件|取消当前股票事件订阅/,
  /扩大到近\s*\d+\s*天|载入一笔示例执行参数|刷新当前账户绩效数据/,
  /^(GET|POST|PUT|DELETE|PATCH)\s+\/api\//,
  /总结.*信号|给我一个下一步操作建议|把当前页面数据整理成行动清单/,
  /把当前个股页整理成一个复盘清单|结合技术面、资金流和估值给出短中期观察重点/,
  /^总结 /,
  /^把/,
  /^结合/,
  /^对结果按行业做分类汇总$/,
  /^示例[:：]/,
  /退出|登出|注销/,
  /删除|移除|清空|清除|重置/,
  /^(研究布局|交易布局|专注布局|单栏|双栏)$/,
  /保存当前视图|保存布局|保存模板/,
  /^(刷新|加载|提交|同步|保存|处理)中(?:\.{3}|…)?$/,
  /启用 2FA|关闭 2FA|恢复默认/,
  /创建策略组合|创建账户|新建|创建/,
  /提交执行|取消订单|同步持仓|更新价格/,
  /全部已读|选中当前筛选|取消全选当前筛选/,
  /加入组合|订阅策略|取消订阅/,
  /生成投资报告|执行工作流/,
  /取消关注|加入自选|移出自选/,
  /返回登录|退出登录/,
];

const ROUTE_SKIP_PATTERNS: Record<string, RegExp[]> = {
  '/settings/security': [/打开导航|收起导航|打开 Copilot|收起 Copilot/],
  '/research': [/拉取云端|立即同步|注入任务|记入任务|切换状态|清理已完成|拖拽调整子面板宽度/],
  '/backtest': [/运行回测|批量回测|高级选项|先看结果总览|再看净值曲线|对比历史结果|最后看批量回测/],
  '/factor': [/生成候选|运行验证|立即运行一次|加载状态|执行回放/],
};

async function ensureRouteReady(page: Page, route: SweepRoute) {
  await openProtectedPage(page, route.path);
  await assertProtectedShell(page);
  if (route.heading) {
    await expect(page.getByRole('heading', { name: route.heading }).first()).toBeVisible();
  }
  await waitForSettledUi(page, route.settleDelayMs ?? 1_000);
  await assertNoHorizontalOverflow(page);
}

async function collectRawTargets(page: Page): Promise<RawSweepTarget[]> {
  return page.evaluate(() => {
    const isVisible = (element: HTMLElement) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        style.opacity !== '0'
      );
    };

    const getLabel = (element: HTMLElement) => {
      const text = [
        element.getAttribute('aria-label'),
        element.getAttribute('title'),
        element.innerText,
        element.textContent,
      ]
        .map((value) => value?.replace(/\s+/g, ' ').trim() ?? '')
        .find(Boolean);

      return text ?? '';
    };

    const getContext = (element: HTMLElement, label: string) => {
      const seen = new Set<HTMLElement>();
      const candidates = [
        element.closest('section'),
        element.closest('article'),
        element.closest('form'),
        element.closest('[role="tabpanel"]'),
        element.parentElement,
        element.parentElement?.parentElement ?? null,
        element.parentElement?.parentElement?.parentElement ?? null,
      ].filter((value): value is HTMLElement => value instanceof HTMLElement);

      for (const candidate of candidates) {
        if (seen.has(candidate)) {
          continue;
        }

        seen.add(candidate);
        const heading = candidate.querySelector('h1, h2, h3, h4, h5, h6, [role="heading"], legend');
        const text = heading?.textContent?.replace(/\s+/g, ' ').trim() ?? '';

        if (text && text !== label) {
          return text.slice(0, 60);
        }
      }

      return '';
    };

    const nodes = Array.from(document.querySelectorAll('button, [role="button"], [role="tab"]'));
    const items: RawSweepTarget[] = [];
    let scanId = 0;

    for (const node of nodes) {
      if (!(node instanceof HTMLElement)) {
        continue;
      }

      if (!isVisible(node)) {
        continue;
      }

      if (node.closest('[hidden], [aria-hidden="true"]')) {
        continue;
      }

      const aside = node.closest('aside');
      if (aside instanceof HTMLElement && /AI Copilot/.test(aside.innerText)) {
        continue;
      }

      if (node.hasAttribute('disabled') || node.getAttribute('aria-disabled') === 'true') {
        continue;
      }

      const label = getLabel(node);
      if (!/[A-Za-z0-9\u4e00-\u9fff]/.test(label)) {
        continue;
      }

      const context = getContext(node, label);
      const role = node.getAttribute('role') === 'tab' ? 'tab' : 'button';
      node.setAttribute('data-pw-scan-id', String(scanId));
      items.push({ scanId, role, label, context });
      scanId += 1;
    }

    return items;
  });
}

function normalizeLabel(label: string) {
  return label.replace(/\s+/g, ' ').trim();
}

function shouldSkipTarget(route: SweepRoute, target: RawSweepTarget) {
  const label = normalizeLabel(target.label);
  const routePath = new URL(route.path, 'http://127.0.0.1').pathname;
  const patterns = [...GLOBAL_SKIP_PATTERNS, ...(ROUTE_SKIP_PATTERNS[routePath] ?? [])];
  if (patterns.some((pattern) => pattern.test(label))) {
    return true;
  }

  if (/^\d{6}$/.test(label)) {
    return true;
  }

  return label.length > 10 && /(当前|页面|资讯|个股|信号|建议|整理|核验|值得|继续|短中期|行动清单|行业|分类汇总|账户表现|持仓|订单|VaR|研究)/.test(label);
}

function dedupeTargets(route: SweepRoute, targets: RawSweepTarget[]): SweepTarget[] {
  const seen = new Set<string>();
  const deduped: SweepTarget[] = [];

  for (const target of targets) {
    if (shouldSkipTarget(route, target)) {
      continue;
    }

    const label = normalizeLabel(target.label);
    const context = normalizeLabel(target.context);
    const key = `${target.role}:${label}:${context}`;
    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    deduped.push({ ...target, context, label, key });
  }

  return deduped;
}

async function collectSweepTargets(page: Page, route: SweepRoute) {
  const rawTargets = await collectRawTargets(page);
  return dedupeTargets(route, rawTargets);
}

async function clickSweepTarget(page: Page, route: SweepRoute, target: SweepTarget) {
  let currentTargets = await collectSweepTargets(page, route);
  let currentTarget = currentTargets.find((candidate) => candidate.key === target.key);

  if (!currentTarget) {
    await ensureRouteReady(page, route);
    currentTargets = await collectSweepTargets(page, route);
    currentTarget = currentTargets.find((candidate) => candidate.key === target.key);
  }

  if (!currentTarget) {
    const labelMatches = currentTargets.filter((candidate) => (
      candidate.role === target.role && candidate.label === target.label
    ));
    if (labelMatches.length === 1) {
      [currentTarget] = labelMatches;
    }
  }

  expect(currentTarget, `${route.name} 丢失按钮: ${target.label}`).toBeTruthy();

  const locator = page.locator(`[data-pw-scan-id="${currentTarget?.scanId ?? -1}"]`);
  await locator.scrollIntoViewIfNeeded();

  const popupPromise = page.waitForEvent('popup', { timeout: 1_500 }).catch(() => null);
  await locator.click({ timeout: 12_000 });
  const popup = await popupPromise;
  await popup?.close().catch(() => {});

  await waitForSettledUi(page, route.settleDelayMs ?? 1_000);
  await dismissOnboarding(page).catch(() => {});
}

function takeIssueSnapshot(collector: IssueCollector): IssueSnapshot {
  return {
    api5xx: collector.api5xx.length,
    httpErrors: collector.httpErrors.length,
    consoleErrors: collector.consoleErrors.length,
    pageErrors: collector.pageErrors.length,
    requestFailures: collector.requestFailures.length,
  };
}

function assertNoNewCriticalIssues(
  collector: IssueCollector,
  snapshot: IssueSnapshot,
  route: SweepRoute,
) {
  assertNoCriticalPageIssues({
    api5xx: collector.api5xx.slice(snapshot.api5xx),
    httpErrors: collector.httpErrors.slice(snapshot.httpErrors),
    consoleErrors: collector.consoleErrors.slice(snapshot.consoleErrors),
    pageErrors: collector.pageErrors.slice(snapshot.pageErrors),
    requestFailures: collector.requestFailures.slice(snapshot.requestFailures),
    dispose: () => {},
  }, {
    allowApi5xx: route.allowApi5xx,
    allowConsoleErrors: route.allowConsoleErrors,
    allowPageErrors: route.allowPageErrors,
    allowRequestFailures: route.allowRequestFailures,
  });
}

for (const route of ROUTES) {
  test(`button sweep: ${route.name}`, async ({ page }) => {
    page.on('dialog', (dialog) => dialog.dismiss().catch(() => {}));
    const collector = createPageIssueCollector(page);

    try {
      await ensureRouteReady(page, route);
      const firstPassTargets = await collectSweepTargets(page, route);
      await ensureRouteReady(page, route);
      const secondPassTargets = await collectSweepTargets(page, route);
      const stableKeys = new Set(secondPassTargets.map((target) => target.key));
      const targets = firstPassTargets.filter((target) => stableKeys.has(target.key));

      console.log(`BUTTON_SWEEP_ROUTE ${route.name} ${targets.length}`);

      if (route.allowEmptyTargets) {
        expect(targets.length, `${route.name} 稳定按钮数量异常`).toBeGreaterThanOrEqual(0);
      } else {
        expect(targets.length, `${route.name} 没有可点击按钮或 tab`).toBeGreaterThan(0);
      }

      for (const target of targets) {
        await test.step(target.label, async () => {
          await ensureRouteReady(page, route);
          const snapshot = takeIssueSnapshot(collector);

          await clickSweepTarget(page, route, target);

          expect(new URL(page.url()).pathname, `${route.name} ${target.label} 点击后跳回登录页`).not.toBe('/login');
          await assertNoHorizontalOverflow(page);
          assertNoNewCriticalIssues(collector, snapshot, route);
        });
      }
    } finally {
      collector.dispose();
    }
  });
}
