import { expect, type Page } from '@playwright/test';
import type { FixtureBundle } from '../contracts';
import { clickVisibleTab, expectAnyVisible, expectTextAny } from './assertions';

type SurfaceAssertion = (page: Page, bundle: FixtureBundle) => Promise<void>;

const assistantAssertion: SurfaceAssertion = async (page) => {
  await expectAnyVisible([
    page.getByRole('heading', { name: /AI 中心|AI 深度诊断报告生成器|AI 对话/ }).first(),
    page.getByRole('textbox', { name: '股票代码' }),
  ]);
};

const strategyDetailAssertion: SurfaceAssertion = async (page) => {
  await expect(page.getByRole('link', { name: /返回策略超市/ }).first()).toBeVisible();
  await expect(page.getByRole('tab', { name: '策略概览' })).toBeVisible();
};

export const ROUTE_ASSERTIONS: Record<string, SurfaceAssertion> = {
  home: async (page) => {
    await expect(page).toHaveTitle(/AIASK|市场概览/);
    await expect(page.getByRole('link', { name: /行情看板|行情/ }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /自选股|自选/ }).first()).toBeVisible();
  },
  market: async (page) => {
    await expect(page.getByRole('heading', { name: /贵州茅台|600519/ }).first()).toBeVisible();
    await expect(page.getByRole('tab', { name: '基础行情' })).toBeVisible();
  },
  stock: async (page) => {
    await expect(page.getByRole('textbox', { name: '股票代码' })).toHaveValue(/\d{6}/);
    await expect(page.getByRole('tab', { name: 'K线图' })).toBeVisible();
  },
  fundamental: async (page) => expect(page.getByRole('heading', { name: /基本面分析(?:工作台)?/ })).toBeVisible(),
  technical: async (page) => expect(page.getByRole('heading', { name: /技术分析(?:工作台)?/ })).toBeVisible(),
  'fund-flow': async (page) => {
    await expect(page.getByRole('heading', { name: /资金流向(?:工作台)?/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: '个股资金流' })).toBeVisible();
  },
  sentiment: async (page) => expect(page.getByRole('heading', { name: /情绪分析(?:工作台)?/ })).toBeVisible(),
  research: async (page) => expect(page.getByRole('heading', { name: /研究工作台|研报公告/ })).toBeVisible(),
  valuation: async (page) => expect(page.getByRole('heading', { name: /估值分析(?:工作台)?/ })).toBeVisible(),
  backtest: async (page) => expect(page.getByRole('heading', { name: /回测分析(?:工作台)?/ })).toBeVisible(),
  factor: async (page) => expect(page.getByRole('heading', { name: /因子研究(?:工作台)?/ })).toBeVisible(),
  'factor-analysis': async (page) => expect(page.getByRole('heading', { name: /因子洞察工作台|因子分析/ })).toBeVisible(),
  events: async (page) => {
    await expect(page.getByRole('heading', { name: '事件日历工作台' }).first()).toBeVisible();
    await expect(page.getByText('订阅标的', { exact: true }).first()).toBeVisible();
  },
  execution: async (page) => {
    await expect(page.getByRole('heading', { name: '执行工作台' })).toBeVisible();
    await expect(page.getByRole('button', { name: '提交执行' })).toBeVisible();
  },
  performance: async (page) => {
    await expect(page.getByRole('heading', { name: '绩效复盘工作台' })).toBeVisible();
    await expect(page.getByRole('tab', { name: /账户绩效|组合归因/ }).first()).toBeVisible();
  },
  screener: async (page) => {
    await expect(page.getByRole('heading', { name: '条件选股' })).toBeVisible();
    await expect(page.getByRole('button', { name: /开始筛选|执行筛选/ }).first()).toBeVisible();
  },
  'paper-trading': async (page) => {
    await expect(page.getByRole('heading', { name: /模拟交易(?:工作台)?/ })).toBeVisible();
    await expect(page.getByText('委托输入与提交流程')).toBeVisible();
  },
  portfolio: async (page) => expect(page.getByRole('heading', { name: /组合管理工作台|投资组合|组合管理/ })).toBeVisible(),
  risk: async (page) => expect(page.getByRole('heading', { name: /风险分析(?:工作台)?/ })).toBeVisible(),
  alerts: async (page) => expect(page.getByRole('heading', { name: /告警中心(?:工作台)?/ })).toBeVisible(),
  notifications: async (page) => expect(page.getByRole('heading', { name: /通知中心/ })).toBeVisible(),
  decision: async (page) => {
    await expect(page.getByRole('heading', { name: '统一决策工作台' })).toBeVisible();
    await expect(page.getByRole('button', { name: '运行统一决策' }).first()).toBeVisible();
  },
  assistant: assistantAssertion,
  chat: assistantAssertion,
  search: async (page) => {
    await expect(page.getByRole('heading', { name: '智能搜索' })).toBeVisible();
    await expect(page.getByRole('tab', { name: /语义搜索|相似股票|K 线搜索/ }).first()).toBeVisible();
  },
  data: async (page) => {
    await expect(page.getByRole('heading', { name: '数据中心' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '期权链' })).toBeVisible();
  },
  'workspace-templates': async (page) => {
    await expect(page.getByRole('heading', { name: '模板中心' })).toBeVisible();
    await expect(page.getByRole('button', { name: '执行工作流' })).toBeVisible();
  },
  skills: async (page) => expect(page.getByRole('heading', { name: '技能中心' })).toBeVisible(),
  user: async (page) => expect(page.getByRole('heading', { name: /用户中心(?:工作台)?/ })).toBeVisible(),
  settings: async (page) => {
    await expect(page.getByRole('heading', { name: '设置中心' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '账户信息' })).toBeVisible();
  },
  'settings-security': async (page) => {
    await expect(page.getByRole('heading', { name: /安全设置/ })).toBeVisible();
    await expect(page.getByText('双因素认证')).toBeVisible();
  },
  'settings-audit-log': async (page) => expect(page.getByRole('heading', { name: /操作审计日志/ })).toBeVisible(),
  strategy: async (page) => expect(page.getByRole('heading', { name: '策略工作台' })).toBeVisible(),
  'strategy-market': async (page) => {
    await expect(page.getByText('Strategy Workspace')).toBeVisible();
    await expect(page.getByRole('heading', { name: /先看筛选结果|订阅、组合和工厂动作/ }).first()).toBeVisible();
  },
  'strategy-detail': strategyDetailAssertion,
  macro: async (page) => expect(page.getByRole('heading', { name: /宏观经济数据分析/ })).toBeVisible(),
  options: async (page) => expect(page.getByRole('heading', { name: /期权全景分析/ })).toBeVisible(),
  watchlist: async (page) => expect(page.getByRole('heading', { name: '自选股工作台', level: 1 })).toBeVisible(),
  admin: async (page) => expect(page.getByRole('heading', { name: '管理后台概览' })).toBeVisible(),
  'admin-cache': async (page) => expect(page.getByRole('heading', { name: /缓存管理/ })).toBeVisible(),
  'admin-dead-letters': async (page) => expect(page.getByRole('heading', { name: /死信队列/ })).toBeVisible(),
  'admin-tools': async (page) => expect(page.getByRole('heading', { name: /MCP 工具仪表盘/ })).toBeVisible(),
  'admin-users': async (page) => expect(page.getByRole('heading', { name: /用户管理/ })).toBeVisible(),
  'execution-artifact-detail': async (page) => {
    await expect(page.getByRole('heading', { name: 'Artifact 详情' })).toBeVisible();
    await expect(page.getByText(/独立查看 artifact 关联的任务/)).toBeVisible();
  },
  login: async (page) => {
    await expect(page.getByRole('heading', { name: /登录账号|账号登录|继续你的行情、研究与交易工作流/ }).first()).toBeVisible();
    await expect(page.getByLabel('用户名')).toBeVisible();
    await expect(page.getByLabel(/^密码$/)).toBeVisible();
  },
  register: async (page) => {
    await expect(page.getByRole('heading', { name: /创建账号|注册账号|先进入核心页面，再逐步补齐个性化配置/ }).first()).toBeVisible();
    await expect(page.getByLabel('用户名')).toBeVisible();
    await expect(page.getByLabel(/^密码$/)).toBeVisible();
    await expect(page.getByLabel('确认密码')).toBeVisible();
  },
  'market-tabs': async (page) => {
    await ROUTE_ASSERTIONS.market(page, {} as FixtureBundle);
    await clickVisibleTab(page, ['涨停板']);
    await expectAnyVisible([
      page.getByText('涨停总数'),
      page.getByText('当前还没有涨停榜单'),
    ]);
    await clickVisibleTab(page, ['板块']);
    await expectAnyVisible([
      page.getByRole('button', { name: '加载行业板块顶部操作', exact: true }),
      page.getByText('板块代码'),
    ]);
    await clickVisibleTab(page, ['指数']);
    await expect(page.getByLabel('指数代码')).toBeVisible();
    await clickVisibleTab(page, ['搜索']);
    await expect(page.getByLabel('搜索关键词')).toBeVisible();
  },
  'stock-analysis-tabs': async (page) => {
    await expect(page.getByRole('textbox', { name: '股票代码' })).toBeVisible();
    await page.getByRole('textbox', { name: '股票代码' }).fill('000001');
    await page.getByRole('button', { name: '立即查询股票', exact: true }).click();
    await expect(page.getByRole('heading', { name: /000001|平安银行/ }).first()).toBeVisible({ timeout: 20_000 });
    await clickVisibleTab(page, ['技术面']);
    await expectTextAny(page, ['MACD', '查询股票后显示技术指标']);
    await clickVisibleTab(page, ['资金流']);
    await expectTextAny(page, ['净流入', '暂无资金流向数据']);
    await clickVisibleTab(page, ['估值']);
    await expectTextAny(page, [/PE|市盈率/, '查询股票后显示估值数据']);
    await clickVisibleTab(page, ['资讯']);
    await expectAnyVisible([
      page.getByRole('heading', { name: '最新资讯' }),
      page.getByText('查询股票后显示相关资讯'),
      page.getByText(/研报|公告|新闻/).first(),
    ]);
  },
  'data-center-tabs': async (page) => {
    await ROUTE_ASSERTIONS.data(page, {} as FixtureBundle);
    await expect(page.getByRole('button', { name: '查询期权链工作台', exact: true })).toBeVisible();
    await clickVisibleTab(page, ['交易日历']);
    await expect(page.getByRole('button', { name: '加载交易日历工作台', exact: true })).toBeVisible();
    await clickVisibleTab(page, ['IPO']);
    await expect(page.getByRole('button', { name: '查询IPO信息工作台', exact: true })).toBeVisible();
    await clickVisibleTab(page, ['可转债']);
    await expect(page.getByRole('button', { name: '查询可转债工作台', exact: true })).toBeVisible();
    await clickVisibleTab(page, ['股本']);
    await expect(page.getByRole('button', { name: '查询股本工作台', exact: true })).toBeVisible();
  },
  'settings-workbench': async (page) => {
    await ROUTE_ASSERTIONS.settings(page, {} as FixtureBundle);
    await clickVisibleTab(page, ['AI 模型']);
    await expectTextAny(page, ['AI 模型', '模型']);
    await clickVisibleTab(page, ['安全日志']);
    await expectTextAny(page, ['安全日志', '查看全量日志', '暂无安全日志']);
    await clickVisibleTab(page, ['活跃会话']);
    await expectTextAny(page, ['活跃会话', '查看完整审计日志', '暂无活跃会话']);
    await clickVisibleTab(page, ['账户信息']);
    await expect(page.getByRole('button', { name: '保存资料' })).toBeVisible();
  },
  'paper-trading-order-workbench': async (page) => {
    await ROUTE_ASSERTIONS['paper-trading'](page, {} as FixtureBundle);
    await expect(page.getByText('订单预览')).toBeVisible();
    await expectAnyVisible([
      page.getByRole('button', { name: '确认买入' }),
      page.getByRole('button', { name: '确认卖出' }),
    ]);
  },
  'performance-review-workbench': async (page) => {
    await ROUTE_ASSERTIONS.performance(page, {} as FixtureBundle);
    await clickVisibleTab(page, ['组合归因']);
    await expectTextAny(page, ['收益归因拆解', '组合归因']);
    await clickVisibleTab(page, ['账户绩效']);
    await expectTextAny(page, ['账户绩效', '净值']);
  },
  'strategy-market-catalog-workbench': async (page) => {
    await ROUTE_ASSERTIONS['strategy-market'](page, {} as FixtureBundle);
    await expect(page.getByText('工厂摘要')).toBeVisible();
    await expect(page.getByRole('button', { name: /组合购物车/ })).toBeVisible();
  },
  'strategy-detail-review-workbench': async (page) => {
    await strategyDetailAssertion(page, {} as FixtureBundle);
    await expect(page.getByRole('tab', { name: '实盘跟踪' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '工厂审查' })).toBeVisible();
    await page.getByRole('tab', { name: '工厂审查' }).click();
    await expect(page.getByRole('tab', { name: '工厂摘要' })).toBeVisible();
    await expect(page.getByRole('tab', { name: '孵化闭环' })).toBeVisible();
  },
};

export async function verifySurface(page: Page, bundle: FixtureBundle, surfaceId: string) {
  const assertion = ROUTE_ASSERTIONS[surfaceId];
  if (!assertion) {
    throw new Error(`missing route assertion for surface ${surfaceId}`);
  }
  await assertion(page, bundle);
}
