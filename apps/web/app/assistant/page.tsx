'use client';

import { useState } from 'react';
import { Badge, PageContainer, StockCodeInput, DataTable } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import DecisionCard from '@/components/decision-card';
import UnifiedDecisionPanel from '@/components/unified-decision-panel';
import UnifiedDecisionDiffLogList from '@/components/unified-decision-diff-log-list';
import CopilotDock from '@/components/copilot-dock';

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';
const LARGE_ACTION_CLS =
  'w-full rounded-[28px] border border-primary/22 bg-[linear-gradient(135deg,rgba(17,110,214,0.94),rgba(61,146,255,0.82))] px-5 py-5 text-left text-white shadow-[0_28px_46px_-30px_rgba(11,107,203,0.56)] transition hover:-translate-y-0.5 disabled:opacity-50';
const SOFT_ACTION_CLS =
  'w-full rounded-[24px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.76),rgba(246,250,255,0.42))] px-4 py-4 text-left text-text-primary shadow-[0_18px_34px_-26px_rgba(15,23,42,0.2)] transition hover:-translate-y-0.5 disabled:opacity-50';

const PRIMARY_ACTIONS = [
  {
    endpoint: '/assistant/unified-decision',
    label: '统一决策',
    actionLabel: '统一决策流水线',
    description: '把基本面、量化、事件和用户风险偏好一起融合成一张决策卡片。',
    className: LARGE_ACTION_CLS,
  },
  {
    endpoint: '/assistant/diagnosis',
    label: '全方位体检',
    actionLabel: '全方位综合体检',
    description: '优先给出综合结论、风险点和后续动作，适合第一次看一只股票。',
    className: `${SOFT_ACTION_CLS} border-primary/16`,
  },
  {
    endpoint: '/assistant/should-buy',
    label: '买入逻辑分析',
    actionLabel: '买入逻辑分析',
    description: '聚焦入场理由、触发条件和风险回报。',
    className: `${SOFT_ACTION_CLS} border-danger/18 text-danger`,
  },
  {
    endpoint: '/assistant/should-sell',
    label: '卖出风险提示',
    actionLabel: '卖出风险提示',
    description: '结合买入价和持有天数评估止盈止损。',
    className: `${SOFT_ACTION_CLS} border-success/18 text-success`,
  },
] as const;

const SECONDARY_ACTIONS = [
  {
    endpoint: '/assistant/industry-chain',
    label: '产业链穿透',
    actionLabel: '产业链价值穿透',
    description: '按关键词看上中下游联动关系。',
    className: `${SOFT_ACTION_CLS} border-sky-500/18 text-sky-700`,
  },
  {
    endpoint: '/assistant/daily-report',
    label: '盘后复盘简报',
    actionLabel: '盘后复盘简报',
    description: '按日期生成市场复盘和重点摘要。',
    className: `${SOFT_ACTION_CLS} border-amber-500/18 text-amber-700`,
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
  const [mobileChatOpen, setMobileChatOpen] = useState(false);

  const resultEnvelope = rawData != null ? (rawData as Record<string, unknown>) : null;
  const result = resultEnvelope != null ? (resultEnvelope.card ?? resultEnvelope) : null;
  const detailsEnvelope = rawDetails != null ? (rawDetails as Record<string, unknown>) : null;
  const unifiedDetails =
    detailsEnvelope != null ? (detailsEnvelope.details ?? detailsEnvelope.raw ?? detailsEnvelope) : null;
  const unifiedLegacyComparison = detailsEnvelope?.legacyComparison ?? resultEnvelope?.legacyComparison ?? null;
  const shouldShowUnifiedDetailsLoader =
    lastEndpoint === '/assistant/unified-decision' && Boolean(resultEnvelope?.detailsAvailable);
  const investmentStyleLabel =
    investmentStyle === 'aggressive' ? '激进' : investmentStyle === 'conservative' ? '保守' : '平衡';
  const currentCodeLabel = trimmedCode || '未输入';
  const resultStateLabel = isPending ? '生成中' : result ? '已生成' : '等待执行';
  const detailsStateLabel =
    shouldShowUnifiedDetailsLoader || isDetailsPending
      ? '详情可继续展开'
      : detailsError
        ? '详情拉取失败'
        : result
          ? '结果已落地'
          : '等待首个结果';
  const heroNotes = [
    '第一次看标的时优先跑"全方位体检"或"统一决策"，把判断先收敛成一张可读卡片。',
    '只有在验证具体交易动作时，再补充买入价、持有天数等参数，避免一开始就陷入细节。',
    '扩展任务更适合补充产业链线索或盘后总结，不建议替代主诊断流程。',
  ];

  function callAssistant(endpoint: string, label: string) {
    setFormError(null);
    reset();
    resetDetails();
    setActionLabel(label);
    setLastEndpoint(endpoint);
    const body: Record<string, unknown> = {};

    const requiresStockCode =
      endpoint === '/assistant/unified-decision' ||
      endpoint === '/assistant/should-buy' ||
      endpoint === '/assistant/should-sell' ||
      endpoint === '/assistant/diagnosis';

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
    <PageContainer className="app-theme-research">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(320px,28vw,420px)]" style={{ minHeight: 'calc(100dvh - 140px)' }}>
        {/* ---- 左侧：诊断工具台（可滚动） ---- */}
        <div className="min-h-0 xl:overflow-y-auto xl:pr-1">
          <section className="page-hero mb-4 p-5 sm:p-6">
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_clamp(240px,22vw,340px)]">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="info">Diagnostic Workspace</Badge>
                  <Badge variant="neutral">{investmentStyleLabel}风格</Badge>
                  <Badge variant={result ? 'success' : isPending ? 'warning' : 'neutral'}>{resultStateLabel}</Badge>
                </div>
                <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
                  AI 中心
                </h1>
                <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
                  诊断工具台与 AI 对话合二为一。左侧运行结构化分析，右侧自由对话、联动页面动作。
                </p>
                <div className="mt-5 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => callAssistant(PRIMARY_ACTIONS[0].endpoint, PRIMARY_ACTIONS[0].actionLabel)}
                    className={HERO_PRIMARY_BUTTON_CLS}
                  >
                    运行统一决策
                  </button>
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => callAssistant(PRIMARY_ACTIONS[1].endpoint, PRIMARY_ACTIONS[1].actionLabel)}
                    className={HERO_SECONDARY_BUTTON_CLS}
                  >
                    全方位体检
                  </button>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-4">
                  <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前代码</div>
                    <div className="mt-3 text-2xl font-semibold text-text-primary">{currentCodeLabel}</div>
                    <div className="mt-1 text-xs text-text-secondary">诊断默认聚焦标的</div>
                  </div>
                  <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">分析风格</div>
                    <div className="mt-3 text-2xl font-semibold text-text-primary">{investmentStyleLabel}</div>
                    <div className="mt-1 text-xs text-text-secondary">统一决策会读取该参数</div>
                  </div>
                  <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">最近任务</div>
                    <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">
                      {actionLabel || '尚未执行'}
                    </div>
                    <div className="mt-1 text-xs text-text-secondary">执行后结果会在下方集中展示</div>
                  </div>
                  <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">详情状态</div>
                    <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{detailsStateLabel}</div>
                    <div className="mt-1 text-xs text-text-secondary">统一决策支持继续展开更多细节</div>
                  </div>
                </div>
              </div>

              <div className="grid gap-3">
                <div className={PANEL_CLS}>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">推荐流程</div>
                  <div className="mt-4 space-y-3">
                    {heroNotes.map((note) => (
                      <div key={note} className={NOTE_CARD_CLS}>
                        {note}
                      </div>
                    ))}
                  </div>
                </div>
                <div className={PANEL_CLS}>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">风险提示</div>
                  <div className="mt-4 metric-tile rounded-[24px] p-4 text-sm leading-7 text-text-secondary">
                    本分析结果仅供参考，不构成投资建议。投资有风险，入市需谨慎。
                  </div>
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_clamp(240px,22vw,320px)]">
            <div className={PANEL_CLS}>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="eyebrow">Task Setup</div>
                    <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">选择分析标的与报告类型</h2>
                    <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
                      先判断当前是在做综合体检、交易验证，还是补充产业链与盘后总结。主任务和扩展任务都保留原有能力，但阅读顺序已经重新梳理。
                    </p>
                  </div>
                  <div className="w-full lg:w-[280px]">
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

                <div className="grid gap-4 border-t border-glass-border pt-4 lg:grid-cols-[minmax(0,0.82fr)_minmax(260px,0.78fr)]">
                  <div className="grid gap-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">扩展任务</div>
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

                  <div className="metric-tile rounded-[24px] p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                      统一决策参数
                    </div>
                    <div className="mt-4 grid gap-3">
                      <label className="grid gap-2 text-xs text-text-secondary">
                        <span className="font-medium uppercase tracking-[0.12em] text-text-muted">投资风格</span>
                        <select
                          value={investmentStyle}
                          onChange={(e) => setInvestmentStyle(e.target.value as 'aggressive' | 'balanced' | 'conservative')}
                          className={FIELD_CLS}
                        >
                          <option value="balanced">平衡</option>
                          <option value="conservative">保守</option>
                          <option value="aggressive">激进</option>
                        </select>
                      </label>
                      <div className="text-xs text-text-secondary">
                        仅"统一决策"会读取该风格参数，并结合你的登录画像动态调仓位。
                      </div>
                      <label className="flex items-center gap-2 text-xs text-text-secondary">
                        <input type="checkbox" checked={legacyMode} onChange={(e) => setLegacyMode(e.target.checked)} />
                        <span>同时拉取旧入口结果并生成差异对比</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-4">
              <div className={PANEL_CLS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">任务建议</div>
                <div className="mt-4 space-y-3">
                  <div className={NOTE_CARD_CLS}>&ldquo;统一决策&rdquo;适合快速收敛结论，&ldquo;全方位体检&rdquo;适合第一次接触一只股票。</div>
                  <div className={NOTE_CARD_CLS}>买入/卖出分析更像交易校验步骤，最好放在综合判断之后。</div>
                  <div className={NOTE_CARD_CLS}>
                    如果你只是补行业线索或盘后摘要，扩展任务可以独立运行，不必强制输入股票代码。
                  </div>
                </div>
              </div>
              <div className={PANEL_CLS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前状态</div>
                <div className="mt-4 grid gap-3">
                  <div className="metric-tile rounded-[24px] p-4">
                    <div className="metric-label">最近请求</div>
                    <div className="mt-3 text-sm font-semibold text-text-primary">{actionLabel || '尚未发起'}</div>
                    <div className="mt-2 text-xs text-text-secondary">
                      {lastEndpoint || '执行任一任务后，这里会记录最近的分析入口。'}
                    </div>
                  </div>
                  <div className="metric-tile rounded-[24px] p-4">
                    <div className="metric-label">返回状态</div>
                    <div className="mt-3 text-sm font-semibold text-text-primary">{resultStateLabel}</div>
                    <div className="mt-2 text-xs text-text-secondary">
                      {result ? '结果已进入下方结果区，可继续展开详情。' : '等待你从左侧选择一个任务入口。'}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => callAssistant(PRIMARY_ACTIONS[2].endpoint, PRIMARY_ACTIONS[2].actionLabel)}
                      className={CHIP_BUTTON_CLS}
                    >
                      快速买入分析
                    </button>
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => callAssistant(PRIMARY_ACTIONS[3].endpoint, PRIMARY_ACTIONS[3].actionLabel)}
                      className={CHIP_BUTTON_CLS}
                    >
                      快速卖出分析
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {isPending ? (
            <div className={`${PANEL_CLS} mt-4 flex items-center justify-center p-12`}>
              <LoadingState text={`报告生成引擎运转中：正在提取 ${actionLabel} 的多维度底层数据...`} />
            </div>
          ) : null}

          {formError || error ? <ErrorState text={formError || error!} hint="请检查标的代码和分析参数后重试" /> : null}
          {!formError && !error && detailsError ? (
            <ErrorState text={detailsError} hint="统一决策详情拉取失败，请稍后重试" />
          ) : null}

          {!isPending && !result && !error && !formError ? (
            <div className={`${PANEL_CLS} mt-4 flex flex-col items-center justify-center p-12 text-center`}>
              <EmptyState text="等待指令：先点击上方主按钮之一，这里会展示对应的结构化诊断结果。" />
            </div>
          ) : null}

          {result ? (
            <div className={`${PANEL_CLS} mt-4`}>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="eyebrow">Result Deck</div>
                  <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">{actionLabel || '诊断结果'}</h2>
                  <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                    结果区现在集中承接主结论、可展开详情和差异对比，避免入口在上方、结果却散落在多个区域里。
                  </p>
                </div>
                <Badge variant={lastEndpoint === '/assistant/unified-decision' ? 'info' : 'success'}>
                  {lastEndpoint === '/assistant/unified-decision' ? '统一决策结果' : '结构化结果'}
                </Badge>
              </div>

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
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm text-text-muted">查看详细数据</summary>
                    {(() => {
                      const rows = extractArray(result);
                      return rows.length ? (
                        <div className="mt-3">
                          <DataTable rows={rows} maxHeight={300} onExport={() => exportCSV(rows, 'assistant-result')} />
                        </div>
                      ) : (
                        <pre className="mt-3 max-h-[300px] overflow-auto rounded-[22px] bg-surface-alt/70 p-3 text-xs">
                          {JSON.stringify(result, null, 2)}
                        </pre>
                      );
                    })()}
                  </details>
                </>
              )}
            </div>
          ) : null}

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className={PANEL_CLS}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="eyebrow">Sell Inputs</div>
                  <h2 className="mb-0 mt-2 text-lg font-semibold text-text-primary">卖出分析参数</h2>
                </div>
                <Badge variant="warning">按需填写</Badge>
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <div className={NOTE_CARD_CLS}>仅在&ldquo;卖出风险提示&rdquo;时使用，避免无关参数打扰主流程。</div>
                <div className="flex flex-wrap gap-3">
                  <label className="grid flex-1 gap-2 text-xs text-text-secondary md:max-w-[220px]">
                    <span className="font-medium uppercase tracking-[0.12em] text-text-muted">买入价</span>
                    <input
                      id="assistant-buy-price"
                      value={sellBuyPrice}
                      onChange={(e) => {
                        setSellBuyPrice(e.target.value);
                        setFormError(null);
                      }}
                      placeholder="卖出分析必填"
                      className={FIELD_CLS}
                      inputMode="decimal"
                    />
                  </label>
                  <label className="grid flex-1 gap-2 text-xs text-text-secondary md:max-w-[200px]">
                    <span className="font-medium uppercase tracking-[0.12em] text-text-muted">持有天数</span>
                    <input
                      id="assistant-holding-days"
                      value={sellHoldingDays}
                      onChange={(e) => {
                        setSellHoldingDays(e.target.value);
                        setFormError(null);
                      }}
                      placeholder="可选"
                      className={FIELD_CLS}
                      inputMode="numeric"
                    />
                  </label>
                </div>
                <p className="mb-0 text-xs text-text-secondary">
                  &ldquo;卖出风险提示&rdquo;会连同买入价和持有天数一起提交，避免出现成功返回但内容为空的假通过。
                </p>
              </div>
            </div>

            <div className={PANEL_CLS}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="eyebrow">Extended Inputs</div>
                  <h2 className="mb-0 mt-2 text-lg font-semibold text-text-primary">扩展分析参数</h2>
                </div>
                <Badge variant="info">可独立运行</Badge>
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <div className={NOTE_CARD_CLS}>
                  &ldquo;产业链穿透&rdquo;和&ldquo;盘后复盘简报&rdquo;不再强制要求股票代码，可按关键词或日期独立生成。
                </div>
                <div className="flex flex-wrap gap-3">
                  <label className="grid flex-1 gap-2 text-xs text-text-secondary md:max-w-[280px]">
                    <span className="font-medium uppercase tracking-[0.12em] text-text-muted">产业链关键词</span>
                    <input
                      id="assistant-industry-keyword"
                      value={industryKeyword}
                      onChange={(e) => {
                        setIndustryKeyword(e.target.value);
                        setFormError(null);
                      }}
                      placeholder="产业链穿透可选"
                      className={FIELD_CLS}
                    />
                  </label>
                  <label className="grid flex-1 gap-2 text-xs text-text-secondary md:max-w-[220px]">
                    <span className="font-medium uppercase tracking-[0.12em] text-text-muted">复盘日期</span>
                    <input
                      id="assistant-daily-report-date"
                      type="date"
                      value={dailyReportDate}
                      onChange={(e) => {
                        setDailyReportDate(e.target.value);
                        setFormError(null);
                      }}
                      className={FIELD_CLS}
                    />
                  </label>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => callAssistant(SECONDARY_ACTIONS[0].endpoint, SECONDARY_ACTIONS[0].actionLabel)}
                    className={CHIP_BUTTON_CLS}
                  >
                    运行产业链穿透
                  </button>
                  <button
                    type="button"
                    disabled={isPending}
                    onClick={() => callAssistant(SECONDARY_ACTIONS[1].endpoint, SECONDARY_ACTIONS[1].actionLabel)}
                    className={CHIP_BUTTON_CLS}
                  >
                    运行盘后复盘
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ---- 右侧：内嵌 AI 对话（桌面端常驻） ---- */}
        <div className="hidden xl:flex min-h-0 sticky top-4 self-start" style={{ height: 'calc(100dvh - 140px)' }}>
          <CopilotDock variant="page" className="flex-1" />
        </div>
      </div>

      {/* ---- 移动端：浮动 AI 对话按钮 + 抽屉 ---- */}
      <button
        type="button"
        onClick={() => setMobileChatOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-white shadow-[0_8px_32px_-8px_rgba(11,107,203,0.5)] transition hover:scale-105 xl:hidden"
        aria-label="打开 AI 对话"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        </svg>
      </button>

      {mobileChatOpen ? (
        <div className="fixed inset-0 z-50 flex flex-col xl:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileChatOpen(false)} />
          <div className="relative z-10 mt-auto flex h-[85dvh] flex-col rounded-t-[28px] border border-border bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(244,249,255,0.64))] shadow-[0_-16px_48px_-16px_rgba(15,23,42,0.3)] backdrop-blur-2xl">
            <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
              <div className="text-sm font-semibold text-text-primary">AI 对话</div>
              <button
                type="button"
                onClick={() => setMobileChatOpen(false)}
                className="rounded-full border border-border px-3 py-1 text-xs"
              >
                关闭
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <CopilotDock variant="page" />
            </div>
          </div>
        </div>
      ) : null}
    </PageContainer>
  );
}
