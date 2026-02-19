'use client';

import { useState } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput } from '@/components/ui';
import { KpiCard, KpiGrid, DataTable } from '@/components/ui';
import { BarChart, LineChart, COLORS } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt } from '@/lib/api';

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

  const stockMut = useApiMutation<unknown>();
  const sectorMut = useApiMutation<unknown>();
  const conceptMut = useApiMutation<unknown>();
  const northMut = useApiMutation<unknown>();
  const dragonMut = useApiMutation<unknown>();
  const marginMut = useApiMutation<unknown>();
  const marginRankMut = useApiMutation<unknown>();
  const blockTradesMut = useApiMutation<unknown>();
  const northHoldingMut = useApiMutation<unknown>();
  const northTopMut = useApiMutation<unknown>();

  const loading = stockMut.isPending || sectorMut.isPending || conceptMut.isPending
    || northMut.isPending || dragonMut.isPending || marginMut.isPending
    || marginRankMut.isPending || blockTradesMut.isPending
    || northHoldingMut.isPending || northTopMut.isPending;
  const error = codeError || stockMut.error || sectorMut.error || conceptMut.error
    || northMut.error || dragonMut.error || marginMut.error
    || marginRankMut.error || blockTradesMut.error
    || northHoldingMut.error || northTopMut.error;

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
              stockMut.trigger(`/fund-flow/stock?code=${encodeURIComponent(trimmedCode)}`);
            }}>查询</button>
          </div>
          {stockMut.data ? (() => {
            const items = extractArray(stockMut.data, 'flows');
            return items.length ? (
              <BarChart
                items={items.map((x: Record<string, unknown>) => ({
                  label: fmt(x.date as string || x.name as string),
                  value: (x.netInflow as number) ?? 0,
                }))}
                height={360}
                yAxisName="净流入"
                colorByValue
              />
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="输入代码查询个股资金流" />}
        </SectionCard>
      )}

      {tab === 'sector' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => sectorMut.trigger('/fund-flow/sector')}>
            加载板块资金流
          </button>
          {sectorMut.data ? (() => {
            const rows = extractArray(sectorMut.data, 'flows');
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'name', label: '板块名称' },
                  { key: 'stockCount', label: '股票数', align: 'right' as const },
                  { key: 'avgChange', label: '平均涨幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-red-500' : 'text-green-500'}>{fmtPct(v as number)}</span> },
                  { key: 'leaderName', label: '领涨股' },
                ]}
                maxHeight={400}
                onExport={() => exportCSV(rows, '板块资金流')}
              />
            ) : <EmptyState text="暂无数据" />;
          })() : <EmptyState text="点击按钮加载板块资金流" />}
        </SectionCard>
      )}

      {tab === 'concept' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => conceptMut.trigger('/fund-flow/concept')}>
            加载概念资金流
          </button>
          {conceptMut.data ? (() => {
            const rows = extractArray(conceptMut.data, 'flows');
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'name', label: '概念名称' },
                  { key: 'stockCount', label: '股票数', align: 'right' as const },
                  { key: 'avgChange', label: '平均涨幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-red-500' : 'text-green-500'}>{fmtPct(v as number)}</span> },
                  { key: 'leaderName', label: '领涨股' },
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
          <button type="button" disabled={loading} onClick={() => northMut.trigger('/fund-flow/north')}>
            加载北向资金
          </button>
          {northMut.data ? (() => {
            const items = extractArray(northMut.data, 'flows');
            return items.length ? (
              <LineChart
                categories={items.map((x: Record<string, unknown>) => fmt(x.date as string))}
                series={[{
                  name: '北向净流入',
                  data: items.map((x: Record<string, unknown>) => (x.netInflow as number) ?? 0),
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
          <button type="button" disabled={loading} onClick={() => dragonMut.trigger('/fund-flow/dragon-tiger')}>
            加载龙虎榜
          </button>
          {dragonMut.data ? (() => {
            const rows = extractArray(dragonMut.data);
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'code', label: '代码' },
                  { key: 'name', label: '名称' },
                  { key: 'closePrice', label: '收盘价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                  { key: 'changePercent', label: '涨跌幅', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-red-500' : 'text-green-500'}>{fmtPct(v as number)}</span> },
                  { key: 'reason', label: '上榜原因' },
                  { key: 'buyAmount', label: '买入额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'sellAmount', label: '卖出额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'netAmount', label: '净买入', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-red-500' : 'text-green-500'}>{fmtAmount(v as number)}</span> },
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
              marginMut.trigger(`/fund-flow/margin${params}`);
            }}>查询融资融券</button>
          </div>
          {marginMut.data ? (() => {
            const rows = extractArray(marginMut.data);
            const obj = extractObject(marginMut.data);
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
                  <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, '融资融券')} />
                ) : <EmptyState text="暂无数据" />}
              </>
            );
          })() : <EmptyState text="查询融资融券数据" />}
          <div className="mt-3">
            <button type="button" disabled={loading} onClick={() => marginRankMut.trigger('/fund-flow/margin-ranking')}>
              融资融券排名
            </button>
            {marginRankMut.data ? (() => {
              const rows = extractArray(marginRankMut.data);
              return rows.length ? (
                <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, '融资融券排名')} />
              ) : <EmptyState text="暂无数据" />;
            })() : null}
          </div>
        </SectionCard>
      )}

      {tab === 'block-trades' && (
        <SectionCard tabAttached>
          <button type="button" disabled={loading} onClick={() => blockTradesMut.trigger('/fund-flow/block-trades')}>
            加载大宗交易
          </button>
          {blockTradesMut.data ? (() => {
            const rows = extractArray(blockTradesMut.data);
            return rows.length ? (
              <DataTable
                rows={rows}
                columns={[
                  { key: 'date', label: '日期' },
                  { key: 'code', label: '代码' },
                  { key: 'name', label: '名称' },
                  { key: 'price', label: '成交价', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                  { key: 'volume', label: '成交量', align: 'right' as const, render: (v: unknown) => fmtNum(v as number) },
                  { key: 'amount', label: '成交额', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
                  { key: 'premium', label: '溢价率', align: 'right' as const, render: (v: unknown) => <span className={(v as number) >= 0 ? 'text-red-500' : 'text-green-500'}>{fmtPct(v as number)}</span> },
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
              northHoldingMut.trigger(`/fund-flow/north-holding?code=${encodeURIComponent(trimmedCode)}`);
              northTopMut.trigger('/fund-flow/north-top');
            }}>查询北向明细</button>
          </div>
          {(northHoldingMut.data || northTopMut.data) ? (
            <>
              {northHoldingMut.data && (() => {
                const obj = extractObject(northHoldingMut.data);
                return (
                  <KpiGrid cols={4}>
                    <KpiCard title="持股数量" value={fmtNum(obj.holdVolume as number ?? obj.sharehold_num as number)} suffix="股" />
                    <KpiCard title="持股市值" value={fmtAmount(obj.holdMarketValue as number ?? obj.market_value as number)} />
                    <KpiCard title="占流通比" value={fmtPct(obj.holdRatio as number ?? obj.ratio as number)} />
                    <KpiCard title="日增持" value={fmtNum(obj.changeVolume as number ?? obj.change as number)} change={obj.changeVolume as number ?? obj.change as number} />
                  </KpiGrid>
                );
              })()}
              {northTopMut.data && (() => {
                const rows = extractArray(northTopMut.data);
                return rows.length ? (
                  <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, '北向持仓TOP')} />
                ) : <EmptyState text="暂无北向TOP数据" />;
              })()}
            </>
          ) : <EmptyState text="输入代码查询北向持仓明细" />}
        </SectionCard>
      )}
    </PageContainer>
  );
}