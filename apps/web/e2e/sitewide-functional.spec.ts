import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertNoHorizontalOverflow,
  assertProtectedShell,
  createPageIssueCollector,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

async function expectEitherVisible(...locators: Locator[]) {
  await expect
    .poll(async () => {
    for (const locator of locators) {
        const count = await locator.count().catch(() => 0);
        for (let index = 0; index < count; index += 1) {
          if (await locator.nth(index).isVisible().catch(() => false)) {
            return true;
          }
        }
      }
      return false;
    }, { timeout: 15_000, intervals: [250, 500, 1_000] })
    .toBe(true);
}

async function openAndCheck(page: Page, path: string, heading: RegExp | string) {
  await openProtectedPage(page, path);
  await assertProtectedShell(page);
  await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible();
  await assertNoHorizontalOverflow(page);
}

test('should exercise market, search and stock analysis workflows', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await openAndCheck(page, '/market', '行情看板');

  await page.getByRole('tab', { name: '涨停板' }).click();
  await page.getByRole('button', { name: '刷新', exact: true }).click();
  await expectEitherVisible(
    page.getByText('涨停总数'),
    page.getByText('当前还没有涨停榜单'),
  );

  await page.getByRole('tab', { name: '板块' }).click();
  await page.getByRole('button', { name: '加载行业板块', exact: true }).click();
  await expectEitherVisible(
    page.getByText('板块代码'),
    page.getByText('先加载行业板块再看轮动'),
  );

  await page.getByRole('tab', { name: '指数' }).click();
  await page.getByLabel('指数代码').fill('000300');
  await page.getByRole('button', { name: '查询指数行情', exact: true }).click();
  await expect(page.getByText('指数名称')).toBeVisible({ timeout: 20_000 });

  await page.getByRole('tab', { name: '搜索' }).click();
  await page.getByLabel('搜索关键词').fill('平安');
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await expectEitherVisible(
    page.getByRole('button', { name: /加载全市场列表|加载全部股票列表/ }),
    page.getByText(/平安银行|中国平安/).first(),
  );

  await page.getByLabel('批量股票代码').fill('000001,600519');
  await page.getByRole('button', { name: '批量行情', exact: true }).click();
  const batchTable = page.getByRole('table').last();
  await expect(batchTable.getByRole('link', { name: '平安银行' })).toBeVisible({ timeout: 20_000 });
  await expect(batchTable.getByRole('link', { name: '贵州茅台' })).toBeVisible({ timeout: 20_000 });
  await assertNoHorizontalOverflow(page);

  await openAndCheck(page, '/stock', /股票详情|\d{6}/);
  await page.getByRole('textbox', { name: '股票代码' }).fill('000001');
  await page.getByRole('button', { name: '查询', exact: true }).click();
  await expect(page.getByRole('heading', { name: /000001|平安银行/ }).first()).toBeVisible({ timeout: 20_000 });

  await page.getByRole('tab', { name: '技术面' }).click();
  await expectEitherVisible(
    page.getByText('MACD'),
    page.getByText('查询股票后显示技术指标'),
  );

  await page.getByRole('tab', { name: '资金流' }).click();
  await expectEitherVisible(
    page.getByText('净流入'),
    page.getByText('暂无资金流向数据'),
  );

  await page.getByRole('tab', { name: '估值' }).click();
  await expectEitherVisible(
    page.getByText(/PE|市盈率/),
    page.getByText('查询股票后显示估值数据'),
  );

  await page.getByRole('tab', { name: '资讯' }).click();
  await expectEitherVisible(
    page.getByRole('heading', { name: '最新资讯' }),
    page.getByText('查询股票后显示相关资讯'),
    page.getByText(/研报|公告|新闻/).first(),
  );

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector);
  collector.dispose();
});

test('should exercise macro, options and data-center workflows', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await openAndCheck(page, '/macro', /宏观经济数据分析/);
  await page.getByLabel('宏观指标').selectOption('cpi');
  await expect(page.getByText('历史数据流水表')).toBeVisible({ timeout: 20_000 });
  await assertNoHorizontalOverflow(page);

  await openAndCheck(page, '/options', /期权全景分析/);
  await page.getByLabel('期权标的代码').fill('510050');
  await page.getByRole('button', { name: '查询', exact: true }).click();
  await expect(page.getByText('T型报价牌')).toBeVisible({ timeout: 20_000 });
  await expectEitherVisible(
    page.getByText('认购 (Call)'),
    page.getByText('当前标的暂无期权链数据'),
  );
  await expectEitherVisible(
    page.getByText('Greeks 解读'),
    page.getByText('当前暂无 Greeks 数据'),
  );

  await openAndCheck(page, '/data', '数据中心');
  await page.getByRole('button', { name: '查询期权链', exact: true }).click();
  await expectEitherVisible(
    page.getByRole('columnheader', { name: '行权价', exact: true }),
    page.getByText('无期权数据', { exact: true }),
  );

  await page.getByRole('tab', { name: '交易日历' }).click();
  await page.getByRole('button', { name: '加载交易日历', exact: true }).click();
  await expectEitherVisible(
    page.getByRole('columnheader', { name: '交易日', exact: true }),
    page.getByText('无交易日历数据', { exact: true }),
  );

  await page.getByRole('tab', { name: 'IPO' }).click();
  await page.getByRole('button', { name: '查询IPO信息', exact: true }).click();
  await expectEitherVisible(
    page.getByRole('columnheader', { name: '发行价', exact: true }),
    page.getByText('无IPO数据', { exact: true }),
  );

  await page.getByRole('tab', { name: '可转债' }).click();
  if (await page.getByRole('button', { name: '填入示例 123039', exact: true }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: '填入示例 123039', exact: true }).click();
  } else {
    await page.getByRole('textbox', { name: '可转债代码' }).fill('123039');
  }
  await page.getByRole('button', { name: '查询可转债', exact: true }).click();
  await expect(page.getByText('转股价', { exact: true })).toBeVisible({ timeout: 20_000 });

  await page.getByRole('tab', { name: '股本' }).click();
  if (await page.getByRole('button', { name: '填入示例 600519', exact: true }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: '填入示例 600519', exact: true }).click();
  } else {
    await page.getByRole('textbox', { name: '股票代码' }).fill('600519');
  }
  await page.getByRole('button', { name: '查询股本', exact: true }).click();
  await expect(page.getByText('总股本', { exact: true })).toBeVisible({ timeout: 20_000 });

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector);
  collector.dispose();
});

test('should exercise notifications, settings and admin utility workflows', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await openAndCheck(page, '/notifications', /通知中心/);
  if (await page.getByRole('button', { name: /全部已读/ }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: /全部已读/ }).click();
    await waitForSettledUi(page, 1200);
  }
  if (await page.getByRole('button', { name: /选中当前筛选|取消全选当前筛选/ }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: /选中当前筛选|取消全选当前筛选/ }).click();
    await waitForSettledUi(page, 600);
  }
  await assertNoHorizontalOverflow(page);

  await openAndCheck(page, '/settings', '设置中心');
  await page.getByRole('tab', { name: '安全日志' }).click();
  await expectEitherVisible(
    page.getByText('暂无安全日志'),
    page.getByText('耗时'),
  );
  await page.getByRole('tab', { name: '活跃会话' }).click();
  await expectEitherVisible(
    page.getByText('暂无活跃会话'),
    page.getByText(/当前会话|异地会话|创建时间/),
  );
  await page.getByRole('tab', { name: '账户信息' }).click();
  await page.getByRole('button', { name: '生成投资报告', exact: true }).click();
  await expect(page.locator('pre').filter({ hasText: '投资报告' })).toBeVisible({ timeout: 20_000 });

  await openAndCheck(page, '/settings/security', /安全设置/);
  await expect(page.locator('input[type="checkbox"]').first()).toBeVisible();

  await openAndCheck(page, '/settings/audit-log', /操作审计日志/);
  await expectEitherVisible(
    page.getByText('技术详情'),
    page.getByText(/资源|暂无审计日志|加载中/).first(),
  );

  await openAndCheck(page, '/admin/cache', /缓存管理/);
  await page.getByRole('button', { name: /清除全部缓存/ }).click();
  await expect(page.getByText('确认清理缓存')).toBeVisible();
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByText('确认清理缓存')).not.toBeVisible({ timeout: 10_000 });

  await openAndCheck(page, '/admin/tools', /MCP 工具仪表盘/);
  await expect(page.getByText('总调用次数')).toBeVisible();

  await openAndCheck(page, '/admin/dead-letters', /死信队列/);
  await expectEitherVisible(
    page.getByText('待处理死信', { exact: true }),
    page.getByText('当前没有待处理死信', { exact: true }),
    page.getByText('正在检查后台失败任务...', { exact: true }),
  );

  await openAndCheck(page, '/admin/users', /用户管理/);
  await expectEitherVisible(
    page.getByRole('columnheader', { name: '用户名', exact: true }),
    page.getByRole('columnheader', { name: '角色', exact: true }),
    page.getByText(/当前展示 \d+ \/ \d+ 位用户/),
  );

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector);
  collector.dispose();
});
