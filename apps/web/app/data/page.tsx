'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  PageContainer,
  TabBar,
  SectionCard,
  StockCodeInput,
  KpiCard,
  KpiGrid,
  DataTable,
  Badge,
} from '@/components/ui';
import { PieChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, extractObject, fmtAmount, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

const TABS = [
  { key: 'option', label: '期权链' },
  { key: 'calendar', label: '交易日历' },
  { key: 'ipo', label: 'IPO' },
  { key: 'cb', label: '可转债' },
  { key: 'capital', label: '股本' },
] as const;

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

type Tab = (typeof TABS)[number]['key'];

function readOptionNumber(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (value == null || value === '') continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function normalizeOptionRow(row: Record<string, unknown>) {
  const type = String(row.type ?? row.option_type ?? row.side ?? '').toLowerCase();
  return {
    ...row,
    strike: readOptionNumber(row, ['strike', 'strikePrice', 'exercise_price']),
    lastPrice: readOptionNumber(row, ['lastPrice', 'last', 'price', 'close']),
    volume: readOptionNumber(row, ['volume', 'trade_volume']),
    openInterest: readOptionNumber(row, ['openInterest', 'open_interest', 'oi']),
    impliedVol: readOptionNumber(row, ['impliedVol', 'impliedVolatility', 'implied_volatility', 'iv']),
    type,
  };
}

export default function DataPage() {
  const [tab, setTab] = useState<Tab>('option');
  const { code, setCode, codeError, setCodeError, validate, trimmedCode } = useStockCode('');
  const [underlying, setUnderlying] = useState('510050');
  const [queryPath, setQueryPath] = useState<string | null>(null);
  const { data, isFetching: isPending, error, refetch } = useApiQuery<unknown>(queryPath);

  function submit() {
    let path: string;

    if (tab === 'option') {
      path = `/data/option-chain?underlying=${encodeURIComponent(underlying.trim())}`;
    } else if (tab === 'calendar') {
      path = '/data/trading-dates?count=30';
    } else if (tab === 'ipo') {
      path = '/data/ipo';
    } else if (tab === 'cb') {
      if (!trimmedCode) {
        setCodeError('请输入可转债代码');
        return;
      }
      path = `/data/cb?code=${encodeURIComponent(trimmedCode)}`;
    } else {
      if (!validate()) return;
      path = `/data/capital?code=${encodeURIComponent(trimmedCode)}`;
    }

    if (path === queryPath) refetch();
    else setQueryPath(path);
  }

  const optionRows = useMemo(
    () =>
      extractArray(data, 'options', 'calls', 'puts', 'chain')
        .map((row) => normalizeOptionRow(row))
        .filter((row) => row.strike != null || row.lastPrice != null || row.type),
    [data],
  );
  const calendarRows = extractArray(data, 'dates', 'tradingDates') as Array<Record<string, unknown>>;
  const ipoRows = extractArray(data, 'ipos', 'list', 'data') as Array<Record<string, unknown>>;
  const cbObj = tab === 'cb' ? (extractObject(data) as Record<string, unknown>) || null : null;
  const capObj = tab === 'capital' ? (extractObject(data) as Record<string, unknown>) || null : null;
  const activeTabLabel = TABS.find((item) => item.key === tab)?.label ?? '数据';
  const resultCount =
    tab === 'option'
      ? optionRows.length
      : tab === 'calendar'
        ? calendarRows.length
        : tab === 'ipo'
          ? ipoRows.length
          : data
            ? 1
            : 0;
  const focusTarget =
    tab === 'option'
      ? underlying.trim() || '510050'
      : tab === 'calendar'
        ? '最近 30 个交易日'
        : tab === 'ipo'
          ? '最近 IPO 窗口'
          : trimmedCode || '待输入';
  const tabDescription =
    tab === 'option'
      ? '适合观察 ETF 期权链的行权价、成交量、持仓量与隐含波动率。'
      : tab === 'calendar'
        ? '适合确认开市、休市与节假日节奏，给后续策略或提醒页做时间参照。'
        : tab === 'ipo'
          ? '适合快速查看最近新股与新债窗口，判断一级市场供给节奏。'
          : tab === 'cb'
            ? '适合用单只转债快速看价格、转股价值和溢价率。'
            : '适合用股本结构确认流通盘、限售盘与总市值的关系。';

  function renderStarterState() {
    if (tab === 'option') {
      return (
        <EmptyState
          text="先输入 ETF 期权标的，再加载期权链"
          hint="常用示例是 510050 和 510300；如果你只是先熟悉页面，直接点一个示例即可。"
          action={
            <>
              {['510050', '510300'].map((item) => (
                <button key={item} type="button" onClick={() => setUnderlying(item)} className={CHIP_BUTTON_CLS}>
                  使用 {item}
                </button>
              ))}
            </>
          }
        />
      );
    }
    if (tab === 'calendar') {
      return (
        <EmptyState
          text="加载最近 30 个交易日，快速确认节假日与开市节奏"
          hint="上方操作区会直接触发查询，返回后会展示最近交易日清单。"
        />
      );
    }
    if (tab === 'ipo') {
      return <EmptyState text="这里适合看最近的新股与新债申购安排" hint="直接使用上方查询按钮即可加载最近申购窗口。" />;
    }
    if (tab === 'cb') {
      return (
        <EmptyState
          text="请输入可转债代码后再查询"
          hint="示例：123039"
          action={
            <button type="button" onClick={() => setCode('123039')} className={CHIP_BUTTON_CLS}>
              填入示例 123039
            </button>
          }
        />
      );
    }
    return (
      <EmptyState
        text="请输入股票代码后查看股本结构"
        hint="示例：600519"
        action={
          <button type="button" onClick={() => setCode('600519')} className={CHIP_BUTTON_CLS}>
            填入示例 600519
          </button>
        }
      />
    );
  }

  function renderData() {
    if (!data) return null;

    if (tab === 'option') {
      if (!optionRows.length) return <EmptyState text="无期权数据" />;
      return (
        <DataTable
          rows={optionRows}
          columns={[
            {
              key: 'strike',
              label: '行权价',
              align: 'right' as const,
              sortable: true,
              render: (value) => fmtNum(Number(value), 2),
            },
            { key: 'lastPrice', label: '最新价', align: 'right' as const, render: (value) => fmtNum(Number(value), 4) },
            {
              key: 'volume',
              label: '成交量',
              align: 'right' as const,
              sortable: true,
              render: (value) => fmtNum(Number(value), 0),
            },
            {
              key: 'openInterest',
              label: '持仓量',
              align: 'right' as const,
              sortable: true,
              render: (value) => fmtNum(Number(value), 0),
            },
            {
              key: 'impliedVol',
              label: '隐含波动率',
              align: 'right' as const,
              render: (value) => (value != null ? `${fmtNum(Number(value) * 100, 2)}%` : '-'),
            },
            {
              key: 'type',
              label: '类型',
              render: (value) => (
                <Badge variant={value === 'Call' || value === 'call' ? 'success' : 'danger'}>
                  {String(value ?? '-')}
                </Badge>
              ),
            },
          ]}
          onExport={() => exportCSV(optionRows, 'option-chain')}
        />
      );
    }

    if (tab === 'calendar') {
      if (!calendarRows.length) return <EmptyState text="无交易日历数据" />;
      return (
        <DataTable
          rows={calendarRows}
          columns={[
            { key: 'date', label: '日期', sortable: true },
            { key: 'dayOfWeek', label: '星期' },
            {
              key: 'isTrading',
              label: '交易日',
              render: (value) => <Badge variant={value ? 'success' : 'neutral'}>{value ? '是' : '否'}</Badge>,
            },
          ]}
          onExport={() => exportCSV(calendarRows, 'trading-calendar')}
        />
      );
    }

    if (tab === 'ipo') {
      if (!ipoRows.length) return <EmptyState text="无 IPO 数据" />;
      return (
        <DataTable
          rows={ipoRows}
          columns={[
            { key: 'code', label: '代码', sortable: true },
            { key: 'name', label: '名称', sortable: true },
            { key: 'ipoDate', label: '上市日期', sortable: true },
            {
              key: 'price',
              label: '发行价',
              align: 'right' as const,
              render: (value) => (value != null ? fmtNum(Number(value), 2) : '-'),
            },
            { key: 'industry', label: '行业' },
            {
              key: 'status',
              label: '状态',
              render: (value) => {
                const statusText = String(value ?? '');
                const isListed =
                  statusText.includes('上市') || statusText.includes('listed') || statusText === 'listed';
                return <Badge variant={isListed ? 'success' : 'warning'}>{statusText || '-'}</Badge>;
              },
            },
          ]}
          onExport={() => exportCSV(ipoRows, 'ipo-list')}
        />
      );
    }

    if (tab === 'cb' && cbObj) {
      return (
        <KpiGrid cols={3}>
          <KpiCard title="价格" value={fmtNum(Number(cbObj.price ?? 0), 2)} />
          <KpiCard title="转股价" value={fmtNum(Number(cbObj.conversionPrice ?? cbObj.conversion_price ?? 0), 2)} />
          <KpiCard title="转股价值" value={fmtNum(Number(cbObj.conversionValue ?? cbObj.conversion_value ?? 0), 2)} />
          <KpiCard title="溢价率" value={fmtNum(Number(cbObj.premium ?? 0) * 100, 2)} suffix="%" />
          <KpiCard title="评级" value={String(cbObj.rating ?? '-')} />
          <KpiCard title="到期日" value={String(cbObj.maturityDate ?? cbObj.maturity_date ?? '-')} />
        </KpiGrid>
      );
    }

    if (tab === 'capital' && capObj) {
      const totalShares = Number(capObj.totalShares ?? capObj.total_shares ?? 0);
      const floatShares = Number(capObj.floatShares ?? capObj.float_shares ?? 0);
      const restrictedShares = totalShares - floatShares;
      const marketCap = Number(capObj.marketCap ?? capObj.market_cap ?? 0);
      const pieData = [
        ...(floatShares > 0 ? [{ name: '流通股', value: floatShares, color: COLORS.primary }] : []),
        ...(restrictedShares > 0 ? [{ name: '限售股', value: restrictedShares, color: COLORS.warning }] : []),
      ];

      return (
        <div className="space-y-4">
          <KpiGrid cols={3}>
            <KpiCard title="总股本" value={fmtAmount(totalShares)} />
            <KpiCard title="流通股" value={fmtAmount(floatShares)} />
            <KpiCard title="总市值" value={fmtAmount(marketCap)} />
          </KpiGrid>
          {pieData.length > 0 ? <PieChart data={pieData} donut /> : null}
        </div>
      );
    }

    return <EmptyState text="无数据" />;
  }

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Data Workspace</Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={queryPath ? 'success' : 'warning'}>
                {queryPath ? '已建立查询上下文' : '等待首次查询'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              数据中心工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这一页负责补齐交易链路中最常被临时查找的数据块。先决定是查期权、日历、IPO、可转债还是股本结构，再在结果区完成对比和导出。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={submit} disabled={isPending} className={HERO_PRIMARY_BUTTON_CLS}>
                {isPending ? '加载中...' : `查询${activeTabLabel}`}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (tab === 'option') setUnderlying('510050');
                  if (tab === 'cb') setCode('123039');
                  if (tab === 'capital') setCode('600519');
                }}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                填入推荐示例
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前类别</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">{tabDescription}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前目标</div>
                <div className="mt-3 text-lg font-semibold text-text-primary">{focusTarget}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">结果条数</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{resultCount}</div>
                <div className="mt-1 text-xs text-text-secondary">用于判断当前结果是否足够继续对比</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">状态</div>
                <div className="mt-3 text-lg font-semibold text-text-primary">
                  {isPending ? '加载中' : data ? '已返回' : '待查询'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前查询焦点</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{focusTarget}</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  类别：<span className="font-medium text-text-primary">{activeTabLabel}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  结果条数：<span className="font-medium text-text-primary">{resultCount}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  下一步：
                  <span className="font-medium text-text-primary">
                    {tab === 'option'
                      ? '比对波动率与持仓量'
                      : tab === 'calendar'
                        ? '确认时间窗口'
                        : tab === 'ipo'
                          ? '补一级市场供给'
                          : tab === 'cb'
                            ? '看溢价与转股价值'
                            : '确认流通盘与市值'}
                  </span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关联跳转</div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href="/market" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  行情看板
                </Link>
                <Link href="/technical" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  技术分析
                </Link>
                <Link href="/fund-flow" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  资金流向
                </Link>
                <Link href="/valuation" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  估值分析
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Data Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">查询工作台</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              先切换数据类别，再填写对应输入项。查询区只负责决定目标，不把结果阅读和筛选动作揉在一起。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前类别：<span className="font-medium text-text-primary">{activeTabLabel}</span>
          </div>
        </div>

        <div className="mt-4">
          <TabBar
            tabs={TABS}
            active={tab}
            onChange={(key) => {
              setTab(key);
              setQueryPath(null);
            }}
          />
        </div>

        <SectionCard tabAttached>
          {tab === 'option' ? (
            <div className="grid gap-4 xl:grid-cols-[220px_auto] xl:items-end">
              <label htmlFor="data-option-underlying" className="grid gap-2 text-xs text-text-secondary">
                <span className="font-medium uppercase tracking-[0.12em] text-text-muted">期权标的代码</span>
                <input
                  id="data-option-underlying"
                  value={underlying}
                  onChange={(e) => setUnderlying(e.target.value)}
                  placeholder="标的代码，如 510050"
                  className={FIELD_CLS}
                />
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                  查询期权链
                </button>
                {['510050', '510300'].map((item) => (
                  <button key={item} type="button" onClick={() => setUnderlying(item)} className={CHIP_BUTTON_CLS}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {tab === 'calendar' ? (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                加载交易日历
              </button>
              <div className="text-sm text-text-secondary">默认返回最近 30 个交易日，用来确认节假日与开市节奏。</div>
            </div>
          ) : null}

          {tab === 'ipo' ? (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                查询 IPO 信息
              </button>
              <div className="text-sm text-text-secondary">适合快速查看最近新股与新债申购窗口。</div>
            </div>
          ) : null}

          {tab === 'cb' ? (
            <div className="grid gap-4 xl:grid-cols-[260px_auto] xl:items-end">
              <StockCodeInput
                id="data-cb-code"
                label="可转债代码"
                value={code}
                onChange={setCode}
                error={codeError}
                placeholder="如 123039"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                  查询可转债
                </button>
                <button type="button" onClick={() => setCode('123039')} className={CHIP_BUTTON_CLS}>
                  123039
                </button>
              </div>
            </div>
          ) : null}

          {tab === 'capital' ? (
            <div className="grid gap-4 xl:grid-cols-[260px_auto] xl:items-end">
              <StockCodeInput
                id="data-capital-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
                placeholder="如 600519"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                  查询股本
                </button>
                <button type="button" onClick={() => setCode('600519')} className={CHIP_BUTTON_CLS}>
                  600519
                </button>
              </div>
            </div>
          ) : null}
        </SectionCard>
      </div>

      <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Result View</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">查询结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              结果区负责查看、比对和导出。先确认返回是否完整，再决定跳去行情、技术或估值页继续联动。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前目标：<span className="font-medium text-text-primary">{focusTarget}</span>
          </div>
        </div>

        {isPending ? <LoadingState text="加载中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
        {!isPending && !data && !error ? renderStarterState() : null}
        {renderData()}
      </div>
    </PageContainer>
  );
}
