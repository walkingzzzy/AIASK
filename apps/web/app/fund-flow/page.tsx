'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Badge, PageContainer, TabBar, SectionCard, StockCodeInput } from '@/components/ui';
import { KpiCard, KpiGrid, DataTable, QuickAction, QuickActionGrid } from '@/components/ui';
import { BarChart, LineChart, PieChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt } from '@/lib/api';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';

type Tab = 'stock' | 'sector' | 'concept' | 'north' | 'dragon' | 'margin' | 'block-trades' | 'north-detail';
const TABS: { key: Tab; label: string }[] = [
  { key: 'stock', label: '个股资金流' },
  { key: 'sector', label: '板块资金流' },
  { key: 'concept', label: '概念资金流' },
  { key: 'north', label: '北向资金' },
  { key: 'dragon', label: '龙虎榜' },
  { key: 'margin', label: '融资融券' },
  { key: 'block-trades', label: '大宗交易' },
  { key: 'north-detail', label: '北向明细' },
];

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';

export default function FundFlowPage() {
  const [tab, setTab] = useState<Tab>('stock');
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode('600519');
  const autoStockPath = resolvedCode ? `/fund-flow/stock?code=${encodeURIComponent(resolvedCode)}` : null;
  const [stockPath, setStockPath] = useState<string | null>(null);
  const [sectorPath, setSectorPath] = useState<string | null>(null);
  const [conceptPath, setConceptPath] = useState<string | null>(null);
  const [northPath, setNorthPath] = useState<string | null>(null);
  const [dragonPath, setDragonPath] = useState<string | null>(null);
  const [marginPath, setMarginPath] = useState<string | null>(null);
  const [marginRankPath, setMarginRankPath] = useState<string | null>(null);
  const [blockTradesPath, setBlockTradesPath] = useState<string | null>(null);
  const [northHoldingPath, setNorthHoldingPath] = useState<string | null>(null);
  const [northTopPath, setNorthTopPath] = useState<string | null>(null);

  const effectiveStockPath = stockPath ?? autoStockPath;

  const stockQ = useApiQuery<unknown>(effectiveStockPath);
  const sectorQ = useApiQuery<unknown>(sectorPath);
  const conceptQ = useApiQuery<unknown>(conceptPath);
  const northQ = useApiQuery<unknown>(northPath);
  const dragonQ = useApiQuery<unknown>(dragonPath);
  const marginQ = useApiQuery<unknown>(marginPath);
  const marginRankQ = useApiQuery<unknown>(marginRankPath);
  const blockTradesQ = useApiQuery<unknown>(blockTradesPath);
  const northHoldingQ = useApiQuery<unknown>(northHoldingPath);
  const northTopQ = useApiQuery<unknown>(northTopPath);

  // Per-tab loading & error — 避免跨 Tab 互相阻塞
  const tabLoading: Record<Tab, boolean> = {
    stock: stockQ.isFetching,
    sector: sectorQ.isFetching,
    concept: conceptQ.isFetching,
    north: northQ.isFetching,
    dragon: dragonQ.isFetching,
    margin: marginQ.isFetching || marginRankQ.isFetching,
    'block-trades': blockTradesQ.isFetching,
    'north-detail': northHoldingQ.isFetching || northTopQ.isFetching,
  };
  const tabError: Record<Tab, string | null> = {
    stock: codeError || stockQ.error,
    sector: sectorQ.error,
    concept: conceptQ.error,
    north: northQ.error,
    dragon: dragonQ.error,
    margin: marginQ.error || marginRankQ.error,
    'block-trades': blockTradesQ.error,
    'north-detail': codeError || northHoldingQ.error || northTopQ.error,
  };
  const loading = tabLoading[tab];
  const error = tabError[tab];
  const primaryActionCls = HERO_PRIMARY_BUTTON_CLS;
  const secondaryActionCls = 'action-chip text-sm no-underline text-inherit';
  const secondaryButtonCls = CHIP_BUTTON_CLS;
  const activeTabLabel = TABS.find((item) => item.key === tab)?.label ?? '资金流向';
  const activeCodeLabel = trimmedCode || resolvedCode || '600519';
  const tabStatusLabel = loading ? '加载中' : error ? '需重试' : '就绪';
  const heroNotes = [
    '先用板块、概念和北向资金判断“钱在往哪流”，再决定是否回到个股或研究页深入。',
    '个股资金流、龙虎榜和融资融券更适合做交易验证，板块与概念榜更适合找方向。',
    '如果你只想看外资偏好，优先走“北向资金”与“北向明细”这条组合路径。',
  ];

  function loadStockFlow(nextCode = trimmedCode || resolvedCode || '600519') {
    setCode(nextCode);
    const p = `/fund-flow/stock?code=${encodeURIComponent(nextCode)}`;
    if (p === effectiveStockPath) stockQ.refetch();
    else setStockPath(p);
  }

  function loadMarginData(nextCode?: string) {
    const effectiveCode = nextCode ?? trimmedCode;
    if (nextCode !== undefined) setCode(nextCode);
    const params = effectiveCode ? `?code=${encodeURIComponent(effectiveCode)}` : '';
    const p = `/fund-flow/margin${params}`;
    if (p === marginPath) marginQ.refetch();
    else setMarginPath(p);
  }

  function loadNorthDetail(nextCode = trimmedCode || resolvedCode || '600519') {
    setCode(nextCode);
    const hp = `/fund-flow/north-holding?code=${encodeURIComponent(nextCode)}`;
    if (hp === northHoldingPath) northHoldingQ.refetch();
    else setNorthHoldingPath(hp);
    if (northTopPath) northTopQ.refetch();
    else setNorthTopPath('/fund-flow/north-top');
  }

  return (
    <PageContainer className="app-theme-market">
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Flow Workspace</Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={error ? 'warning' : loading ? 'warning' : 'success'}>{tabStatusLabel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              资金流向工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这一页现在会先帮你判断钱正在流向哪里，再把个股、板块、北向和融资融券这几类观察路径收束到同一套工作台语言里，减少“看了一半还得重新找入口”的切换成本。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  setTab('stock');
                  loadStockFlow(activeCodeLabel);
                }}
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                查看个股资金流
              </button>
              <button
                type="button"
                onClick={() => {
                  setTab('north');
                  if (northPath) northQ.refetch();
                  else setNorthPath('/fund-flow/north');
                }}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                查看北向资金
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前视角</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">当前正在查看的资金流维度</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前代码</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{activeCodeLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">个股与北向明细会优先使用它</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">状态</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{tabStatusLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">当前 tab 的数据加载状态</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">联动入口</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">市场、研究、风险、自选</div>
                <div className="mt-1 text-xs text-text-secondary">看完资金流后可直接跳到下一步</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读建议</div>
              <div className="mt-4 space-y-3">
                {heroNotes.map((note) => (
                  <div key={note} className={NOTE_CARD_CLS}>
                    {note}
                  </div>
                ))}
              </div>
            </div>
            <div className={PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">快捷跳转</div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href="/market" className={secondaryActionCls}>
                  市场看板
                </Link>
                <Link href="/research" className={secondaryActionCls}>
                  研究分析
                </Link>
                <Link href="/watchlist" className={secondaryActionCls}>
                  自选联动
                </Link>
                <Link href="/risk" className={secondaryActionCls}>
                  风险页
                </Link>
              </div>
              {resolvedCode ? (
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <StockLink code={resolvedCode} name={resolvedCode} />
                  <WatchlistButton code={resolvedCode} name="" />
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <div className={`${PANEL_CLS} mb-4`}>
        <QuickActionGrid cols={4}>
          <QuickAction href="/market" icon="📈" title="市场看板" description="先确认指数、板块和题材强弱" />
          <QuickAction href="/research" icon="🧭" title="研究分析" description="把资金流和基本面、估值放一起看" />
          <QuickAction href="/watchlist" icon="⭐" title="自选联动" description="把关注标的拉回到日常跟踪清单" />
          <QuickAction href="/risk" icon="🛡️" title="风险页" description="确认异常资金波动是否伴随仓位风险" />
        </QuickActionGrid>
      </div>

      {loading ? <LoadingState text="加载中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      <div className={`${PANEL_CLS} mb-1`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="eyebrow">Flow Tabs</div>
            <div className="mt-2 text-sm leading-7 text-text-secondary">
              先选一个资金维度，再在下方展开具体图表或榜单。个股、板块和北向是最常见的三条起手路径。
            </div>
          </div>
          <Badge variant="neutral">{activeTabLabel}</Badge>
        </div>
        <div className="mt-4">
          <TabBar tabs={TABS} active={tab} onChange={setTab} />
        </div>
      </div>

      {tab === 'stock' && (
        <SectionCard tabAttached>
          <div className="flex gap-3 flex-wrap items-end">
            <StockCodeInput
              id="fund-flow-stock-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
            />
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                if (!validate()) return;
                loadStockFlow(trimmedCode);
              }}
            >
              查询
            </button>
          </div>
          <p className="mt-2 text-sm text-text-secondary">
            适合确认一只股票最近几天是否持续获得主力净流入，尤其适合在看板和自选之间来回核对。
          </p>
          {stockQ.data ? (
            (() => {
              const items = extractArray(stockQ.data, 'flows');
              return items.length ? (
                <>
                  <BarChart
                    items={items.map((x: Record<string, unknown>) => ({
                      label: fmt((x.date as string) || (x.name as string)),
                      value: (x.netInflow as number) ?? 0,
                    }))}
                    height={360}
                    yAxisName="净流入"
                    colorByValue
                  />
                  <DataTable
                    rows={items}
                    columns={[
                      { key: 'date', label: '日期' },
                      {
                        key: 'netInflow',
                        label: '净流入',
                        align: 'right' as const,
                        render: (v: unknown) => (
                          <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                            {fmtAmount(v as number)}
                          </span>
                        ),
                      },
                      {
                        key: 'mainInflow',
                        label: '主力流入',
                        align: 'right' as const,
                        render: (v: unknown) => fmtAmount(v as number),
                      },
                      {
                        key: 'mainOutflow',
                        label: '主力流出',
                        align: 'right' as const,
                        render: (v: unknown) => fmtAmount(v as number),
                      },
                      {
                        key: 'retailInflow',
                        label: '散户流入',
                        align: 'right' as const,
                        render: (v: unknown) => fmtAmount(v as number),
                      },
                      {
                        key: 'retailOutflow',
                        label: '散户流出',
                        align: 'right' as const,
                        render: (v: unknown) => fmtAmount(v as number),
                      },
                    ]}
                    maxHeight={300}
                    onExport={() => exportCSV(items, '个股资金流')}
                  />
                </>
              ) : (
                <EmptyState
                  text="这只股票最近没有可展示的资金流记录"
                  hint="可换成成交更活跃的标的，或等待交易时段后刷新再看主力净流入趋势。"
                />
              );
            })()
          ) : (
            <EmptyState
              text="输入股票代码后查看近期开盘资金流向"
              hint="推荐先从 600519 或自选股里的活跃标的开始，快速确认主力与散户资金是否同向。"
              action={
                <>
                  <button type="button" onClick={() => loadStockFlow('600519')} className={primaryActionCls}>
                    示例：600519
                  </button>
                  <Link href="/watchlist" className={secondaryActionCls}>
                    查看自选股
                  </Link>
                </>
              }
            />
          )}
        </SectionCard>
      )}
      {tab === 'sector' && (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (sectorPath) sectorQ.refetch();
              else setSectorPath('/fund-flow/sector');
            }}
          >
            加载板块资金流
          </button>
          {sectorQ.data ? (
            (() => {
              const rows = extractArray(sectorQ.data, 'flows');
              const top5In = rows
                .filter((r: Record<string, unknown>) => Number(r.netInflow ?? 0) > 0)
                .sort(
                  (a: Record<string, unknown>, b: Record<string, unknown>) =>
                    Number(b.netInflow ?? 0) - Number(a.netInflow ?? 0),
                )
                .slice(0, 5);
              const top5Out = rows
                .filter((r: Record<string, unknown>) => Number(r.netInflow ?? 0) < 0)
                .sort(
                  (a: Record<string, unknown>, b: Record<string, unknown>) =>
                    Number(a.netInflow ?? 0) - Number(b.netInflow ?? 0),
                )
                .slice(0, 5);
              return rows.length ? (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                    {top5In.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-1 text-danger">净流入 TOP5</h4>
                        <PieChart
                          data={top5In.map((r: Record<string, unknown>) => ({
                            name: String(r.name ?? ''),
                            value: Number(r.netInflow ?? 0),
                          }))}
                          height={200}
                        />
                      </div>
                    )}
                    {top5Out.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-1 text-success">净流出 TOP5</h4>
                        <PieChart
                          data={top5Out.map((r: Record<string, unknown>) => ({
                            name: String(r.name ?? ''),
                            value: Math.abs(Number(r.netInflow ?? 0)),
                          }))}
                          height={200}
                        />
                      </div>
                    )}
                  </div>
                  <DataTable
                    rows={rows}
                    columns={[
                      { key: 'name', label: '板块名称' },
                      {
                        key: 'changePercent',
                        label: '涨跌幅',
                        align: 'right' as const,
                        render: (v: unknown) => (
                          <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                            {fmtPct(v as number)}
                          </span>
                        ),
                      },
                      {
                        key: 'netInflow',
                        label: '净流入',
                        align: 'right' as const,
                        render: (v: unknown) => (
                          <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                            {fmtAmount(v as number)}
                          </span>
                        ),
                      },
                      {
                        key: 'mainInflow',
                        label: '主力流入',
                        align: 'right' as const,
                        render: (v: unknown) => fmtAmount(v as number),
                      },
                      {
                        key: 'retailInflow',
                        label: '散户流入',
                        align: 'right' as const,
                        render: (v: unknown) => fmtAmount(v as number),
                      },
                    ]}
                    maxHeight={400}
                    onExport={() => exportCSV(rows, '板块资金流')}
                  />
                </>
              ) : (
                <EmptyState text="当前没有板块资金流榜单" hint="非交易时段或数据源短暂波动时常见，建议稍后再次加载。" />
              );
            })()
          ) : (
            <EmptyState
              text="点击按钮查看板块资金流强弱"
              hint="适合盘中快速判断哪类板块正在获得资金关注，再决定深入看个股。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (sectorPath) sectorQ.refetch();
                      else setSectorPath('/fund-flow/sector');
                    }}
                    className={primaryActionCls}
                  >
                    立即加载板块榜单
                  </button>
                  <Link href="/market" className={secondaryActionCls}>
                    去市场看板对照
                  </Link>
                </>
              }
            />
          )}
        </SectionCard>
      )}

      {tab === 'concept' && (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (conceptPath) conceptQ.refetch();
              else setConceptPath('/fund-flow/concept');
            }}
          >
            加载概念资金流
          </button>
          {conceptQ.data ? (
            (() => {
              const rows = extractArray(conceptQ.data, 'flows');
              return rows.length ? (
                <DataTable
                  rows={rows}
                  columns={[
                    { key: 'name', label: '概念名称' },
                    {
                      key: 'changePercent',
                      label: '涨跌幅',
                      align: 'right' as const,
                      render: (v: unknown) => (
                        <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                          {fmtPct(v as number)}
                        </span>
                      ),
                    },
                    {
                      key: 'netInflow',
                      label: '净流入',
                      align: 'right' as const,
                      render: (v: unknown) => (
                        <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                          {fmtAmount(v as number)}
                        </span>
                      ),
                    },
                    {
                      key: 'mainInflow',
                      label: '主力流入',
                      align: 'right' as const,
                      render: (v: unknown) => fmtAmount(v as number),
                    },
                    {
                      key: 'retailInflow',
                      label: '散户流入',
                      align: 'right' as const,
                      render: (v: unknown) => fmtAmount(v as number),
                    },
                  ]}
                  maxHeight={400}
                  onExport={() => exportCSV(rows, '概念资金流')}
                />
              ) : (
                <EmptyState
                  text="当前没有概念资金流榜单"
                  hint="如果你在追踪题材轮动，这里建议在交易时段再刷新一次确认强弱排序。"
                />
              );
            })()
          ) : (
            <EmptyState
              text="点击按钮查看概念题材的资金轮动"
              hint="这一步适合先确定热点概念，再回到市场页或个股页做细查。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (conceptPath) conceptQ.refetch();
                      else setConceptPath('/fund-flow/concept');
                    }}
                    className={primaryActionCls}
                  >
                    立即加载概念榜单
                  </button>
                  <Link href="/research" className={secondaryActionCls}>
                    去研究页深挖
                  </Link>
                </>
              }
            />
          )}
        </SectionCard>
      )}

      {tab === 'north' && (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (northPath) northQ.refetch();
              else setNorthPath('/fund-flow/north');
            }}
          >
            加载北向资金
          </button>
          {northQ.data ? (
            (() => {
              const items = extractArray(northQ.data, 'items', 'flows');
              return items.length ? (
                <LineChart
                  categories={items.map((x: Record<string, unknown>) => fmt(x.date as string))}
                  series={[
                    {
                      name: '北向净流入',
                      data: items.map(
                        (x: Record<string, unknown>) => (x.total as number) ?? (x.netInflow as number) ?? 0,
                      ),
                      color: COLORS.primary,
                    },
                  ]}
                  height={360}
                  yAxisName="净流入(亿)"
                />
              ) : (
                <EmptyState text="当前没有北向净流入序列" hint="非交易日或接口临时缺数时可能为空，建议稍后重新加载。" />
              );
            })()
          ) : (
            <EmptyState
              text="点击按钮加载北向资金走势"
              hint="适合先判断外资整体偏流入还是流出，再决定是否继续追踪北向明细。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (northPath) northQ.refetch();
                      else setNorthPath('/fund-flow/north');
                    }}
                    className={primaryActionCls}
                  >
                    加载北向走势
                  </button>
                  <button type="button" onClick={() => setTab('north-detail')} className={secondaryButtonCls}>
                    去看北向明细
                  </button>
                </>
              }
            />
          )}
        </SectionCard>
      )}
      {tab === 'dragon' && (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (dragonPath) dragonQ.refetch();
              else setDragonPath('/fund-flow/dragon-tiger');
            }}
          >
            加载龙虎榜
          </button>
          {dragonQ.data ? (
            (() => {
              const rows = extractArray(dragonQ.data);
              return rows.length ? (
                <DataTable
                  rows={rows}
                  columns={[
                    {
                      key: 'code',
                      label: '代码',
                      render: (v: unknown, row: Record<string, unknown>) => (
                        <StockLink code={String(v)} name={String(row.name ?? '')} />
                      ),
                    },
                    { key: 'name', label: '名称' },
                    {
                      key: 'closePrice',
                      label: '收盘价',
                      align: 'right' as const,
                      render: (v: unknown) => fmtNum(v as number, 2),
                    },
                    {
                      key: 'changePercent',
                      label: '涨跌幅',
                      align: 'right' as const,
                      render: (v: unknown) => (
                        <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                          {fmtPct(v as number)}
                        </span>
                      ),
                    },
                    { key: 'reason', label: '上榜原因' },
                    {
                      key: 'buyAmount',
                      label: '买入额',
                      align: 'right' as const,
                      render: (v: unknown) => fmtAmount(v as number),
                    },
                    {
                      key: 'sellAmount',
                      label: '卖出额',
                      align: 'right' as const,
                      render: (v: unknown) => fmtAmount(v as number),
                    },
                    {
                      key: 'netAmount',
                      label: '净买入',
                      align: 'right' as const,
                      render: (v: unknown) => (
                        <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                          {fmtAmount(v as number)}
                        </span>
                      ),
                    },
                  ]}
                  maxHeight={400}
                  onExport={() => exportCSV(rows, '龙虎榜')}
                />
              ) : (
                <EmptyState
                  text="当前没有龙虎榜记录"
                  hint="不是每天都有足够的上榜样本；交易日收盘后再次查看通常更完整。"
                />
              );
            })()
          ) : (
            <EmptyState
              text="点击按钮加载龙虎榜数据"
              hint="适合用来识别短线活跃标的与异常成交，再联动到个股详情页核对。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (dragonPath) dragonQ.refetch();
                      else setDragonPath('/fund-flow/dragon-tiger');
                    }}
                    className={primaryActionCls}
                  >
                    加载龙虎榜
                  </button>
                  <Link href="/stock" className={secondaryActionCls}>
                    去个股页核对
                  </Link>
                </>
              }
            />
          )}
        </SectionCard>
      )}

      {tab === 'margin' && (
        <SectionCard tabAttached>
          <div className="flex gap-3 flex-wrap items-end">
            <StockCodeInput
              id="fund-flow-margin-code"
              label="股票代码（可选）"
              value={code}
              onChange={setCode}
              placeholder="留空看全市场"
            />
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                loadMarginData();
              }}
            >
              查询融资融券
            </button>
          </div>
          <p className="mt-2 text-sm text-text-secondary">
            留空代码时更适合看市场级融资融券概况；填入股票代码时则用于确认个股是否存在明显杠杆资金介入。
          </p>
          {marginQ.data ? (
            (() => {
              const rows = extractArray(marginQ.data);
              return (
                <>
                  {rows.length > 1 && (
                    <LineChart
                      categories={rows.map((x: Record<string, unknown>) => fmt(x.date as string))}
                      series={[
                        {
                          name: '融资余额',
                          data: rows.map(
                            (x: Record<string, unknown>) => (x.marginBalance as number) ?? (x.balance as number) ?? 0,
                          ),
                          color: COLORS.primary,
                        },
                      ]}
                      height={300}
                      yAxisName="余额(亿)"
                    />
                  )}
                  {rows.length > 0 ? (
                    <DataTable
                      rows={rows}
                      columns={[
                        { key: 'date', label: '日期' },
                        {
                          key: 'code',
                          label: '代码',
                          render: (v: unknown, row: Record<string, unknown>) => (
                            <StockLink code={String(v)} name={String(row.name ?? '')} />
                          ),
                        },
                        { key: 'name', label: '名称' },
                        {
                          key: 'marginBalance',
                          label: '融资余额',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                        {
                          key: 'marginBuy',
                          label: '融资买入',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                        {
                          key: 'shortBalance',
                          label: '融券余额',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                        {
                          key: 'totalBalance',
                          label: '总余额',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                      ]}
                      maxHeight={400}
                      onExport={() => exportCSV(rows, '融资融券')}
                    />
                  ) : (
                    <EmptyState
                      text="当前没有融资融券记录"
                      hint="可以留空代码查看市场汇总，或换成融资交易更活跃的股票后重试。"
                    />
                  )}
                </>
              );
            })()
          ) : (
            <EmptyState
              text="可按个股查询融资融券，也可以先看全市场概况"
              hint="第一次使用建议先留空查询市场整体，再输入股票代码确认是否存在明显杠杆交易。"
              action={
                <>
                  <button type="button" onClick={() => loadMarginData('600519')} className={primaryActionCls}>
                    示例：600519
                  </button>
                  <button type="button" onClick={() => loadMarginData('')} className={secondaryActionCls}>
                    查看全市场
                  </button>
                </>
              }
            />
          )}
          <div className="mt-3">
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                if (marginRankPath) marginRankQ.refetch();
                else setMarginRankPath('/fund-flow/margin-ranking');
              }}
            >
              融资融券排名
            </button>
            {marginRankQ.data
              ? (() => {
                  const rows = extractArray(marginRankQ.data);
                  return rows.length ? (
                    <DataTable
                      rows={rows}
                      columns={[
                        {
                          key: 'code',
                          label: '代码',
                          render: (v: unknown, row: Record<string, unknown>) => (
                            <StockLink code={String(v)} name={String(row.name ?? '')} />
                          ),
                        },
                        { key: 'name', label: '名称' },
                        {
                          key: 'marginBalance',
                          label: '融资余额',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                        {
                          key: 'marginBuy',
                          label: '融资买入',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                        {
                          key: 'totalBalance',
                          label: '总余额',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                      ]}
                      maxHeight={400}
                      onExport={() => exportCSV(rows, '融资融券排名')}
                    />
                  ) : (
                    <EmptyState
                      text="当前没有融资融券排名数据"
                      hint="如果你要找融资最活跃的标的，可以稍后重新加载该榜单。"
                    />
                  );
                })()
              : null}
          </div>
        </SectionCard>
      )}
      {tab === 'block-trades' && (
        <SectionCard tabAttached>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (blockTradesPath) blockTradesQ.refetch();
              else setBlockTradesPath('/fund-flow/block-trades');
            }}
          >
            加载大宗交易
          </button>
          {blockTradesQ.data ? (
            (() => {
              const rows = extractArray(blockTradesQ.data);
              return rows.length ? (
                <DataTable
                  rows={rows}
                  columns={[
                    { key: 'date', label: '日期' },
                    {
                      key: 'code',
                      label: '代码',
                      render: (v: unknown, row: Record<string, unknown>) => (
                        <StockLink code={String(v)} name={String(row.name ?? '')} />
                      ),
                    },
                    { key: 'name', label: '名称' },
                    {
                      key: 'price',
                      label: '成交价',
                      align: 'right' as const,
                      render: (v: unknown) => fmtNum(v as number, 2),
                    },
                    {
                      key: 'volume',
                      label: '成交量',
                      align: 'right' as const,
                      render: (v: unknown) => fmtNum(v as number),
                    },
                    {
                      key: 'amount',
                      label: '成交额',
                      align: 'right' as const,
                      render: (v: unknown) => fmtAmount(v as number),
                    },
                    {
                      key: 'premium',
                      label: '溢价率',
                      align: 'right' as const,
                      render: (v: unknown) => (
                        <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>
                          {fmtPct(v as number)}
                        </span>
                      ),
                    },
                    { key: 'buyer', label: '买方' },
                    { key: 'seller', label: '卖方' },
                  ]}
                  maxHeight={400}
                  onExport={() => exportCSV(rows, '大宗交易')}
                />
              ) : (
                <EmptyState text="当前没有大宗交易记录" hint="大宗交易在部分日期样本较少，建议交易日收盘后再次确认。" />
              );
            })()
          ) : (
            <EmptyState
              text="点击按钮加载大宗交易数据"
              hint="适合查看机构席位和折溢价交易，再结合个股走势评估影响。"
              action={
                <>
                  <button
                    type="button"
                    onClick={() => {
                      if (blockTradesPath) blockTradesQ.refetch();
                      else setBlockTradesPath('/fund-flow/block-trades');
                    }}
                    className={primaryActionCls}
                  >
                    加载大宗交易
                  </button>
                  <Link href="/research" className={secondaryActionCls}>
                    去研究页联动分析
                  </Link>
                </>
              }
            />
          )}
        </SectionCard>
      )}

      {tab === 'north-detail' && (
        <SectionCard tabAttached>
          <div className="flex gap-3 flex-wrap items-end">
            <StockCodeInput
              id="fund-flow-north-detail-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
            />
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                if (!validate()) return;
                loadNorthDetail(trimmedCode);
              }}
            >
              查询北向明细
            </button>
          </div>
          <p className="mt-2 text-sm text-text-secondary">
            查询后会同时返回单只股票的北向持股概览和全市场热门持仓榜，方便横向对比是否真正受外资偏好。
          </p>
          {northHoldingQ.data || northTopQ.data ? (
            <>
              {northHoldingQ.data &&
                (() => {
                  const obj = extractObject(northHoldingQ.data);
                  const shares = obj.shares as number;
                  const change = obj.change as number;
                  return (
                    <KpiGrid cols={3}>
                      <KpiCard title="持股数量" value={fmtAmount(shares)} />
                      <KpiCard title="占流通比" value={fmtPct(obj.ratio as number)} />
                      <KpiCard
                        title="日增持"
                        value={fmtAmount(change)}
                        change={change != null && shares ? (change / shares) * 100 : null}
                      />
                    </KpiGrid>
                  );
                })()}
              {northTopQ.data &&
                (() => {
                  const rows = extractArray(northTopQ.data);
                  return rows.length ? (
                    <DataTable
                      rows={rows}
                      columns={[
                        {
                          key: 'code',
                          label: '代码',
                          render: (v: unknown, row: Record<string, unknown>) => (
                            <StockLink code={String(v)} name={String(row.name ?? '')} />
                          ),
                        },
                        { key: 'name', label: '名称' },
                        {
                          key: 'shares',
                          label: '持股数',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                        {
                          key: 'ratio',
                          label: '占比',
                          align: 'right' as const,
                          render: (v: unknown) => fmtPct(v as number),
                        },
                        {
                          key: 'marketCap',
                          label: '市值',
                          align: 'right' as const,
                          render: (v: unknown) => fmtAmount(v as number),
                        },
                      ]}
                      maxHeight={400}
                      onExport={() => exportCSV(rows, '北向持仓TOP')}
                    />
                  ) : (
                    <EmptyState text="当前没有北向热门持仓榜" hint="建议在交易日收盘后再看，榜单通常会更完整。" />
                  );
                })()}
            </>
          ) : (
            <EmptyState
              text="输入股票代码查询北向持仓明细"
              hint="这一步适合确认单只股票的外资持股比例，并与全市场热门持仓榜做对照。"
              action={
                <>
                  <button type="button" onClick={() => loadNorthDetail('600519')} className={primaryActionCls}>
                    示例：600519
                  </button>
                  <Link href="/risk" className={secondaryActionCls}>
                    联动风险页
                  </Link>
                </>
              }
            />
          )}
        </SectionCard>
      )}
    </PageContainer>
  );
}
