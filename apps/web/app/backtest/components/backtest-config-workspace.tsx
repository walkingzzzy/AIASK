import type { FormEvent } from 'react';
import { SectionCard, StockCodeInput } from '@/components/ui';
import {
  backtestChipButtonCls,
  backtestInputCls,
  backtestLabelCls,
  backtestNoteCardCls,
  backtestPrimaryButtonCls,
} from '@/app/backtest/components/backtest-panel-styles';

type StrategyOption = { value: string; label: string };
type CostPreset = { key: string; label: string; initialCapital: number; commission: number; slippage: number };

type BacktestConfigWorkspaceProps = {
  code: string;
  setCode: (value: string) => void;
  codeError: string | null;
  strategy: string;
  setStrategy: (value: string) => void;
  strategies: readonly StrategyOption[];
  startDate: string;
  setStartDate: (value: string) => void;
  endDate: string;
  setEndDate: (value: string) => void;
  shortPeriod: number;
  setShortPeriod: (value: number) => void;
  longPeriod: number;
  setLongPeriod: (value: number) => void;
  lookback: number;
  setLookback: (value: number) => void;
  threshold: number;
  setThreshold: (value: number) => void;
  rsiPeriod: number;
  setRsiPeriod: (value: number) => void;
  oversold: number;
  setOversold: (value: number) => void;
  overbought: number;
  setOverbought: (value: number) => void;
  showAdvanced: boolean;
  setShowAdvanced: (value: boolean) => void;
  initialCapital: number;
  setInitialCapital: (value: number) => void;
  commission: number;
  setCommission: (value: number) => void;
  slippage: number;
  setSlippage: (value: number) => void;
  costPresets: readonly CostPreset[];
  onApplyCostPreset: (preset: CostPreset) => void;
  configurationSummary: string;
  loading: boolean;
  runBacktest: (event: FormEvent<HTMLFormElement>) => void;
};

export default function BacktestConfigWorkspace({
  code,
  setCode,
  codeError,
  strategy,
  setStrategy,
  strategies,
  startDate,
  setStartDate,
  endDate,
  setEndDate,
  shortPeriod,
  setShortPeriod,
  longPeriod,
  setLongPeriod,
  lookback,
  setLookback,
  threshold,
  setThreshold,
  rsiPeriod,
  setRsiPeriod,
  oversold,
  setOversold,
  overbought,
  setOverbought,
  showAdvanced,
  setShowAdvanced,
  initialCapital,
  setInitialCapital,
  commission,
  setCommission,
  slippage,
  setSlippage,
  costPresets,
  onApplyCostPreset,
  configurationSummary,
  loading,
  runBacktest,
}: BacktestConfigWorkspaceProps) {
  return (
    <SectionCard className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">配置步骤</div>
          <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">回测配置</h3>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            按“基础参数 → 策略参数 → 成本假设”的顺序完成配置，便于复查样本、交易规则和成本口径。
          </p>
        </div>
      </div>

      <form id="backtest-config-form" onSubmit={runBacktest} className="mt-4 grid gap-4 xl:grid-cols-3">
        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="eyebrow">基础参数</div>
          <div className="mt-4 grid gap-3">
            <StockCodeInput id="backtest-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
            <label htmlFor="backtest-strategy" className="grid gap-1">
              <span className={backtestLabelCls}>策略</span>
              <select
                id="backtest-strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className={`${backtestInputCls} w-full`}
              >
                {strategies.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label htmlFor="backtest-start-date" className="grid gap-1">
                <span className={backtestLabelCls}>开始日期</span>
                <input
                  id="backtest-start-date"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className={`${backtestInputCls} w-full`}
                />
              </label>
              <label htmlFor="backtest-end-date" className="grid gap-1">
                <span className={backtestLabelCls}>结束日期</span>
                <input
                  id="backtest-end-date"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className={`${backtestInputCls} w-full`}
                />
              </label>
            </div>
          </div>
          <div className={`${backtestNoteCardCls} mt-4`}>
            先完成基础参数，再去调整策略细节和成本假设；首轮判断更看方向性，不必一开始就把每个参数调到极细。
          </div>
        </div>

        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="eyebrow">策略参数</div>
          <div className="mt-4">
            {strategy === 'ma_cross' ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <label htmlFor="backtest-short-period" className="grid gap-1">
                  <span className={backtestLabelCls}>短周期</span>
                  <input
                    id="backtest-short-period"
                    type="number"
                    value={shortPeriod}
                    onChange={(e) => setShortPeriod(+e.target.value)}
                    min={2}
                    max={100}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
                <label htmlFor="backtest-long-period" className="grid gap-1">
                  <span className={backtestLabelCls}>长周期</span>
                  <input
                    id="backtest-long-period"
                    type="number"
                    value={longPeriod}
                    onChange={(e) => setLongPeriod(+e.target.value)}
                    min={5}
                    max={250}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
              </div>
            ) : null}
            {strategy === 'momentum' ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <label htmlFor="backtest-lookback" className="grid gap-1">
                  <span className={backtestLabelCls}>回看周期</span>
                  <input
                    id="backtest-lookback"
                    type="number"
                    value={lookback}
                    onChange={(e) => setLookback(+e.target.value)}
                    min={5}
                    max={120}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
                <label htmlFor="backtest-threshold" className="grid gap-1">
                  <span className={backtestLabelCls}>阈值</span>
                  <input
                    id="backtest-threshold"
                    type="number"
                    value={threshold}
                    onChange={(e) => setThreshold(+e.target.value)}
                    step={0.005}
                    min={0}
                    max={0.5}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
              </div>
            ) : null}
            {strategy === 'rsi' ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <label htmlFor="backtest-rsi-period" className="grid gap-1">
                  <span className={backtestLabelCls}>RSI 周期</span>
                  <input
                    id="backtest-rsi-period"
                    type="number"
                    value={rsiPeriod}
                    onChange={(e) => setRsiPeriod(+e.target.value)}
                    min={2}
                    max={50}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
                <label htmlFor="backtest-oversold" className="grid gap-1">
                  <span className={backtestLabelCls}>超卖线</span>
                  <input
                    id="backtest-oversold"
                    type="number"
                    value={oversold}
                    onChange={(e) => setOversold(+e.target.value)}
                    min={5}
                    max={50}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
                <label htmlFor="backtest-overbought" className="grid gap-1">
                  <span className={backtestLabelCls}>超买线</span>
                  <input
                    id="backtest-overbought"
                    type="number"
                    value={overbought}
                    onChange={(e) => setOverbought(+e.target.value)}
                    min={50}
                    max={95}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
              </div>
            ) : null}
            {strategy === 'buy_and_hold' ? (
              <div className={backtestNoteCardCls}>买入持有不需要额外策略参数，适合拿来做基准对照或快速 sanity check。</div>
            ) : null}
          </div>
          {strategy !== 'buy_and_hold' ? (
            <div className={`${backtestNoteCardCls} mt-4`}>
              不同策略的参数只负责表达交易节奏，不负责替代样本验证。先看结果方向，再决定是否继续细调参数。
            </div>
          ) : null}
        </div>

        <div className="panel-soft rounded-[26px] p-4 sm:p-5">
          <div className="eyebrow">成本假设</div>
          <div className="mt-4 flex flex-wrap gap-2">
            {costPresets.map((preset) => (
              <button key={preset.key} type="button" onClick={() => onApplyCostPreset(preset)} className={backtestChipButtonCls}>
                {preset.label}
              </button>
            ))}
            <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} className={backtestChipButtonCls}>
              {showAdvanced ? '收起高级选项' : '展开高级选项'}
            </button>
          </div>
          {showAdvanced ? (
            <div className="mt-4 grid gap-3">
              <label htmlFor="backtest-initial-capital" className="grid gap-1">
                <span className={backtestLabelCls}>初始资金</span>
                <input
                  id="backtest-initial-capital"
                  type="number"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(+e.target.value)}
                  min={10000}
                  step={10000}
                  className={`${backtestInputCls} w-full`}
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label htmlFor="backtest-commission" className="grid gap-1">
                  <span className={backtestLabelCls}>手续费率</span>
                  <input
                    id="backtest-commission"
                    type="number"
                    value={commission}
                    onChange={(e) => setCommission(+e.target.value)}
                    step={0.0001}
                    min={0}
                    max={0.01}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
                <label htmlFor="backtest-slippage" className="grid gap-1">
                  <span className={backtestLabelCls}>滑点</span>
                  <input
                    id="backtest-slippage"
                    type="number"
                    value={slippage}
                    onChange={(e) => setSlippage(+e.target.value)}
                    step={0.0001}
                    min={0}
                    max={0.01}
                    className={`${backtestInputCls} w-full`}
                  />
                </label>
              </div>
            </div>
          ) : (
            <div className={`${backtestNoteCardCls} mt-4`}>
              可以先点上方模板快速填入成本参数；只有在需要贴近真实成交时，再展开高级选项微调手续费和滑点。
            </div>
          )}
          {showAdvanced ? <div className={`${backtestNoteCardCls} mt-4`}>{configurationSummary}</div> : null}
        </div>

        <div className="xl:col-span-3">
          <button type="submit" disabled={loading} className={backtestPrimaryButtonCls}>
            {loading ? '运行中...' : '运行当前配置'}
          </button>
        </div>
      </form>
    </SectionCard>
  );
}
