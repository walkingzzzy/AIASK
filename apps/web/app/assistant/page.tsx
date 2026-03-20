'use client';

import { useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, DataTable } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import DecisionCard from '@/components/decision-card';
import UnifiedDecisionPanel from '@/components/unified-decision-panel';
import UnifiedDecisionDiffLogList from '@/components/unified-decision-diff-log-list';

const PRIMARY_ACTIONS = [
  {
    endpoint: '/assistant/unified-decision',
    label: '统一决策',
    actionLabel: '统一决策流水线',
    description: '把基本面、量化、事件和用户风险偏好一起融合成一张决策卡片。',
    className: 'w-full rounded-2xl border border-primary/30 bg-primary px-5 py-4 text-left text-white shadow-sm transition hover:bg-primary/90 disabled:opacity-50',
  },
  {
    endpoint: '/assistant/diagnosis',
    label: '全方位体检',
    actionLabel: '全方位综合体检',
    description: '优先给出综合结论、风险点和后续动作，适合第一次看一只股票。',
    className: 'w-full rounded-xl border border-primary/20 bg-primary/10 px-4 py-3 text-left text-primary transition hover:bg-primary/15 disabled:opacity-50',
  },
  {
    endpoint: '/assistant/should-buy',
    label: '买入逻辑分析',
    actionLabel: '买入逻辑分析',
    description: '聚焦入场理由、触发条件和风险回报。',
    className: 'w-full rounded-xl border border-danger/20 bg-danger/10 px-4 py-3 text-left text-danger transition hover:bg-danger/15 disabled:opacity-50',
  },
  {
    endpoint: '/assistant/should-sell',
    label: '卖出风险提示',
    actionLabel: '卖出风险提示',
    description: '结合买入价和持有天数评估止盈止损。',
    className: 'w-full rounded-xl border border-success/20 bg-success/10 px-4 py-3 text-left text-success transition hover:bg-success/15 disabled:opacity-50',
  },
] as const;

const SECONDARY_ACTIONS = [
  {
    endpoint: '/assistant/industry-chain',
    label: '产业链穿透',
    actionLabel: '产业链价值穿透',
    description: '按关键词看上中下游联动关系。',
    className: 'w-full rounded-xl border border-violet-500/20 bg-violet-500/10 px-4 py-3 text-left text-violet-700 transition hover:bg-violet-500/15 disabled:opacity-50 dark:text-violet-300',
  },
  {
    endpoint: '/assistant/daily-report',
    label: '盘后复盘简报',
    actionLabel: '盘后复盘简报',
    description: '按日期生成市场复盘和重点摘要。',
    className: 'w-full rounded-xl border border-orange-500/20 bg-orange-500/10 px-4 py-3 text-left text-orange-700 transition hover:bg-orange-500/15 disabled:opacity-50 dark:text-orange-300',
  },
] as const;

export default function AssistantPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode();
  const { trigger, data: rawData, isPending, error, reset } = useApiMutation<unknown>();
  const {
    trigger: triggerDetails,
    data: rawDetails,
    isPending: isDetailsPending,
    error: detailsError,
    reset: resetDetails,
  } = useApiMutation<unknown>({ errorToast: true });
  const [actionLabel, setActionLabel] = useState('');
  const [sellBuyPrice, setSellBuyPrice] = useState('');
  const [sellHoldingDays, setSellHoldingDays] = useState('');
  const [industryKeyword, setIndustryKeyword] = useState('');
  const [dailyReportDate, setDailyReportDate] = useState('');
  const [investmentStyle, setInvestmentStyle] = useState<'aggressive' | 'balanced' | 'conservative'>('balanced');
  const [legacyMode, setLegacyMode] = useState(false);
  const [lastEndpoint, setLastEndpoint] = useState('');
  const [lastRequestBody, setLastRequestBody] = useState<Record<string, unknown> | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const resultEnvelope = rawData != null ? rawData as Record<string, unknown> : null;
  const result = resultEnvelope != null
    ? resultEnvelope.card ?? resultEnvelope
    : null;
  const detailsEnvelope = rawDetails != null ? rawDetails as Record<string, unknown> : null;
  const unifiedDetails = detailsEnvelope != null
    ? (detailsEnvelope.details ?? detailsEnvelope.raw ?? detailsEnvelope)
    : null;
  const unifiedLegacyComparison = detailsEnvelope?.legacyComparison ?? resultEnvelope?.legacyComparison ?? null;
  const shouldShowUnifiedDetailsLoader =
    lastEndpoint === '/assistant/unified-decision' && Boolean(resultEnvelope?.detailsAvailable);

  function callAssistant(endpoint: string, label: string) {
    setFormError(null);
    reset();
    resetDetails();
    setActionLabel(label);
    setLastEndpoint(endpoint);
    const body: Record<string, unknown> = {};

    const requiresStockCode = endpoint === '/assistant/unified-decision'
      || endpoint === '/assistant/should-buy'
      || endpoint === '/assistant/should-sell'
      || endpoint === '/assistant/diagnosis';

    if (requiresStockCode) {
      if (!validate()) return;
      body.code = trimmedCode;
    }

    if (endpoint === '/assistant/unified-decision') {
      body.investmentStyle = investmentStyle;
      body.legacyMode = legacyMode;
    }

    if (endpoint === '/assistant/should-sell') {
      const buyPrice = Number(sellBuyPrice);
      if (!sellBuyPrice.trim() || !Number.isFinite(buyPrice) || buyPrice <= 0) {
        setFormError('卖出风险提示需要填写有效的买入价');
        return;
      }
      body.buyPrice = buyPrice;

      if (sellHoldingDays.trim()) {
        const holdingDays = Number(sellHoldingDays);
        if (!Number.isFinite(holdingDays) || holdingDays < 0) {
          setFormError('持有天数需要填写为非负数');
          return;
        }
        body.holdingDays = holdingDays;
      }
    }

    if (endpoint === '/assistant/industry-chain' && industryKeyword.trim()) {
      body.keyword = industryKeyword.trim();
    }

    if (endpoint === '/assistant/daily-report' && dailyReportDate.trim()) {
      body.date = dailyReportDate.trim();
    }

    setLastRequestBody(body);
    trigger(endpoint, { method: 'POST' }, body);
  }

  function loadUnifiedDetails() {
    if (!lastRequestBody) return;
    triggerDetails('/assistant/unified-decision/details', { method: 'POST' }, lastRequestBody);
  }

  return (
    <PageContainer>
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-primary flex items-center gap-2">
          🧠 AI 深度诊断报告生成器 (Diagnostic AI)
        </h1>
        <p className="text-muted-foreground mt-2">与随问随答的 Chat 不同，这里专注于针对特定标的的深度、主动性结构化诊断报告生成。</p>
      </div>

      <SectionCard className="mb-4 p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.1fr)_minmax(260px,0.9fr)] lg:items-start">
          <div>
            <h2 className="mt-0 text-base font-semibold">任务式使用建议</h2>
            <p className="mb-0 mt-1 text-sm text-text-secondary">先选一个核心问题：第一次看标的时优先做“全方位体检”，需要验证交易动作时再切换到买入/卖出分析。扩展任务适合补充产业链线索或盘后复盘。</p>
          </div>
          <div className="rounded-2xl border border-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
            <div className="font-medium text-text-primary">推荐流程</div>
            <ol className="mb-0 mt-2 space-y-1 pl-4">
              <li>先输入股票代码并执行主任务。</li>
              <li>如需卖出建议，再补充买入价与持有天数。</li>
              <li>最后用扩展任务补齐产业链或盘后复盘信息。</li>
            </ol>
          </div>
        </div>
      </SectionCard>

      <SectionCard className="p-5 mb-4">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <h2 className="mt-0 mb-1 text-sm font-semibold text-text-muted uppercase tracking-wider">选择分析标的与报告类型</h2>
              <p className="m-0 text-sm text-text-secondary">先判断当前要回答的是“先做综合体检”还是“验证一次买卖决策”，再按需补充下方参数。</p>
            </div>
            <div className="w-full md:w-72">
              <StockCodeInput
                id="assistant-stock-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
                placeholder="输入股票代码 (如 600519)"
              />
            </div>
          </div>

          <div className="grid gap-3">
            <button
              type="button"
              disabled={isPending}
              onClick={() => callAssistant(PRIMARY_ACTIONS[0].endpoint, PRIMARY_ACTIONS[0].actionLabel)}
              className={PRIMARY_ACTIONS[0].className}
            >
              <div className="text-base font-semibold">{PRIMARY_ACTIONS[0].label}</div>
              <div className="mt-1 text-sm text-white/90">{PRIMARY_ACTIONS[0].description}</div>
            </button>

            <div className="grid gap-3 md:grid-cols-3">
              {PRIMARY_ACTIONS.slice(1).map((action) => (
                <button
                  key={action.endpoint}
                  type="button"
                  disabled={isPending}
                  onClick={() => callAssistant(action.endpoint, action.actionLabel)}
                  className={action.className}
                >
                  <div className="text-sm font-semibold">{action.label}</div>
                  <div className="mt-1 text-xs opacity-80">{action.description}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-glass-border pt-4">
            <div className="mb-3 grid gap-2 md:max-w-[260px]">
              <label className="grid gap-1 text-xs text-text-secondary">
                <span className="font-medium text-text-muted uppercase tracking-wider">统一决策风格</span>
                <select
                  value={investmentStyle}
                  onChange={(e) => setInvestmentStyle(e.target.value as 'aggressive' | 'balanced' | 'conservative')}
                  className="rounded-md border border-glass-border bg-surface px-3 py-2 text-sm"
                >
                  <option value="balanced">平衡</option>
                  <option value="conservative">保守</option>
                  <option value="aggressive">激进</option>
                </select>
              </label>
              <div className="text-xs text-text-muted">仅“统一决策”会读取该风格参数，并结合你的登录画像动态调仓位。</div>
              <label className="mt-1 flex items-center gap-2 text-xs text-text-secondary">
                <input
                  type="checkbox"
                  checked={legacyMode}
                  onChange={(e) => setLegacyMode(e.target.checked)}
                />
                <span>同时拉取旧入口结果并生成差异对比</span>
              </label>
            </div>
            <div className="mb-2 text-xs font-medium text-text-muted uppercase tracking-wider">扩展任务</div>
            <div className="grid gap-3 md:grid-cols-2">
              {SECONDARY_ACTIONS.map((action) => (
                <button
                  key={action.endpoint}
                  type="button"
                  disabled={isPending}
                  onClick={() => callAssistant(action.endpoint, action.actionLabel)}
                  className={action.className}
                >
                  <div className="text-sm font-semibold">{action.label}</div>
                  <div className="mt-1 text-xs opacity-80">{action.description}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </SectionCard>

      <div className="mb-4 rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-xs text-text-secondary shadow-sm backdrop-blur">
        本分析结果仅供参考，不构成投资建议。投资有风险，入市需谨慎。
      </div>

      {isPending ? (
        <div className="p-12 border-2 border-dashed border-muted rounded-xl bg-surface-alt/30 flex justify-center items-center">
          <LoadingState text={`报告生成引擎运转中：正在提取 ${actionLabel} 的多维度底层数据...`} />
        </div>
      ) : null}

      {formError || error ? <ErrorState text={formError || error!} hint="请检查标的代码和分析参数后重试" /> : null}
      {!formError && !error && detailsError ? <ErrorState text={detailsError} hint="统一决策详情拉取失败，请稍后重试" /> : null}

      {!isPending && !result && !error && !formError ? (
        <div className="p-16 border-2 border-dashed border-muted rounded-xl bg-surface-alt/10 flex flex-col items-center text-center">
          <EmptyState text="等待指令：先点击上方主按钮之一，这里会展示对应的结构化诊断结果。" />
        </div>
      ) : null}

      {result ? (
        <>
          {lastEndpoint === '/assistant/unified-decision' ? (
            <>
              <UnifiedDecisionPanel
                card={result as Record<string, unknown>}
                details={unifiedDetails}
                detailsPending={isDetailsPending}
                canLoadDetails={shouldShowUnifiedDetailsLoader}
                onLoadDetails={loadUnifiedDetails}
                legacyComparison={unifiedLegacyComparison}
              />
              <UnifiedDecisionDiffLogList
                enabled={legacyMode}
                code={String(lastRequestBody?.code ?? trimmedCode ?? '')}
              />
            </>
          ) : (
            <>
              <DecisionCard data={result as Record<string, unknown>} />
              <details className="mt-3">
                <summary className="cursor-pointer text-text-muted">查看详细数据</summary>
                {(() => {
                  const rows = extractArray(result);
                  return rows.length
                    ? <DataTable rows={rows} maxHeight={300} onExport={() => exportCSV(rows, 'assistant-result')} />
                    : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(result, null, 2)}</pre>;
                })()}
              </details>
            </>
          )}
        </>
      ) : null}

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <SectionCard className="p-5">
          <h2 className="mt-0 mb-3 text-sm font-semibold text-text-muted uppercase tracking-wider">卖出分析参数</h2>
          <div className="flex flex-col gap-2 md:max-w-[420px]">
            <div className="text-xs font-medium text-text-muted uppercase tracking-wider">仅在“卖出风险提示”时使用</div>
            <div className="flex gap-2 flex-wrap">
              <label className="grid gap-1 text-xs text-text-secondary">
                <span>买入价</span>
                <input
                  id="assistant-buy-price"
                  value={sellBuyPrice}
                  onChange={(e) => { setSellBuyPrice(e.target.value); setFormError(null); }}
                  placeholder="卖出分析必填"
                  className="w-full md:w-[200px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
                  inputMode="decimal"
                />
              </label>
              <label className="grid gap-1 text-xs text-text-secondary">
                <span>持有天数</span>
                <input
                  id="assistant-holding-days"
                  value={sellHoldingDays}
                  onChange={(e) => { setSellHoldingDays(e.target.value); setFormError(null); }}
                  placeholder="可选"
                  className="w-full md:w-[180px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
                  inputMode="numeric"
                />
              </label>
            </div>
            <p className="text-xs text-text-muted">“卖出风险提示”会连同买入价和持有天数一起提交，避免出现成功返回但内容为空的假通过。</p>
          </div>
        </SectionCard>

        <SectionCard className="p-5">
          <h2 className="mt-0 mb-3 text-sm font-semibold text-text-muted uppercase tracking-wider">扩展分析参数</h2>
          <div className="grid gap-2 md:max-w-[520px]">
            <div className="text-xs font-medium text-text-muted uppercase tracking-wider">按关键词或日期独立生成</div>
            <div className="flex gap-2 flex-wrap">
              <label className="grid gap-1 text-xs text-text-secondary">
                <span>产业链关键词</span>
                <input
                  id="assistant-industry-keyword"
                  value={industryKeyword}
                  onChange={(e) => { setIndustryKeyword(e.target.value); setFormError(null); }}
                  placeholder="产业链穿透可选"
                  className="w-full md:w-[240px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
                />
              </label>
              <label className="grid gap-1 text-xs text-text-secondary">
                <span>复盘日期</span>
                <input
                  id="assistant-daily-report-date"
                  type="date"
                  value={dailyReportDate}
                  onChange={(e) => { setDailyReportDate(e.target.value); setFormError(null); }}
                  className="w-full md:w-[200px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
                />
              </label>
            </div>
            <p className="text-xs text-text-muted">“产业链穿透”和“盘后复盘简报”不再强制要求股票代码，可按关键词或日期独立生成。</p>
          </div>
        </SectionCard>
      </div>
    </PageContainer>
  );
}
