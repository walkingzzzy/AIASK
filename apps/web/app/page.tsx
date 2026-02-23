'use client';

import { useMemo } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge } from '@/components/ui';
import { QuickAction, QuickActionGrid } from '@/components/ui/quick-action';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractObject, extractArray, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { BFF_BASE } from '@/lib/api';
import { LoadingState, ErrorState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import Link from 'next/link';
import { WatchlistButton } from '@/components/watchlist-button';
import { useWatchlistStore } from '@/store/watchlist-store';
import { useStockContext } from '@/store/stock-context';
import { tradingInterval } from '@/lib/trading-hours';

const poll = tradingInterval(60_000);

export default function HomePage() {
  const indexQ = useApiQuery<unknown>('/market/batch-quotes', {
    body: { codes: ['000001', '399001', '399006', '000688'] },
    refetchInterval: poll,
  });
  const limitUpQ = useApiQuery<unknown>('/market/limit-up-stats', { refetchInterval: poll });
  const northQ = useApiQuery<unknown>('/fund-flow/north', { refetchInterval: poll });
  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', { refetchInterval: poll });
  const healthQ = useApiQuery<unknown>('/health/mcp');
  const sectorQ = useApiQuery<unknown>('/market/blocks?blockType=industry&limit=20', { refetchInterval: poll });
  const sectorFlowQ = useApiQuery<unknown>('/fund-flow/sector', { refetchInterval: poll });
  const watchlistItems = useWatchlistStore((s) => s.items);
  const recentStocks = useStockContext((s) => s.recent);

  const isPending = indexQ.isPending || limitUpQ.isPending;
  const lastUpdated = indexQ.dataUpdatedAt ? new Date(indexQ.dataUpdatedAt) : null;

  const indices = useMemo(() => extractArray(indexQ.data, 'quotes', 'items', 'data'), [indexQ.data]);
  const luStats = extractObject(limitUpQ.data);
  const northFlows = extractArray(northQ.data, 'items', 'flows');
  const latestNorth = northFlows.length ? northFlows[northFlows.length - 1] : null;
  const fgObj = extractObject(fearGreedQ.data);
  const fgValue = Number(fgObj.index ?? fgObj.value ?? fgObj.fear_greed_index ?? 50);
  const fgLabel = fgValue <= 25 ? '极度恐惧' : fgValue <= 50 ? '恐惧' : fgValue <= 75 ? '贪婪' : '极度贪婪';

  const sectors = useMemo(() => extractArray(sectorQ.data, 'blocks', 'items', 'data'), [sectorQ.data]);
  const sectorFlows = useMemo(() => {
    const raw = extractArray(sectorFlowQ.data, 'flows', 'items', 'data');
    return raw.slice(0, 10).map((x) => ({
      label: String(x.name ?? x.sector ?? '').slice(0, 6),
      value: Number(x.netInflow ?? x.net_inflow ?? x.main_net_inflow ?? 0),
    }));
  }, [sectorFlowQ.data]);

  const health = healthQ.data as Record<string, unknown> | null;
  const mcp = (health?.mcp ?? {}) as Record<string, unknown>;
/* PLACEHOLDER_HOME_BOTTOM */

  return (
    <PageContainer>
      <h1>市场概览</h1>
      {isPending ? <LoadingState text="加载市场数据..." /> : null}

      {/* Market Pulse Bar */}
      <div className="glass rounded-xl p-4 mb-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <span className="text-sm font-medium">市场状态</span>
          <span className="text-xs text-text-muted">
            {new Date().toLocaleDateString('zh-CN', { weekday: 'long', month: 'long', day: 'numeric' })}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-text-secondary">
          {lastUpdated && <span>更新: {lastUpdated.toLocaleTimeString('zh-CN')}</span>}
          <span>恐贪: <span className={fgValue > 50 ? 'text-danger font-medium' : 'text-success font-medium'}>{fgValue.toFixed(0)}</span></span>
          <span>涨停: <span className="font-medium">{String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')}</span></span>
          <span>北向: <span className={Number(latestNorth?.total ?? latestNorth?.netInflow ?? 0) >= 0 ? 'text-danger font-medium' : 'text-success font-medium'}>{fmtAmount(latestNorth?.total ?? latestNorth?.netInflow)}</span></span>
        </div>
      </div>

      {/* Quick Actions */}
      <QuickActionGrid cols={5} className="mb-4">
        <QuickAction href="/market" icon="📈" title="查看行情" description="实时行情与板块数据" />
        <QuickAction href="/stock" icon="🔍" title="个股分析" description="技术面/基本面/资金流" />
        <QuickAction href="/paper-trading" icon="💹" title="模拟交易" description="零风险模拟下单" />
        <QuickAction href="/strategy-market" icon="🧪" title="策略超市" description="量化策略浏览与订阅" />
        <QuickAction href="/backtest" icon="📊" title="回测分析" description="历史数据验证策略" />
      </QuickActionGrid>

      {/* Multi-Index Quotes */}
      <SectionCard className="p-4">
        <h3 className="mt-0">主要指数</h3>
        {indexQ.error ? <ErrorState text={indexQ.error} /> : null}
        {indices.length > 0 ? (
          <KpiGrid cols={4}>
            {indices.map((q, i) => {
              const chg = Number(q.changePercent ?? q.change_pct ?? q.changePct ?? 0);
              return (
                <KpiCard
                  key={i}
                  title={String(q.name ?? q.index_name ?? q.code ?? `指数${i + 1}`)}
                  value={fmtNum(q.price ?? q.close ?? q.current, 2)}
                  change={chg}
                />
              );
            })}
          </KpiGrid>
        ) : !indexQ.isPending ? (
          <KpiGrid cols={4}>
            <KpiCard title="上证指数" value="-" />
            <KpiCard title="深证成指" value="-" />
            <KpiCard title="创业板指" value="-" />
            <KpiCard title="科创50" value="-" />
          </KpiGrid>
        ) : null}
      </SectionCard>

      {/* Sector Heatmap */}
      {sectors.length > 0 && (
        <SectionCard className="p-4 mt-4">
          <h3 className="mt-0">板块热力</h3>
          <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
            {sectors.map((s, i) => {
              const chg = Number(s.avgChange ?? s.avg_change ?? s.change_pct ?? 0);
              return (
                <Link key={i} href={`/market?tab=blocks&block=${encodeURIComponent(String(s.code ?? s.block_code ?? ''))}`}
                  className={`glass rounded-lg p-2 text-center text-xs no-underline text-inherit ${chg >= 0 ? 'border border-danger/30' : 'border border-success/30'} transition-transform hover:scale-105`}
                  aria-label={`${String(s.name ?? '')} ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`}>
                  <div className="truncate font-medium">{String(s.name ?? '').slice(0, 6)}</div>
                  <div className={`text-sm font-bold ${chg >= 0 ? 'text-danger' : 'text-success'}`}>{chg >= 0 ? '+' : ''}{chg.toFixed(2)}%</div>
                </Link>
              );
            })}
          </div>
        </SectionCard>
      )}

      {/* Fear-Greed + Sector Fund Flow side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        <SectionCard className="p-4">
          <h3 className="mt-0">恐贪指数</h3>
          {fearGreedQ.error ? <ErrorState text={fearGreedQ.error} /> : null}
          {fearGreedQ.data != null ? (
            <GaugeChart
              value={fgValue}
              min={0}
              max={100}
              title={fgLabel}
              height={200}
              zones={[
                { start: 0, end: 25, color: COLORS.down },
                { start: 25, end: 50, color: COLORS.warning },
                { start: 50, end: 75, color: '#f97316' },
                { start: 75, end: 100, color: COLORS.up },
              ]}
            />
          ) : null}
        </SectionCard>

        <SectionCard className="p-4">
          <h3 className="mt-0">板块资金流向</h3>
          {sectorFlowQ.error ? <ErrorState text={sectorFlowQ.error} /> : null}
          {sectorFlows.length > 0 ? (
            <BarChart items={sectorFlows} height={200} yAxisName="净流入(亿)" colorByValue horizontal />
          ) : !sectorFlowQ.isPending ? <p className="text-text-muted text-sm">暂无数据</p> : null}
        </SectionCard>
      </div>

      {/* Limit-Up Stats + North Fund side by side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        <SectionCard className="p-4">
          <h3 className="mt-0">涨停统计</h3>
          {limitUpQ.error ? <ErrorState text={limitUpQ.error} /> : null}
          <KpiGrid cols={3}>
            <KpiCard title="涨停家数" value={String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')} />
            <KpiCard title="首板" value={String(luStats.firstBoard ?? luStats.first_board ?? '-')} />
            <KpiCard title="连板成功率" value={fmtPct(luStats.successRate ?? luStats.success_rate)} />
          </KpiGrid>
        </SectionCard>

        <SectionCard className="p-4">
          <h3 className="mt-0">北向资金</h3>
          {northQ.error ? <ErrorState text={northQ.error} /> : null}
          {latestNorth ? (
            <KpiGrid cols={2}>
              <KpiCard title="今日净流入" value={fmtAmount(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow)} change={Number(latestNorth.total ?? latestNorth.netInflow ?? latestNorth.net_inflow ?? null)} />
              <KpiCard title="累计净流入" value={fmtAmount(latestNorth.cumulative ?? latestNorth.cumNetInflow ?? latestNorth.cum_net_inflow)} />
            </KpiGrid>
          ) : null}
        </SectionCard>
      </div>

      {/* North Fund Trend */}
      {northFlows.length > 1 && (
        <SectionCard className="p-4 mt-4">
          <h3 className="mt-0">北向资金走势（近20日）</h3>
          <BarChart
            items={northFlows.slice(-20).map((x) => ({
              label: String(x.date ?? '').slice(5),
              value: Number(x.total ?? x.netInflow ?? x.net_inflow ?? 0),
            }))}
            height={240}
            yAxisName="净流入(亿)"
            colorByValue
          />
        </SectionCard>
      )}

      {/* Watchlist + Recent Stocks */}
      {(watchlistItems.length > 0 || recentStocks.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
          {watchlistItems.length > 0 && (
            <SectionCard className="p-4">
              <h3 className="mt-0">我的自选 ({watchlistItems.length})</h3>
              <div className="space-y-1.5">
                {watchlistItems.slice(0, 8).map((item) => (
                  <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30">
                    <StockLink code={item.code} name={item.name || item.code} />
                    <WatchlistButton code={item.code} name={item.name} />
                  </div>
                ))}
              </div>
            </SectionCard>
          )}
          {recentStocks.length > 0 && (
            <SectionCard className="p-4">
              <h3 className="mt-0">最近查看</h3>
              <div className="space-y-1.5">
                {recentStocks.slice(0, 8).map((item) => (
                  <div key={item.code} className="flex items-center justify-between text-sm py-1 border-b border-border/30">
                    <StockLink code={item.code} name={item.name || item.code} />
                    <span className="text-xs text-text-muted">{new Date(item.ts).toLocaleDateString('zh-CN')}</span>
                  </div>
                ))}
              </div>
            </SectionCard>
          )}
        </div>
      )}

      <details className="mt-6">
        <summary className="cursor-pointer text-text-secondary text-sm">BFF / MCP 健康状态</summary>
        <SectionCard className="p-4 mt-2">
          {healthQ.error ? <ErrorState text={healthQ.error} /> : null}
          {health ? (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>服务: <Badge variant={String(health.status) === 'ok' ? 'success' : 'warning'}>{String(health.status ?? '-')}</Badge></div>
              <div>MCP: <Badge variant={mcp.reachable ? 'success' : 'danger'}>{mcp.reachable ? '已连接' : '未连接'}</Badge></div>
              <div>工具数: {String(mcp.toolCount ?? '-')} / {String(mcp.expectedTools ?? '-')}</div>
              <div>匹配: <Badge variant={mcp.matched ? 'success' : 'warning'}>{String(mcp.matched ?? '-')}</Badge></div>
            </div>
          ) : <p className="text-text-secondary text-sm">无法连接 BFF: {BFF_BASE}</p>}
        </SectionCard>
      </details>
    </PageContainer>
  );
}
