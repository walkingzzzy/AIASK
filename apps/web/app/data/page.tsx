'use client';

import { useState } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
import { PieChart, COLORS } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
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

export default function DataPage() {
  const [tab, setTab] = useState<Tab>('option');
  const { code, setCode, codeError, setCodeError, validate, trimmedCode } = useStockCode('');
  const [underlying, setUnderlying] = useState('510050');
  const { trigger, data, isPending, error, reset } = useApiMutation<unknown>();

  function submit() {
    if (tab === 'option') {
      trigger(`/data/option-chain?underlying=${encodeURIComponent(underlying.trim())}`);
    } else if (tab === 'calendar') {
      trigger('/data/trading-dates?count=30');
    } else if (tab === 'ipo') {
      trigger('/data/ipo');
    } else if (tab === 'cb') {
      if (!trimmedCode) { setCodeError('请输入可转债代码'); return; }
      trigger(`/data/cb?code=${encodeURIComponent(trimmedCode)}`);
    } else {
      if (!validate()) return;
      trigger(`/data/capital?code=${encodeURIComponent(trimmedCode)}`);
    }
  }

  const optionRows = extractArray(data, 'options', 'calls', 'puts', 'chain') as Array<Record<string, unknown>>;
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

  return (
    <PageContainer>
      <h1>数据中心</h1>
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); reset(); }} />
      <SectionCard tabAttached>
        {tab === 'option' ? (
          <div className="flex gap-2 items-center">
            <input
              value={underlying}
              onChange={(e) => setUnderlying(e.target.value)}
              placeholder="标的代码 如 510050"
              className="w-[160px] px-2 py-1 border border-border rounded text-sm"
            />
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              查询期权链
            </button>
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
            <StockCodeInput value={code} onChange={setCode} error={codeError} placeholder="可转债代码" />
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              查询可转债
            </button>
          </div>
        ) : null}
        {tab === 'capital' ? (
          <div className="flex gap-2 items-center">
            <StockCodeInput value={code} onChange={setCode} error={codeError} />
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              查询股本
            </button>
          </div>
        ) : null}
        {isPending ? <LoadingState text="加载中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
        {!isPending && !data && !error ? <EmptyState text="点击按钮查询数据" /> : null}
        {renderData()}
      </SectionCard>
    </PageContainer>
  );
}
