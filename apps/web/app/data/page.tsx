'use client';

import { useMemo, useState } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
import { PieChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

const TABS = [
  { key: 'option', label: '期权链' },
  { key: 'calendar', label: '交易日历' },
  { key: 'ipo', label: 'IPO' },
  { key: 'cb', label: '可转债' },
  { key: 'capital', label: '股本' },
] as const;

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
    let p: string;
    if (tab === 'option') {
      p = `/data/option-chain?underlying=${encodeURIComponent(underlying.trim())}`;
    } else if (tab === 'calendar') {
      p = '/data/trading-dates?count=30';
    } else if (tab === 'ipo') {
      p = '/data/ipo';
    } else if (tab === 'cb') {
      if (!trimmedCode) { setCodeError('请输入可转债代码'); return; }
      p = `/data/cb?code=${encodeURIComponent(trimmedCode)}`;
    } else {
      if (!validate()) return;
      p = `/data/capital?code=${encodeURIComponent(trimmedCode)}`;
    }
    if (p === queryPath) refetch(); else setQueryPath(p);
  }

  const optionRows = useMemo(
    () => extractArray(data, 'options', 'calls', 'puts', 'chain')
      .map((row) => normalizeOptionRow(row))
      .filter((row) => row.strike != null || row.lastPrice != null || row.type),
    [data],
  );
  const calendarRows = extractArray(data, 'dates', 'tradingDates') as Array<Record<string, unknown>>;
  const ipoRows = extractArray(data, 'ipos', 'list', 'data') as Array<Record<string, unknown>>;
  const cbObj = tab === 'cb' ? extractObject(data) as Record<string, unknown> | null : null;
  const capObj = tab === 'capital' ? extractObject(data) as Record<string, unknown> | null : null;

  function renderData() {
    if (!data) return null;

    if (tab === 'option') {
      if (!optionRows.length) return <EmptyState text="无期权数据" />;
      return (
        <DataTable
          rows={optionRows}
          columns={[
            { key: 'strike', label: '行权价', align: 'right' as const, sortable: true, render: (v) => fmtNum(Number(v), 2) },
            { key: 'lastPrice', label: '最新价', align: 'right' as const, render: (v) => fmtNum(Number(v), 4) },
            { key: 'volume', label: '成交量', align: 'right' as const, sortable: true, render: (v) => fmtNum(Number(v), 0) },
            { key: 'openInterest', label: '持仓量', align: 'right' as const, sortable: true, render: (v) => fmtNum(Number(v), 0) },
            { key: 'impliedVol', label: '隐含波动率', align: 'right' as const, render: (v) => v != null ? fmtNum(Number(v) * 100, 2) + '%' : '-' },
            { key: 'type', label: '类型', render: (v) => <Badge variant={v === 'Call' || v === 'call' ? 'success' : 'danger'}>{String(v ?? '-')}</Badge> },
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
            { key: 'isTrading', label: '交易日', render: (v) => <Badge variant={v ? 'success' : 'neutral'}>{v ? '是' : '否'}</Badge> },
          ]}
          onExport={() => exportCSV(calendarRows, 'trading-calendar')}
        />
      );
    }

    if (tab === 'ipo') {
      if (!ipoRows.length) return <EmptyState text="无IPO数据" />;
      return (
        <DataTable
          rows={ipoRows}
          columns={[
            { key: 'code', label: '代码', sortable: true },
            { key: 'name', label: '名称', sortable: true },
            { key: 'ipoDate', label: '上市日期', sortable: true },
            { key: 'price', label: '发行价', align: 'right' as const, render: (v) => v != null ? fmtNum(Number(v), 2) : '-' },
            { key: 'industry', label: '行业' },
            { key: 'status', label: '状态', render: (v) => {
              const s = String(v ?? '');
              const isListed = s.includes('上市') || s.includes('listed') || s === 'listed';
              return <Badge variant={isListed ? 'success' : 'warning'}>{s || '-'}</Badge>;
            }},
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
        <>
          <KpiGrid cols={3}>
            <KpiCard title="总股本" value={fmtAmount(totalShares)} />
            <KpiCard title="流通股" value={fmtAmount(floatShares)} />
            <KpiCard title="总市值" value={fmtAmount(marketCap)} />
          </KpiGrid>
          {pieData.length > 0 && <PieChart data={pieData} donut />}
        </>
      );
    }

    return <EmptyState text="无数据" />;
  }

  function renderStarterState() {
    if (tab === 'option') {
      return (
        <EmptyState
          text="先输入 ETF 期权标的，再加载期权链。"
          hint="常用示例是 510050 和 510300；如果你只是在熟悉页面，直接点一个示例即可。"
          action={
            <>
              {['510050', '510300'].map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setUnderlying(item)}
                  className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt"
                >
                  使用 {item}
                </button>
              ))}
            </>
          }
        />
      );
    }
    if (tab === 'calendar') {
      return <EmptyState text="加载最近 30 个交易日，快速确认节假日与开市节奏。" hint="上方操作区会直接触发查询，返回后会展示最近交易日清单。" />;
    }
    if (tab === 'ipo') {
      return <EmptyState text="这里适合看最近的新股与新债申购安排。" hint="直接使用上方查询按钮即可加载最近申购窗口。" />;
    }
    if (tab === 'cb') {
      return <EmptyState text="请输入可转债代码后再查询。" hint="示例：123039" action={<button type="button" onClick={() => setCode('123039')} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt">填入示例 123039</button>} />;
    }
    return <EmptyState text="请输入股票代码后查看股本结构。" hint="示例：600519" action={<button type="button" onClick={() => setCode('600519')} className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt">填入示例 600519</button>} />;
  }

  return (
    <PageContainer>
      <h1>数据中心</h1>
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); setQueryPath(null); }} />
      <SectionCard tabAttached>
        {tab === 'option' ? (
          <div className="grid gap-2">
            <label htmlFor="data-option-underlying" className="grid gap-1 text-xs text-text-secondary">
              <span>期权标的代码</span>
              <div className="flex gap-2 items-center flex-wrap">
                <input
                  id="data-option-underlying"
                  value={underlying}
                  onChange={(e) => setUnderlying(e.target.value)}
                  placeholder="标的代码 如 510050"
                  className="w-[160px] px-2 py-1 border border-border rounded text-sm"
                />
                <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
                  查询期权链
                </button>
              </div>
            </label>
            <p className="m-0 text-xs text-text-secondary">这里的“标的代码”指 ETF 期权对应的基础标的，不是单只股票代码。</p>
          </div>
        ) : null}
        {tab === 'calendar' ? (
          <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
            加载交易日历
          </button>
        ) : null}
        {tab === 'ipo' ? (
          <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
            查询IPO信息
          </button>
        ) : null}
        {tab === 'cb' ? (
          <div className="flex gap-2 items-center">
            <StockCodeInput id="data-cb-code" label="可转债代码" value={code} onChange={setCode} error={codeError} placeholder="如 123039" />
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              查询可转债
            </button>
          </div>
        ) : null}
        {tab === 'capital' ? (
          <div className="flex gap-2 items-center">
            <StockCodeInput id="data-capital-code" label="股票代码" value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              查询股本
            </button>
          </div>
        ) : null}
        {isPending ? <LoadingState text="加载中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
        {!isPending && !data && !error ? renderStarterState() : null}
        {renderData()}
      </SectionCard>
    </PageContainer>
  );
}
