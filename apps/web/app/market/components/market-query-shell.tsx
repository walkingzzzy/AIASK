import type { FormEvent } from 'react';
import { SectionCard, TabBar } from '@/components/ui';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import {
  marketChipButtonCls,
  marketFieldCls,
  marketNoteCardCls,
  marketPanelCls,
  marketPrimaryButtonCls,
  marketSecondaryButtonCls,
  marketSelectCls,
} from '@/app/market/components/market-panel-styles';
import {
  MARKET_STARTER_CODES,
  MARKET_VIEW_PRESETS,
  TABS,
  type MarketTab,
  type Period,
  type SavedMarketView,
} from '@/app/market/lib/market-view';

type MarketQueryShellProps = {
  code: string;
  onCodeChange: (value: string) => void;
  codeError: string | null;
  period: Period;
  onPeriodChange: (value: Period) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  showPrimaryLoading: boolean;
  onSaveCurrentView: () => void;
  submittedCode: string | null;
  onUseStarterCode: (code: string) => void;
  onApplyPreset: (preset: Partial<SavedMarketView>, label?: string) => void;
  activeTab: MarketTab;
  onActiveTabChange: (tab: MarketTab) => void;
  cacheStatusItems: Array<{ label: string; value: string }>;
  activeDisplayName: string;
  activeDisplayCode: string;
  activePeriodLabel: string;
  freshnessLabel: string;
};

export default function MarketQueryShell({
  code,
  onCodeChange,
  codeError,
  period,
  onPeriodChange,
  onSubmit,
  showPrimaryLoading,
  onSaveCurrentView,
  submittedCode,
  onUseStarterCode,
  onApplyPreset,
  activeTab,
  onActiveTabChange,
  cacheStatusItems,
  activeDisplayName,
  activeDisplayCode,
  activePeriodLabel,
  freshnessLabel,
}: MarketQueryShellProps) {
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactLayout = hydrated ? compactLayoutDetected : true;
  const visibleCacheItems = compactLayout ? [] : cacheStatusItems;

  return (
    <SectionCard className="mt-0">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_320px]">
        <div className="grid gap-4">
          <div className={`${marketPanelCls} rounded-[30px]`}>
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <div className="eyebrow">查询与预设</div>
                  <h2 className="mt-2">{compactLayout ? '先完成输入' : '先完成输入，再进入主图工作区'}</h2>
                  {!compactLayout ? (
                    <p className="mt-2 text-sm leading-6 text-text-secondary">
                      用统一的输入和预设切换路径，减少盘中重复填写与多次切 tab 的动作。
                    </p>
                  ) : null}
                </div>
                {!compactLayout ? (
                  <div className="flex flex-wrap gap-2">
                    {MARKET_STARTER_CODES.map((item) => (
                      <button
                        key={`starter-inline-${item.code}`}
                        type="button"
                        onClick={() => onUseStarterCode(item.code)}
                        className={`${marketChipButtonCls} ${submittedCode === item.code ? 'border-primary/28 bg-primary/10 text-primary shadow-[0_16px_30px_-24px_rgba(11,107,203,0.46)]' : ''}`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <form onSubmit={onSubmit} className={`grid gap-3 ${compactLayout ? 'md:grid-cols-[minmax(0,1fr)_140px]' : 'xl:grid-cols-[minmax(0,220px)_140px_minmax(0,1fr)]'}`}>
                <label className="flex flex-col gap-2">
                  <span className="metric-label">股票代码</span>
                  <div className="flex flex-col gap-1">
                    <input
                      id="market-code"
                      value={code}
                      onChange={(e) => onCodeChange(e.target.value)}
                      maxLength={6}
                      placeholder="输入股票代码"
                      aria-label="股票代码"
                      aria-invalid={codeError ? true : undefined}
                      className={`w-full ${marketFieldCls}`}
                    />
                    {codeError ? <span className="px-1 text-xs text-error">{codeError}</span> : null}
                  </div>
                </label>

                <label className="flex flex-col gap-2">
                  <span className="metric-label">K 线周期</span>
                  <select
                    value={period}
                    onChange={(e) => onPeriodChange(e.target.value as Period)}
                    aria-label="K线周期"
                    className={`w-full ${marketSelectCls}`}
                  >
                    <option value="daily">日线</option>
                    <option value="weekly">周线</option>
                    <option value="monthly">月线</option>
                  </select>
                </label>

                <div className={`flex flex-col gap-2 ${compactLayout ? 'md:col-span-2' : ''}`}>
                  <span className="metric-label">执行动作</span>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="submit"
                      disabled={showPrimaryLoading}
                      aria-label="查询主行情工作台"
                      className={marketPrimaryButtonCls}
                    >
                      {showPrimaryLoading ? '加载中' : '查询主行情'}
                    </button>
                    {!compactLayout ? (
                      <button type="button" onClick={onSaveCurrentView} className={marketSecondaryButtonCls}>
                        保存视图
                      </button>
                    ) : null}
                  </div>
                </div>
              </form>

              {!compactLayout ? (
                <div className="grid gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="metric-label">视图预设</span>
                    {MARKET_VIEW_PRESETS.map((preset) => (
                      <button
                        key={preset.key}
                        type="button"
                        onClick={() => onApplyPreset(preset.apply(), preset.label)}
                        className={marketChipButtonCls}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className={`${marketPanelCls} rounded-[30px]`}>
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="overflow-x-auto">
                <TabBar tabs={TABS} active={activeTab} onChange={onActiveTabChange} />
              </div>
              <div className="flex flex-wrap gap-2">
                {visibleCacheItems.map((item) => (
                  <div key={item.label} className={`${marketNoteCardCls} px-3 py-2`}>
                    <span className="metric-label">{item.label}</span>
                    <div className="mt-1 text-sm font-medium text-text-primary">{item.value}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {compactLayout ? (
          <details className={`${marketPanelCls} rounded-[26px]`}>
            <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开查询状态与预设</summary>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div className={`${marketNoteCardCls} px-4 py-3`}>
                <div className="metric-label">当前代码</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{activeDisplayCode || '未选择'}</div>
              </div>
              <div className={`${marketNoteCardCls} px-4 py-3`}>
                <div className="metric-label">当前周期</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{activePeriodLabel}</div>
              </div>
              <div className={`${marketNoteCardCls} px-4 py-3`}>
                <div className="metric-label">刷新时间</div>
                <div className="mt-2 text-sm font-medium text-text-primary">{freshnessLabel}</div>
              </div>
              <div className={`${marketNoteCardCls} px-4 py-3`}>
                <div className="metric-label">建议顺序</div>
                <div className="mt-2 text-sm leading-6 text-text-secondary">查询 → 主图 → 摘要 → 下一步。</div>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              <div>
                <div className="metric-label">常用标的</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {MARKET_STARTER_CODES.map((item) => (
                    <button
                      key={`starter-detail-${item.code}`}
                      type="button"
                      onClick={() => onUseStarterCode(item.code)}
                      className={`${marketChipButtonCls} ${submittedCode === item.code ? 'border-primary/28 bg-primary/10 text-primary shadow-[0_16px_30px_-24px_rgba(11,107,203,0.46)]' : ''}`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="metric-label">视图预设</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {MARKET_VIEW_PRESETS.map((preset) => (
                    <button
                      key={preset.key}
                      type="button"
                      onClick={() => onApplyPreset(preset.apply(), preset.label)}
                      className={marketChipButtonCls}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={onSaveCurrentView} className={marketSecondaryButtonCls}>
                  保存当前视图
                </button>
                {cacheStatusItems.map((item) => (
                  <div key={item.label} className={`${marketNoteCardCls} px-3 py-2`}>
                    <span className="metric-label">{item.label}</span>
                    <div className="mt-1 text-sm font-medium text-text-primary">{item.value}</div>
                  </div>
                ))}
              </div>
            </div>
          </details>
        ) : (
        <div className={`${marketPanelCls} rounded-[30px]`}>
          <div>
            <div className="eyebrow">当前视图</div>
            <h2 className="mt-2">查询状态</h2>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              当前工作流已锁定 {activeDisplayName}，下一步优先看 {activePeriodLabel} 主图和摘要。
            </p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-1">
            <div className={`${marketNoteCardCls} px-4 py-3`}>
              <div className="metric-label">当前代码</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{activeDisplayCode || '未选择'}</div>
            </div>
            <div className={`${marketNoteCardCls} px-4 py-3`}>
              <div className="metric-label">当前周期</div>
              <div className="mt-2 text-base font-semibold text-text-primary">{activePeriodLabel}</div>
            </div>
            <div className={`${marketNoteCardCls} px-4 py-3`}>
              <div className="metric-label">刷新时间</div>
              <div className="mt-2 text-sm font-medium text-text-primary">{freshnessLabel}</div>
            </div>
            <div className={`${marketNoteCardCls} px-4 py-3`}>
              <div className="metric-label">建议阅读顺序</div>
              <div className="mt-2 text-sm leading-6 text-text-secondary">
                查询 → 主图 → 摘要 → 下一步。
              </div>
            </div>
          </div>
        </div>
        )}
      </div>
    </SectionCard>
  );
}
