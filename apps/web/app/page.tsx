'use client';

import { useEffect } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { extractObject, extractArray, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { BFF_BASE } from '@/lib/api';
import { LoadingState, ErrorState } from '@/components/status-state';

export default function HomePage() {
  const indexMut = useApiMutation<unknown>();
  const limitUpMut = useApiMutation<unknown>();
  const northMut = useApiMutation<unknown>();
  const fearGreedMut = useApiMutation<unknown>();
  const healthMut = useApiMutation<unknown>();

  useEffect(() => {
    indexMut.trigger('/market/index-quote?indexCode=000001');
    limitUpMut.trigger('/market/limit-up-stats');
    northMut.trigger('/fund-flow/north');
    fearGreedMut.trigger('/sentiment/fear-greed');
    healthMut.trigger('/health/mcp');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isPending = indexMut.isPending || limitUpMut.isPending || northMut.isPending || fearGreedMut.isPending;

  const idx = extractObject(indexMut.data);
  const luStats = extractObject(limitUpMut.data);
  const northFlows = extractArray(northMut.data, 'flows');
  const latestNorth = northFlows.length ? northFlows[northFlows.length - 1] : null;
  const fgObj = extractObject(fearGreedMut.data);
  const fgValue = Number(fgObj.index ?? fgObj.value ?? fgObj.fear_greed_index ?? 50);
  const fgLabel = fgValue <= 25 ? '极度恐惧' : fgValue <= 50 ? '恐惧' : fgValue <= 75 ? '贪婪' : '极度贪婪';

  const health = healthMut.data as Record<string, unknown> | null;
  const mcp = (health?.mcp ?? {}) as Record<string, unknown>;

  return (
    <PageContainer>
      <h1>市场概览</h1>
      {isPending ? <LoadingState text="加载市场数据..." /> : null}

      {/* PLACEHOLDER_SECTIONS */}

      <SectionCard className="p-4">
        <h3 className="mt-0">主要指数</h3>
        {indexMut.error ? <ErrorState text={indexMut.error} /> : null}
        <KpiGrid cols={4}>
          <KpiCard title="指数名称" value={String(idx.name ?? idx.index_name ?? '上证指数')} />
          <KpiCard title="最新点位" value={fmtNum(idx.price ?? idx.close ?? idx.current, 2)} change={Number(idx.changePercent ?? idx.change_pct ?? null)} />
          <KpiCard title="成交额" value={fmtAmount(idx.amount ?? idx.turnover)} />
          <KpiCard title="涨跌幅" value={fmtPct(idx.changePercent ?? idx.change_pct)} change={Number(idx.changePercent ?? idx.change_pct ?? null)} />
        </KpiGrid>
      </SectionCard>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        <SectionCard className="p-4">
          <h3 className="mt-0">涨停统计</h3>
          {limitUpMut.error ? <ErrorState text={limitUpMut.error} /> : null}
          <KpiGrid cols={3}>
            <KpiCard title="涨停家数" value={String(luStats.totalLimitUp ?? luStats.total ?? luStats.count ?? '-')} />
            <KpiCard title="首板" value={String(luStats.firstBoard ?? luStats.first_board ?? '-')} />
            <KpiCard title="连板成功率" value={fmtPct(luStats.successRate ?? luStats.success_rate)} />
          </KpiGrid>
        </SectionCard>

        <SectionCard className="p-4">
          <h3 className="mt-0">恐贪指数</h3>
          {fearGreedMut.error ? <ErrorState text={fearGreedMut.error} /> : null}
          {fearGreedMut.data != null ? (
            <div className="flex items-center gap-4">
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
            </div>
          ) : null}
        </SectionCard>
      </div>

      <SectionCard className="p-4 mt-4">
        <h3 className="mt-0">北向资金</h3>
        {northMut.error ? <ErrorState text={northMut.error} /> : null}
        {latestNorth ? (
          <KpiGrid cols={3}>
            <KpiCard title="日期" value={String(latestNorth.date ?? '-')} />
            <KpiCard title="净流入" value={fmtAmount(latestNorth.netInflow ?? latestNorth.net_inflow)} change={Number(latestNorth.netInflow ?? latestNorth.net_inflow ?? null)} />
            <KpiCard title="累计净流入" value={fmtAmount(latestNorth.cumNetInflow ?? latestNorth.cum_net_inflow)} />
          </KpiGrid>
        ) : null}
        {northFlows.length > 1 ? (
          <BarChart
            items={northFlows.slice(-20).map((x) => ({
              label: String(x.date ?? '').slice(5),
              value: Number(x.netInflow ?? x.net_inflow ?? 0),
            }))}
            height={240}
            yAxisName="净流入(亿)"
            colorByValue
          />
        ) : null}
      </SectionCard>

      <details className="mt-6">
        <summary className="cursor-pointer text-text-secondary text-sm">BFF / MCP 健康状态</summary>
        <SectionCard className="p-4 mt-2">
          {healthMut.error ? <ErrorState text={healthMut.error} /> : null}
          {health ? (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>服务: <Badge variant={String(health.status) === 'ok' ? 'success' : 'warning'}>{String(health.status ?? '-')}</Badge></div>
              <div>MCP: <Badge variant={mcp.reachable ? 'success' : 'danger'}>{mcp.reachable ? '已连接' : '未连接'}</Badge></div>
              <div>工具数: {String(mcp.toolCount ?? '-')} / {String(mcp.expectedTools ?? '-')}</div>
              <div>匹配: <Badge variant={mcp.matched ? 'success' : 'warning'}>{String(mcp.matched ?? '-')}</Badge></div>
              <div>来源: {String(mcp.source ?? '-')}</div>
              <div>时间: {String(health.timestamp ?? '-')}</div>
            </div>
          ) : <p className="text-text-secondary text-sm">无法连接 BFF: {BFF_BASE}</p>}
        </SectionCard>
      </details>
    </PageContainer>
  );
}