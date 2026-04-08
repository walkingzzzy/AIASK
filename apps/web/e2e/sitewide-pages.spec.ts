import { expect, test, type Page } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertNoHorizontalOverflow,
  assertProtectedShell,
  createPageIssueCollector,
  dismissOnboarding,
  expectRouteMatch,
  loginAsConfigured,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';

test.describe.configure({ mode: 'serial' });
test.setTimeout(300_000);

type RouteSpec = {
  name: string;
  path: string;
  resolvePath?: (page: Page) => Promise<string>;
  public?: boolean;
  allowAuthenticatedRedirect?: boolean;
  redirectPath?: string;
  verify: (page: Page) => Promise<void>;
};

const ROUTES: RouteSpec[] = [
  {
    name: '首页',
    path: '/',
    verify: async (page) => {
      await expect(page).toHaveTitle(/AIASK|市场概览/);
      await expect(page.getByRole('link', { name: /行情看板|行情/ }).first()).toBeVisible();
      await expect(page.getByRole('link', { name: /自选股|自选/ }).first()).toBeVisible();
    },
  },
  {
    name: '行情看板',
    path: '/market',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: /贵州茅台|600519/ }).first()).toBeVisible();
      await expect(page.getByRole('tab', { name: '基础行情' })).toBeVisible();
    },
  },
  {
    name: '个股详情',
    path: '/stock',
    verify: async (page) => {
      await expect(page.getByRole('textbox', { name: '股票代码' })).toHaveValue(/\d{6}/);
      await expect(page.getByRole('tab', { name: 'K线图' })).toBeVisible();
    },
  },
  { name: '基本面分析', path: '/fundamental', verify: async (page) => expect(page.getByRole('heading', { name: /基本面分析(?:工作台)?/ })).toBeVisible() },
  { name: '技术分析', path: '/technical', verify: async (page) => expect(page.getByRole('heading', { name: /技术分析(?:工作台)?/ })).toBeVisible() },
  {
    name: '资金流向',
    path: '/fund-flow',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: /资金流向(?:工作台)?/ })).toBeVisible();
      await expect(page.getByRole('tab', { name: '个股资金流' })).toBeVisible();
    },
  },
  { name: '情绪分析', path: '/sentiment', verify: async (page) => expect(page.getByRole('heading', { name: /情绪分析(?:工作台)?/ })).toBeVisible() },
  { name: '研报公告', path: '/research', verify: async (page) => expect(page.getByRole('heading', { name: /研究工作台|研报公告/ })).toBeVisible() },
  { name: '估值分析', path: '/valuation', verify: async (page) => expect(page.getByRole('heading', { name: /估值分析(?:工作台)?/ })).toBeVisible() },
  { name: '回测分析', path: '/backtest', verify: async (page) => expect(page.getByRole('heading', { name: /回测分析(?:工作台)?/ })).toBeVisible() },
  { name: '因子研究', path: '/factor', verify: async (page) => expect(page.getByRole('heading', { name: /因子研究(?:工作台)?/ })).toBeVisible() },
  { name: '因子分析', path: '/factor-analysis', verify: async (page) => expect(page.getByRole('heading', { name: /因子洞察工作台|因子分析/ })).toBeVisible() },
  {
    name: '事件工作台',
    path: '/events',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '事件日历工作台' }).first()).toBeVisible();
      await expect(page.getByText('订阅标的', { exact: true }).first()).toBeVisible();
    },
  },
  {
    name: '执行中心',
    path: '/execution',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '执行工作台' })).toBeVisible();
      await expect(page.getByRole('button', { name: '提交执行' })).toBeVisible();
    },
  },
  {
    name: '绩效中心',
    path: '/performance',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '绩效复盘工作台' })).toBeVisible();
      await expect(page.getByRole('tab', { name: /账户绩效|组合归因/ }).first()).toBeVisible();
    },
  },
  {
    name: '条件选股',
    path: '/screener',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '条件选股' })).toBeVisible();
      await expect(page.getByRole('button', { name: /开始筛选|执行筛选/ }).first()).toBeVisible();
    },
  },
  { name: '模拟交易', path: '/paper-trading', verify: async (page) => expect(page.getByRole('heading', { name: /模拟交易(?:工作台)?/ })).toBeVisible() },
  { name: '投资组合', path: '/portfolio', verify: async (page) => expect(page.getByRole('heading', { name: /组合管理工作台|投资组合|组合管理/ })).toBeVisible() },
  { name: '风险分析', path: '/risk', verify: async (page) => expect(page.getByRole('heading', { name: /风险分析(?:工作台)?/ })).toBeVisible() },
  { name: '告警中心', path: '/alerts', verify: async (page) => expect(page.getByRole('heading', { name: /告警中心(?:工作台)?/ })).toBeVisible() },
  { name: '通知中心', path: '/notifications', verify: async (page) => expect(page.getByRole('heading', { name: /通知中心/ })).toBeVisible() },
  {
    name: '统一决策',
    path: '/decision',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '统一决策工作台' })).toBeVisible();
      await expect(page.getByRole('button', { name: '运行统一决策' }).first()).toBeVisible();
    },
  },
  {
    name: '智能助手',
    path: '/assistant',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: /AI 中心|AI 深度诊断报告生成器/ })).toBeVisible();
      await expect(page.getByRole('textbox', { name: '股票代码' })).toBeVisible();
    },
  },
  {
    name: 'AI 对话',
    path: '/chat',
    allowAuthenticatedRedirect: true,
    redirectPath: '/assistant',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: /AI 中心|AI 对话/ })).toBeVisible();
      await expect(page.getByRole('textbox', { name: '股票代码' })).toBeVisible();
    },
  },
  {
    name: '智能搜索',
    path: '/search',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '智能搜索' })).toBeVisible();
      await expect(page.getByRole('tab', { name: /语义搜索|相似股票|K 线搜索/ }).first()).toBeVisible();
    },
  },
  {
    name: '数据中心',
    path: '/data',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '数据中心' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '期权链' })).toBeVisible();
    },
  },
  {
    name: '模板中心',
    path: '/workspace-templates',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '模板中心' })).toBeVisible();
      await expect(page.getByRole('button', { name: '执行工作流' })).toBeVisible();
    },
  },
  { name: '技能中心', path: '/skills', verify: async (page) => expect(page.getByRole('heading', { name: '技能中心' })).toBeVisible() },
  { name: '用户中心', path: '/user', verify: async (page) => expect(page.getByRole('heading', { name: /用户中心(?:工作台)?/ })).toBeVisible() },
  {
    name: '设置中心',
    path: '/settings',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '设置中心' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '账户信息' })).toBeVisible();
    },
  },
  { name: '安全设置', path: '/settings/security', verify: async (page) => expect(page.getByRole('heading', { name: /安全设置/ })).toBeVisible() },
  { name: '审计日志', path: '/settings/audit-log', verify: async (page) => expect(page.getByRole('heading', { name: /操作审计日志/ })).toBeVisible() },
  { name: '策略工作台', path: '/strategy', verify: async (page) => expect(page.getByRole('heading', { name: '策略工作台' })).toBeVisible() },
  {
    name: '策略超市',
    path: '/strategy-market',
    verify: async (page) => {
      await expect(page.getByText('Strategy Workspace')).toBeVisible();
      await expect(page.getByRole('heading', { name: /先看筛选结果|订阅、组合和工厂动作/ }).first()).toBeVisible();
    },
  },
  {
    name: '策略详情页',
    path: '/strategy-market',
    resolvePath: resolveFirstStrategyDetailPath,
    verify: async (page) => {
      await expect
        .poll(async () => {
          if (await page.getByText('Strategy Workspace').isVisible().catch(() => false)) return 'detail';
          if (await page.getByText('策略不存在或已下架').isVisible().catch(() => false)) return 'missing';
          if (await page.getByText('策略详情暂时无法加载').isVisible().catch(() => false)) return 'error';
          return null;
        }, { timeout: 20_000, intervals: [250, 500, 1_000] })
        .not.toBeNull();
      await expect(page.getByRole('link', { name: /返回策略超市/ }).first()).toBeVisible();
    },
  },
  { name: '宏观页面', path: '/macro', verify: async (page) => expect(page.getByRole('heading', { name: /宏观经济数据分析/ })).toBeVisible() },
  { name: '期权页面', path: '/options', verify: async (page) => expect(page.getByRole('heading', { name: /期权全景分析/ })).toBeVisible() },
  { name: '自选股', path: '/watchlist', verify: async (page) => expect(page.getByRole('heading', { name: '自选股工作台', level: 1 })).toBeVisible() },
  { name: '管理后台', path: '/admin', verify: async (page) => expect(page.getByRole('heading', { name: '管理后台概览' })).toBeVisible() },
  { name: '缓存管理', path: '/admin/cache', verify: async (page) => expect(page.getByRole('heading', { name: /缓存管理/ })).toBeVisible() },
  { name: '死信队列', path: '/admin/dead-letters', verify: async (page) => expect(page.getByRole('heading', { name: /死信队列/ })).toBeVisible() },
  { name: 'MCP 工具页', path: '/admin/tools', verify: async (page) => expect(page.getByRole('heading', { name: /MCP 工具仪表盘/ })).toBeVisible() },
  { name: '用户管理', path: '/admin/users', verify: async (page) => expect(page.getByRole('heading', { name: /用户管理/ })).toBeVisible() },
  {
    name: '执行 Artifact 详情页',
    path: '/execution/artifacts/demo-artifact',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: 'Artifact 详情' })).toBeVisible();
      await expect(page.getByText(/独立查看 artifact 关联的任务/)).toBeVisible();
    },
  },
  {
    name: '登录页',
    path: '/login',
    public: true,
    allowAuthenticatedRedirect: true,
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: /登录后继续查看|账号登录/ }).first()).toBeVisible();
      await expect(page.getByLabel('用户名')).toBeVisible();
      await expect(page.getByLabel(/^密码$/)).toBeVisible();
    },
  },
  {
    name: '注册页',
    path: '/register',
    public: true,
    allowAuthenticatedRedirect: true,
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: /创建你的 AI 股票研究工作台|注册账号/ }).first()).toBeVisible();
      await expect(page.getByLabel('用户名')).toBeVisible();
      await expect(page.getByLabel(/^密码$/)).toBeVisible();
      await expect(page.getByLabel('确认密码')).toBeVisible();
    },
  },
];

async function gotoProtectedRoute(page: Page, path: string) {
  await page.goto(path);
  await waitForSettledUi(page);

  if (new URL(page.url()).pathname === '/login') {
    await openProtectedPage(page, path);
    return;
  }

  await dismissOnboarding(page);
}

async function resolveFirstStrategyDetailPath(page: Page) {
  const tempPage = await page.context().newPage();

  try {
    await openProtectedPage(tempPage, '/strategy-market');
    await assertProtectedShell(tempPage);
    await waitForSettledUi(tempPage, 1_500);

    const detailHref = await tempPage.locator('a[href^="/strategy-market/"]').evaluateAll((nodes) => {
      for (const node of nodes) {
        const href = node.getAttribute('href');
        if (href && /^\/strategy-market\/[^/?#]+(?:\?.*)?$/.test(href) && href !== '/strategy-market') {
          return href;
        }
      }
      return null;
    });

    expect(detailHref, '策略详情链接不能为空').toBeTruthy();
    return detailHref!;
  } finally {
    await tempPage.close();
  }
}

test('should load sitewide routes without layout or runtime regressions', async ({ page }) => {
  const failures: string[] = [];
  expect(ROUTES).toHaveLength(46);

  await loginAsConfigured(page, '/');
  const context = page.context();
  await page.close();

  for (const route of ROUTES) {
    await test.step(route.name, async () => {
      const routePage = await context.newPage();
      const collector = createPageIssueCollector(routePage);

      try {
        const targetPath = route.resolvePath ? await route.resolvePath(routePage) : route.path;

        if (route.public) {
          await routePage.goto(targetPath);
          await waitForSettledUi(routePage);
        } else {
          await gotoProtectedRoute(routePage, targetPath);
          await assertProtectedShell(routePage);
        }

        const pathname = new URL(routePage.url()).pathname;
        if (route.public && route.allowAuthenticatedRedirect && pathname !== targetPath) {
          expect(['/market', '/']).toContain(pathname);
          await assertProtectedShell(routePage);
        } else if (!route.public && route.allowAuthenticatedRedirect && route.redirectPath && pathname !== targetPath) {
          expect(pathname).toBe(route.redirectPath);
          await route.verify(routePage);
        } else {
          await expectRouteMatch(routePage, targetPath);
          await route.verify(routePage);
        }
        await assertNoHorizontalOverflow(routePage);
      } catch (error) {
        failures.push(`${route.name}: ${error instanceof Error ? error.message : String(error)}`);
      }

      try {
        assertNoCriticalPageIssues(collector);
      } catch (error) {
        failures.push(`${route.name} 异常: ${error instanceof Error ? error.message : String(error)}`);
      } finally {
        collector.dispose();
        await routePage.close();
      }
    });
  }

  expect(failures, failures.join('\n')).toEqual([]);
});
