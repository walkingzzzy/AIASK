import type { FormEvent } from 'react';
import { Badge } from '@/components/ui';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import {
  stockFieldCls,
  stockPanelCls,
  stockPrimaryButtonCls,
  stockSecondaryButtonCls,
} from '@/app/stock/components/stock-panel-styles';
import type { Period, StockInfoTab } from '@/app/stock/lib/stock-detail-view';
import { getStockPeriodLabel } from '@/app/stock/lib/stock-detail-view';
import { fmtNum } from '@/lib/data-utils';

type StockQueryShellProps = {
  code: string;
  onCodeChange: (value: string) => void;
  codeError: string | null;
  period: Period;
  onPeriodChange: (value: Period) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  loading: boolean;
  refreshStatus: string;
  refreshTimeText: string;
  sentimentScore: number;
  onTabChange: (tab: StockInfoTab) => void;
};

export default function StockQueryShell({
  code,
  onCodeChange,
  codeError,
  period,
  onPeriodChange,
  onSubmit,
  loading,
  refreshStatus,
  refreshTimeText,
  sentimentScore,
  onTabChange,
}: StockQueryShellProps) {
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactLayout = hydrated ? compactLayoutDetected : true;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.06fr)_320px]">
      <div className={stockPanelCls}>
        <form id="stock-query-form" onSubmit={onSubmit} className="grid gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="eyebrow">Query Deck</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">代码、周期与刷新入口</h2>
              {!compactLayout ? (
                <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                  先固定标的与周期，再让下方所有图表、指标与资讯沿同一上下文刷新，避免每个模块各自加载、阅读顺序被打散。
                </p>
              ) : null}
            </div>
            <Badge variant="info">{getStockPeriodLabel(period)}</Badge>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-2 text-xs text-text-secondary">
              <span className="font-medium uppercase tracking-[0.12em] text-text-muted">股票代码</span>
              <input
                name="stockCode"
                value={code}
                onChange={(e) => onCodeChange(e.target.value)}
                maxLength={6}
                placeholder="如 600519"
                aria-label="股票代码"
                className={`${stockFieldCls} w-[180px]`}
              />
            </label>
            <label className="grid gap-2 text-xs text-text-secondary">
              <span className="font-medium uppercase tracking-[0.12em] text-text-muted">K线周期</span>
              <select
                name="period"
                value={period}
                onChange={(e) => onPeriodChange(e.target.value as Period)}
                aria-label="K线周期"
                className={`${stockFieldCls} w-[120px] pr-10`}
              >
                <option value="daily">日线</option>
                <option value="weekly">周线</option>
                <option value="monthly">月线</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={loading}
              aria-label="立即查询股票"
              className={stockPrimaryButtonCls}
            >
              {loading ? '加载中...' : '立即查询'}
            </button>
          </div>
          {codeError ? (
            <span className="text-xs text-error" role="alert">
              {codeError}
            </span>
          ) : null}
        </form>
      </div>

      {compactLayout ? (
        <details className={stockPanelCls}>
          <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开状态与下一步</summary>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">报价刷新</div>
              <div className="mt-3 text-sm font-semibold text-text-primary">{refreshStatus}</div>
              <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">短线情绪</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{fmtNum(sentimentScore, 0)}</div>
              <div className="mt-1 text-xs text-text-secondary">结合价格和量能一起理解更稳妥</div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={() => onTabChange('chart')} className={stockSecondaryButtonCls}>
              看主图
            </button>
            <button type="button" onClick={() => onTabChange('fund')} className={stockSecondaryButtonCls}>
              看资金流
            </button>
            <button type="button" onClick={() => onTabChange('valuation')} className={stockSecondaryButtonCls}>
              看估值
            </button>
          </div>
        </details>
      ) : (
        <div className={stockPanelCls}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">状态与下一步</div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">报价刷新</div>
              <div className="mt-3 text-sm font-semibold text-text-primary">{refreshStatus}</div>
              <div className="mt-1 text-xs text-text-secondary">{refreshTimeText}</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">短线情绪</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{fmtNum(sentimentScore, 0)}</div>
              <div className="mt-1 text-xs text-text-secondary">结合价格和量能一起理解更稳妥</div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={() => onTabChange('chart')} className={stockSecondaryButtonCls}>
              看主图
            </button>
            <button type="button" onClick={() => onTabChange('fund')} className={stockSecondaryButtonCls}>
              看资金流
            </button>
            <button type="button" onClick={() => onTabChange('valuation')} className={stockSecondaryButtonCls}>
              看估值
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
