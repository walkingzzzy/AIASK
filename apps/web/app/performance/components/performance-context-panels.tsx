import { SectionCard } from '@/components/ui';
import { performanceChipButtonCls } from '@/app/performance/components/performance-panel-styles';

type PerformanceContextPanelsProps = {
  isAccountMode: boolean;
  accountId: string;
  accounts: Array<{ account_id?: string }>;
  onAccountChange: (value: string) => void;
  portfolios: Array<{ id: string; name: string }>;
  portfolioId: string;
  onPortfolioChange: (value: string) => void;
  benchmark: string;
  benchmarkOptions: Array<{ code: string; label: string }>;
  onBenchmarkChange: (value: string) => void;
  windowPresets: readonly number[];
  days: number;
  onDaysChange: (value: number) => void;
  portfolioNarrative: string;
  activeModeLabel: string;
  portfolioLookbackDays: number;
  selectedBenchmarkLabel: string;
  topContributorCode: string;
  weakContributorCode: string;
  linkedStockCode: string;
  onOpenRisk: () => void;
  onOpenStock: (() => void) | null;
  onOpenResearch: (() => void) | null;
};

export default function PerformanceContextPanels({
  isAccountMode,
  accountId,
  accounts,
  onAccountChange,
  portfolios,
  portfolioId,
  onPortfolioChange,
  benchmark,
  benchmarkOptions,
  onBenchmarkChange,
  windowPresets,
  days,
  onDaysChange,
  portfolioNarrative,
  activeModeLabel,
  portfolioLookbackDays,
  selectedBenchmarkLabel,
  topContributorCode,
  weakContributorCode,
  linkedStockCode,
  onOpenRisk,
  onOpenStock,
  onOpenResearch,
}: PerformanceContextPanelsProps) {
  return (
    <>
      <SectionCard tabAttached className="p-4">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
          <div>
            <h3 className="m-0 font-medium">{isAccountMode ? '账户绩效上下文' : '组合归因上下文'}</h3>
            <p className="mb-0 mt-1 text-sm text-text-secondary">
              {isAccountMode
                ? '用于观察模拟账户净值、波动、回撤和核心持仓，适合从交易结果往回看。'
                : '用于观察组合收益是由个股选择、行业配置还是择时带来的，适合从研究和配置往后复盘。'}
            </p>
          </div>
          <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
            <div className="font-medium text-text-primary">联动建议</div>
            <ol className="mb-0 mt-2 space-y-1 pl-4">
              <li>先确认当前查看的是账户还是组合。</li>
              <li>再切换窗口长度，避免短周期和长周期混用。</li>
              <li>最后跳到风险中心，核对收益和风险是否匹配。</li>
            </ol>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {isAccountMode ? (
            <select
              value={accountId}
              onChange={(event) => onAccountChange(event.target.value)}
              className="w-auto min-w-[148px] text-sm"
            >
              <option value="">默认账户</option>
              {accounts.map((account, index) => (
                <option key={account.account_id ?? index} value={account.account_id ?? ''}>
                  {account.account_id ?? `账户 ${index + 1}`}
                </option>
              ))}
            </select>
          ) : (
            <>
              <select
                value={portfolioId}
                onChange={(event) => onPortfolioChange(event.target.value)}
                className="w-auto min-w-[168px] text-sm"
              >
                <option value="">选择组合</option>
                {portfolios.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>
                    {portfolio.name}
                  </option>
                ))}
              </select>
              <select
                value={benchmark}
                onChange={(event) => onBenchmarkChange(event.target.value)}
                className="w-auto min-w-[144px] text-sm"
              >
                {benchmarkOptions.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </>
          )}
          {windowPresets.map((windowDays) => (
            <button
              key={windowDays}
              type="button"
              onClick={() => onDaysChange(windowDays)}
              className={`action-chip cursor-pointer text-xs ${days === windowDays ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
            >
              {windowDays} 天
            </button>
          ))}
        </div>
      </SectionCard>

      <SectionCard className="mt-4 p-4">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
          <div>
            <h3 className="m-0 font-medium">{isAccountMode ? '账户复盘说明' : '归因解释与下一步动作'}</h3>
            <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">{portfolioNarrative}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={onOpenRisk} className={performanceChipButtonCls}>
                打开风险中心
              </button>
              {linkedStockCode && onOpenStock ? (
                <button type="button" onClick={onOpenStock} className={performanceChipButtonCls}>
                  打开重点股票详情
                </button>
              ) : null}
              {linkedStockCode && onOpenResearch ? (
                <button type="button" onClick={onOpenResearch} className={performanceChipButtonCls}>
                  打开重点股票研究
                </button>
              ) : null}
            </div>
          </div>
          <div className="panel-soft rounded-[24px] p-4">
            <div className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">当前联动上下文</div>
            <div className="mt-3 space-y-2 text-xs text-text-secondary">
              <div>
                当前模式：<span className="font-medium text-text-primary">{activeModeLabel}</span>
              </div>
              <div>
                观察窗口：
                <span className="font-medium text-text-primary">{isAccountMode ? days : portfolioLookbackDays} 天</span>
              </div>
              <div>
                基准口径：
                <span className="font-medium text-text-primary">
                  {isAccountMode ? '账户净值视角' : selectedBenchmarkLabel}
                </span>
              </div>
              {!isAccountMode && topContributorCode ? (
                <div>
                  最大贡献股：<span className="font-medium text-text-primary">{topContributorCode}</span>
                </div>
              ) : null}
              {!isAccountMode && weakContributorCode ? (
                <div>
                  主要拖累股：<span className="font-medium text-text-primary">{weakContributorCode}</span>
                </div>
              ) : null}
            </div>
            {!isAccountMode ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {benchmarkOptions.map((item) => (
                  <button
                    key={item.code}
                    type="button"
                    onClick={() => onBenchmarkChange(item.code)}
                    className={`action-chip cursor-pointer text-[11px] ${benchmark === item.code ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </SectionCard>
    </>
  );
}
