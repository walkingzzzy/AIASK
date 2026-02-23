'use client';

import { useState } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput } from '@/components/ui';
import { KpiCard, KpiGrid, DataTable } from '@/components/ui';
import { BarChart, LineChart, PieChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt } from '@/lib/api';
import { StockLink } from '@/components/stock-link';

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

export default function FundFlowPage() {
  const [tab, setTab] = useState<Tab>('stock');
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');

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

  const stockQ = useApiQuery<unknown>(stockPath);
  const sectorQ = useApiQuery<unknown>(sectorPath);
  const conceptQ = useApiQuery<unknown>(conceptPath);
  const northQ = useApiQuery<unknown>(northPath);
  const dragonQ = useApiQuery<unknown>(dragonPath);
  const marginQ = useApiQuery<unknown>(marginPath);
  const marginRankQ = useApiQuery<unknown>(marginRankPath);
  const blockTradesQ = useApiQuery<unknown>(blockTradesPath);
  const northHoldingQ = useApiQuery<unknown>(northHoldingPath);
  const northTopQ = useApiQuery<unknown>(northTopPath);

  const loading = stockQ.isFetching || sectorQ.isFetching || conceptQ.isFetching
    || northQ.isFetching || dragonQ.isFetching || marginQ.isFetching
    || marginRankQ.isFetching || blockTradesQ.isFetching
    || northHoldingQ.isFetching || northTopQ.isFetching;
  const error = codeError || stockQ.error || sectorQ.error || conceptQ.error
    || northQ.error || dragonQ.error || marginQ.error
    || marginRankQ.error || blockTradesQ.error
    || northHoldingQ.error || northTopQ.error;

  return (
    <PageContainer>
      <h1>资金流向</h1>
      {loading ? <LoadingState text="加载中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      <TabBar tabs={TABS} active={tab} onChange={setTab} />

      {tab === 'stock' && (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <StockCodeInput value={code} onChange={setCode} error={codeError} />
            <button type="button" disabled={loading} onClick={() => {
              if (!validate()) return;
              const p = `/fund-flow/stock?code=${encodeURIComponent(trimmedCode)}`;
              if (p === stockPath) stockQ.refetch(); else setStockPath(p);
            }}>查询</button>
          </div>
          {stockQ.data ? (() => {
            const items = extractArray(stockQ.data, 'flows');
            return items.length ? (
              <>
              <BarChart
                items={items.map((x: Record<string, unknown>) => ({
                  label: fmt(x.date as string || x.name as string),
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
                  { key: 'netInflow', label: '净流入', align: 'right' as const,
                    render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtAmount(v as number)}</span> },
                  { key: 'mainInflow', label: '主力流入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'mainOutflow', label: '主力流出', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'retailInflow', label: '散户流入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'retailOutflow', label: '散户流出', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                ]}
                maxHeight={300}
                onExport={() => exportCSV(items, '个股资金流')}
              />
              </>
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="输入代码查询个股资金流" />}
        </SectionCard>
      )}
      {tab === 'sector' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => {
            if (sectorPath) sectorQ.refetch(); else setSectorPath('/fund-flow/sector');
          }}>
            加载板块资金流
          </button>
          {sectorQ.data ? (() => {
            const rows = extractArray(sectorQ.data, 'flows');
            const top5In = rows.filter((r: Record<string, unknown>) => Number(r.netInflow ?? 0) > 0)
              .sort((a: Record<string, unknown>, b: Record<string, unknown>) => Number(b.netInflow ?? 0) - Number(a.netInflow ?? 0))
              .slice(0, 5);
            const top5Out = rows.filter((r: Record<string, unknown>) => Number(r.netInflow ?? 0) < 0)
              .sort((a: Record<string, unknown>, b: Record<string, unknown>) => Number(a.netInflow ?? 0) - Number(b.netInflow ?? 0))
              .slice(0, 5);
            return rows.length ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                  {top5In.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-1 text-danger">净流入 TOP5</h4>
                      <PieChart data={top5In.map((r: Record<string, unknown>) => ({ name: String(r.name ?? ''), value: Number(r.netInflow ?? 0) }))} height={200} />
                    </div>
                  )}
                  {top5Out.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium mb-1 text-success">净流出 TOP5</h4>
                      <PieChart data={top5Out.map((r: Record<string, unknown>) => ({ name: String(r.name ?? ''), value: Math.abs(Number(r.netInflow ?? 0)) }))} height={200} />
                    </div>
                  )}
                </div>
                <DataTable
                rows={rows}
                columns={[
                  { key: 'name', label: '板块名称' },
                  { key: 'netInflow', label: '净流入', align: 'right' as const,
                    render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtAmount(v as number)}</span> },
                  { key: 'mainInflow', label: '主力流入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'mainOutflow', label: '主力流出', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'retailInflow', label: '散户流入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'retailOutflow', label: '散户流出', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                ]}
                maxHeight={400}
                onExport={() => exportCSV(rows, '板块资金流')}
              />
              </>
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="点击按钮加载板块资金流" />}
        </SectionCard>
      )}

      {tab === 'concept' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => {
            if (conceptPath) conceptQ.refetch(); else setConceptPath('/fund-flow/concept');
          }}>
            加载概念资金流
          </button>
          {conceptQ.data ? (() => {
            const rows = extractArray(conceptQ.data, 'flows');
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'name', label: '概念名称' },
                  { key: 'netInflow', label: '净流入', align: 'right' as const,
                    render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtAmount(v as number)}</span> },
                  { key: 'mainInflow', label: '主力流入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'mainOutflow', label: '主力流出', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'retailInflow', label: '散户流入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'retailOutflow', label: '散户流出', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                ]}
                maxHeight={400}
                onExport={() => exportCSV(rows, '概念资金流')}
              />
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="点击按钮加载概念资金流" />}
        </SectionCard>
      )}

      {tab === 'north' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => {
            if (northPath) northQ.refetch(); else setNorthPath('/fund-flow/north');
          }}>
            加载北向资金
          </button>
          {northQ.data ? (() => {
            const items = extractArray(northQ.data, 'items', 'flows');
            return items.length ? (
              <LineChart
                categories={items.map((x: Record<string, unknown>) => fmt(x.date as string))}
                series={[{
                  name: '北向净流入',
                  data: items.map((x: Record<string, unknown>) => (x.total as number) ?? (x.netInflow as number) ?? 0),
                  color: COLORS.primary,
                }]}
                height={360}
                yAxisName="净流入(亿)"
              />
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="点击按钮加载北向资金" />}
        </SectionCard>
      )}
      {tab === 'dragon' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => {
            if (dragonPath) dragonQ.refetch(); else setDragonPath('/fund-flow/dragon-tiger');
          }}>
            加载龙虎榜
          </button>
          {dragonQ.data ? (() => {
            const rows = extractArray(dragonQ.data);
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
                  { key: 'name', label: '名称' },
                  { key: 'closePrice', label: '收盘价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                  { key: 'changePercent', label: '涨跌幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
                  { key: 'reason', label: '上榜原因' },
                  { key: 'buyAmount', label: '买入额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'sellAmount', label: '卖出额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'netAmount', label: '净买入', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtAmount(v as number)}</span> },
                ]}
                maxHeight={400}
                onExport={() => exportCSV(rows, '龙虎榜')}
              />
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="点击按钮加载龙虎榜数据" />}
        </SectionCard>
      )}

      {tab === 'margin' && (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <StockCodeInput value={code} onChange={setCode} placeholder="股票代码（可选）" />
            <button type="button" disabled={loading} onClick={() => {
              const params = trimmedCode ? `?code=${encodeURIComponent(trimmedCode)}` : '';
              const p = `/fund-flow/margin${params}`;
              if (p === marginPath) marginQ.refetch(); else setMarginPath(p);
            }}>查询融资融券</button>
          </div>
          {marginQ.data ? (() => {
            const rows = extractArray(marginQ.data);
            const obj = extractObject(marginQ.data);
            const trend = extractArray(obj, 'trend', 'history');
            return (
              <>
                {trend.length > 0 && (
                  <LineChart
                    categories={trend.map((x: Record<string, unknown>) => fmt(x.date as string))}
                    series={[{
                      name: '融资余额',
                      data: trend.map((x: Record<string, unknown>) => (x.balance as number) ?? (x.rzye as number) ?? 0),
                      color: COLORS.primary,
                    }]}
                    height={300}
                    yAxisName="余额(亿)"
                  />
                )}
                {rows.length > 0 ? (
                  <DataTable rows={rows} columns={[
                    { key: 'date', label: '日期' },
                    { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
                    { key: 'name', label: '名称' },
                    { key: 'marginBalance', label: '融资余额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                    { key: 'marginBuy', label: '融资买入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                    { key: 'shortBalance', label: '融券余额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                    { key: 'totalBalance', label: '总余额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  ]} maxHeight={400} onExport={() => exportCSV(rows, '融资融券')} />
                ) : <EmptyState text="暂无数据" />}
              </>
            );
          })() : <EmptyState text="查询融资融券数据" />}
          <div className="mt-3">
            <button type="button" disabled={loading} onClick={() => {
              if (marginRankPath) marginRankQ.refetch(); else setMarginRankPath('/fund-flow/margin-ranking');
            }}>
              融资融券排名
            </button>
            {marginRankQ.data ? (() => {
              const rows = extractArray(marginRankQ.data);
              return rows.length ? (
                <DataTable rows={rows} columns={[
                  { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
                  { key: 'name', label: '名称' },
                  { key: 'marginBalance', label: '融资余额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'marginBuy', label: '融资买入', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'totalBalance', label: '总余额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                ]} maxHeight={400} onExport={() => exportCSV(rows, '融资融券排名')} />
              ) : <EmptyState text="暂无数据" />;
            })() : null}
          </div>
        </SectionCard>
      )}
      {tab === 'block-trades' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => {
            if (blockTradesPath) blockTradesQ.refetch(); else setBlockTradesPath('/fund-flow/block-trades');
          }}>
            加载大宗交易
          </button>
          {blockTradesQ.data ? (() => {
            const rows = extractArray(blockTradesQ.data);
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'date', label: '日期' },
                  { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
                  { key: 'name', label: '名称' },
                  { key: 'price', label: '成交价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                  { key: 'volume', label: '成交量', align: 'right' as const, render: (v: unknown) => fmtNum(v as number) },
                  { key: 'amount', label: '成交额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'premium', label: '溢价率', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-danger' : 'text-success'}>{fmtPct(v as number)}</span> },
                  { key: 'buyer', label: '买方' },
                  { key: 'seller', label: '卖方' },
                ]}
                maxHeight={400}
                onExport={() => exportCSV(rows, '大宗交易')}
              />
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="点击按钮加载大宗交易数据" />}
        </SectionCard>
      )}

      {tab === 'north-detail' && (
        <SectionCard tabAttached>
          <div className="flex gap-2 items-center">
            <StockCodeInput value={code} onChange={setCode} error={codeError} />
            <button type="button" disabled={loading} onClick={() => {
              if (!validate()) return;
              const hp = `/fund-flow/north-holding?code=${encodeURIComponent(trimmedCode)}`;
              if (hp === northHoldingPath) northHoldingQ.refetch(); else setNorthHoldingPath(hp);
              if (northTopPath) northTopQ.refetch(); else setNorthTopPath('/fund-flow/north-top');
            }}>查询北向明细</button>
          </div>
          {(northHoldingQ.data || northTopQ.data) ? (
            <>
              {northHoldingQ.data && (() => {
                const obj = extractObject(northHoldingQ.data);
                return (
                  <KpiGrid cols={4}>
                    <KpiCard title="持股数量" value={fmtNum(obj.shares as number)} suffix="股" />
                    <KpiCard title="占流通比" value={fmtPct(obj.ratio as number)} />
                    <KpiCard title="日增持" value={fmtNum(obj.change as number)} change={obj.change as number} />
                    <KpiCard title="股票代码" value={String(obj.code ?? '-')} />
                  </KpiGrid>
                );
              })()}
              {northTopQ.data && (() => {
                const rows = extractArray(northTopQ.data);
                return rows.length ? (
                  <DataTable rows={rows} columns={[
                    { key: 'code', label: '代码', render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
                    { key: 'name', label: '名称' },
                    { key: 'shares', label: '持股数', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 0) },
                    { key: 'ratio', label: '占比', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
                    { key: 'marketCap', label: '市值', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  ]} maxHeight={400} onExport={() => exportCSV(rows, '北向持仓TOP')} />
                ) : <EmptyState text="暂无北向TOP数据" />;
              })()}
            </>
          ) : <EmptyState text="输入代码查询北向持仓明细" />}
        </SectionCard>
      )}
    </PageContainer>
  );
}
