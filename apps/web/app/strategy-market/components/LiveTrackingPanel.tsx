'use client';

import { SectionCard, KpiCard, KpiGrid, DataTable } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { LoadingState } from '@/components/status-state';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import type { SignalStatsResponse, SignalsResponse } from '../types';

export type LiveTrackingPanelProps = {
  stats: SignalStatsResponse | null | undefined;
  signals: SignalsResponse | null | undefined;
  statsLoading: boolean;
  signalsLoading: boolean;
};

export function LiveTrackingPanel({
  stats,
  signals,
  statsLoading,
  signalsLoading,
}: LiveTrackingPanelProps) {
  const st = (stats && typeof stats === 'object' ? stats : {}) as SignalStatsResponse;
  const sig = (signals && typeof signals === 'object' ? signals : {}) as SignalsResponse;
  const forwardDays = Object.keys(st.hit_rate ?? {}).map(Number).sort((a, b) => a - b);
  const icCategories = forwardDays.map((day) => `${day}D`);
  const icValues = forwardDays.map((day) => st.forward_ic?.[day] ?? 0);
  const sharpeValues = forwardDays.map((day) => st.forward_sharpe?.[day] ?? 0);

  return (
    <div className="mt-4 space-y-4">
      {statsLoading ? (
        <LoadingState text="加载信号统计..." />
      ) : (
        <>
          <KpiGrid cols={4}>
            <KpiCard title="总信号数" value={st.total_signals ?? 0} />
            {forwardDays.slice(0, 1).map((day) => <KpiCard key={`hr-${day}`} title={`${day}D 命中率`} value={fmtPct(st.hit_rate?.[day] ?? 0)} />)}
            {forwardDays.slice(0, 1).map((day) => <KpiCard key={`ic-${day}`} title={`${day}D 前向IC`} value={fmtNum(st.forward_ic?.[day] ?? 0, 4)} />)}
            {forwardDays.slice(0, 1).map((day) => <KpiCard key={`sp-${day}`} title={`${day}D 前向Sharpe`} value={fmtNum(st.forward_sharpe?.[day] ?? 0, 4)} />)}
          </KpiGrid>

          {forwardDays.length > 0 ? (
            <SectionCard className="p-3">
              <h3 className="mt-0">前向验证指标</h3>
              <DataTable
                columns={[
                  { key: 'period', label: '周期' },
                  { key: 'hit_rate', label: '命中率' },
                  { key: 'forward_ic', label: '前向IC' },
                  { key: 'forward_sharpe', label: '前向Sharpe' },
                ]}
                rows={forwardDays.map((day) => ({
                  period: `${day} 天`,
                  hit_rate: fmtPct(st.hit_rate?.[day] ?? 0),
                  forward_ic: fmtNum(st.forward_ic?.[day] ?? 0, 4),
                  forward_sharpe: fmtNum(st.forward_sharpe?.[day] ?? 0, 4),
                }))}
              />
            </SectionCard>
          ) : null}

          {icCategories.length > 1 ? (
            <SectionCard className="p-3">
              <h3 className="mt-0">前向 IC / Sharpe 趋势</h3>
              <LineChart
                categories={icCategories}
                series={[
                  { name: '前向IC', data: icValues, color: '#1a73e8' },
                  { name: '前向Sharpe', data: sharpeValues, color: '#f59e0b', yAxisIndex: 1 },
                ]}
                height={240}
                yAxisName="IC"
                y2AxisName="Sharpe"
              />
            </SectionCard>
          ) : null}
        </>
      )}

      <SectionCard className="p-3">
        <h3 className="mt-0">信号历史 {sig.subscriber === false ? <span className="text-text-secondary text-xs ml-2">(非订阅者，数据延迟1-3天)</span> : null}</h3>
        {signalsLoading ? (
          <LoadingState text="加载信号..." />
        ) : sig.signals?.length ? (
          <DataTable
            columns={[
              { key: 'signal_date', label: '日期' },
              { key: 'code', label: '代码' },
              { key: 'direction', label: '方向' },
              { key: 'score', label: '强度' },
            ]}
            rows={sig.signals.map((item) => ({
              signal_date: item.signal_date ?? '-',
              code: item.code ?? '-',
              direction: item.signal === 1 ? '买入' : item.signal === -1 ? '卖出' : '持有',
              score: fmtNum(item.score ?? 0, 2),
            }))}
          />
        ) : (
          <p className="text-text-secondary text-sm">暂无信号数据</p>
        )}
      </SectionCard>
    </div>
  );
}
