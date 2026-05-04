'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, SectionCard, KpiCard, Badge, TabBar } from '@/components/ui';
import { BarChart, PieChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { EmptyState, ErrorState, LoadingState, MetaLine, PageStatusCard } from '@/components/status-state';
import { ensureRecord } from '@/lib/query-parse';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

type ModuleKey = 'var' | 'stress' | 'exposure';
type RiskSummary = {
  portfolioId?: number | null;
  lookbackDays?: number;
  varResult?: unknown;
  stressResult?: unknown;
  exposureResult?: unknown;
  moduleStatus?: Partial<Record<ModuleKey, { ok?: boolean; reason?: string | null }>>;
  degraded?: boolean;
  degradeReasons?: string[];
  meta?: { fetchedAt?: string; cache?: { hit?: boolean; backend?: string; ttlSeconds?: number } };
};
const RESULT_TABS = [
  { key: 'overview', label: '总览' },
  { key: 'var', label: 'VaR' },
  { key: 'stress', label: '压力' },
  { key: 'exposure', label: '暴露' },
] as const;
type RiskResultTab = (typeof RESULT_TABS)[number]['key'];

const LOOKBACK_PRESETS = [90, 252, 504] as const;
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const WORKBENCH_INPUT_CLS =
  'h-11 w-full rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

function buildRiskQueryString(portfolioId: string, lookbackDays: string) {
  const qs = new URLSearchParams();
  if (portfolioId) qs.set('portfolioId', portfolioId);
  qs.set('lookbackDays', lookbackDays || '252');
  return qs.toString();
}

function brief(v: unknown): string {
  if (v == null) return '无数据';
  if (Array.isArray(v)) return `数组(${v.length})`;
  if (typeof v !== 'object') return String(v);
  const o = v as Record<string, unknown>;
  const pairs = Object.entries(o)
    .filter(([, x]) => ['string', 'number', 'boolean'].includes(typeof x))
    .slice(0, 3);
  if (!pairs.length) return `对象(${Object.keys(o).length}键)`;
  return pairs.map(([k, x]) => `${k}:${String(x)}`).join(' | ');
}

function hasUsefulRiskData(value: unknown): boolean {
  if (value == null) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value !== 'object') return true;
  const entries = Object.values(value as Record<string, unknown>);
  if (entries.length === 0) return false;
  return entries.some((item) => {
    if (item == null) return false;
    if (Array.isArray(item)) return item.length > 0;
    if (typeof item === 'object') return hasUsefulRiskData(item);
    return String(item).trim().length > 0;
  });
}

export default function RiskPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const searchParams = useStableSearchParams();
  const router = useRouter();
  const pathname = useStablePathname();
  const [portfolioId, setPortfolioId] = useState(() => searchParams.get('portfolioId') ?? '');
  const [lookbackDays, setLookbackDays] = useState(() => searchParams.get('lookbackDays') ?? '252');
  const [formError, setFormError] = useState<string | null>(null);
  const [, setLastPrimaryRefreshAt] = useState<string | null>(null);
  const [resultTab, setResultTab] = useState<RiskResultTab>('overview');
  const applyingWorkspaceDefaultsRef = useRef(false);
  const task = searchParams.get('task');
  const from = searchParams.get('from');
  const submittedQs = useMemo(
    () => buildRiskQueryString(searchParams.get('portfolioId') ?? '', searchParams.get('lookbackDays') ?? '252'),
    [searchParams],
  );

  useEffect(() => {
    const queryPortfolioId = searchParams.get('portfolioId');
    const queryLookbackDays = searchParams.get('lookbackDays');
    if (queryPortfolioId != null && queryPortfolioId !== portfolioId) {
      setPortfolioId(queryPortfolioId);
    }
    if (queryLookbackDays != null && queryLookbackDays !== lookbackDays) {
      setLookbackDays(queryLookbackDays);
    }
  }, [lookbackDays, portfolioId, searchParams]);

  const summaryQ = useApiQuery<RiskSummary>(submittedQs ? `/risk/summary?${submittedQs}` : null, {
    critical: true,
    parse: (raw) => {
      const obj = ensureRecord(raw, '风险汇总');
      if ('moduleStatus' in obj && obj.moduleStatus != null && typeof obj.moduleStatus !== 'object') {
        throw new Error('风险汇总.moduleStatus 字段类型异常');
      }
      return obj as RiskSummary;
    },
  });
  const varQ = useApiQuery<unknown>(submittedQs ? `/risk/var?${submittedQs}` : null, {
    critical: true,
    parse: (raw) => ensureRecord(raw, '风险VaR'),
  });

  const loading = summaryQ.isFetching || varQ.isFetching;
  const error = formError || summaryQ.error || varQ.error;
  const summary = summaryQ.data;
  const varResult = useMemo(() => {
    if (!varQ.data || typeof varQ.data !== 'object') return null;
    const raw = varQ.data as Record<string, unknown>;
    return raw.result && typeof raw.result === 'object' ? (raw.result as Record<string, unknown>) : raw;
  }, [varQ.data]);

  function onLoad(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (portfolioId && !/^\d+$/.test(portfolioId)) return setFormError('portfolioId 必须为数字');
    if (!/^\d+$/.test(lookbackDays)) return setFormError('lookbackDays 必须为数字');
    const newQs = buildRiskQueryString(portfolioId, lookbackDays);
    if (newQs === submittedQs) {
      summaryQ.refetch();
      varQ.refetch();
    } else router.replace(`${pathname}?${newQs}`, { scroll: false });
  }

  const topCards = useMemo(() => {
    const cache = summary?.meta?.cache;
    return {
      portfolioId: String(summary?.portfolioId ?? '-'),
      lookbackDays: String(summary?.lookbackDays ?? '-'),
      degraded: summary?.degraded ? '是' : '否',
      cache: cache ? `${cache.hit ? '命中' : '未命中'}(${cache.backend ?? '-'}) TTL=${cache.ttlSeconds ?? '-'}s` : '-',
    };
  }, [summary]);

  const moduleCards = useMemo(() => {
    const cfg: Array<{ key: ModuleKey; title: string; data: unknown }> = [
      { key: 'var', title: 'VaR', data: varResult ?? summary?.varResult },
      { key: 'stress', title: '压力测试', data: summary?.stressResult },
      { key: 'exposure', title: '风险暴露', data: summary?.exposureResult },
    ];
    return cfg.map((x) => {
      const st = summary?.moduleStatus?.[x.key];
      const hasData = hasUsefulRiskData(x.data);
      const ok = st?.ok === true && hasData || (st?.ok == null && hasData);
      return {
        ...x,
        status: ok ? '成功' : summary?.degraded ? '降级' : '空数据',
        reason: st?.reason ?? (hasData ? null : `${x.title} 未返回可展示数据`),
        brief: brief(x.data),
      };
    });
  }, [summary, varResult]);

  const varBarItems = useMemo(() => {
    if (!varResult) return [];
    const candidates = [
      {
        label: 'VaR 金额',
        value: Number(
          (varResult.var as Record<string, unknown> | undefined)?.amount ??
            (varResult as Record<string, unknown>).var_amount ??
            NaN,
        ),
      },
      {
        label: 'CVaR 金额',
        value: Number(
          (varResult.cvar as Record<string, unknown> | undefined)?.amount ??
            (varResult as Record<string, unknown>).cvar_amount ??
            NaN,
        ),
      },
      {
        label: 'VaR 百分比',
        value: Number(
          (varResult.var as Record<string, unknown> | undefined)?.percentage ??
            (varResult as Record<string, unknown>).var_percent ??
            (varResult as Record<string, unknown>).var95 ??
            NaN,
        ),
      },
      {
        label: 'CVaR 百分比',
        value: Number(
          (varResult.cvar as Record<string, unknown> | undefined)?.percentage ??
            (varResult as Record<string, unknown>).cvar_percent ??
            NaN,
        ),
      },
      { label: '波动率', value: Number((varResult as Record<string, unknown>).volatility ?? NaN) },
      { label: '最大回撤', value: Number((varResult as Record<string, unknown>).max_drawdown ?? NaN) },
    ];
    return candidates.filter((item) => Number.isFinite(item.value));
  }, [varResult]);

  const stressItems = useMemo(() => {
    const raw = summary?.stressResult;
    if (!raw || typeof raw !== 'object') return [];
    const obj = raw as Record<string, unknown>;
    const scenarios = (obj.scenarios ?? obj.results ?? obj.items) as Record<string, unknown>[] | undefined;
    if (Array.isArray(scenarios)) {
      return scenarios.map((s) => ({
        label: String(s.name ?? s.scenario ?? ''),
        value: Number(s.impact ?? s.loss ?? s.change ?? 0),
      }));
    }
    return Object.entries(obj)
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 8)
      .map(([k, v]) => ({ label: k, value: Number(v) }));
  }, [summary]);

  const exposureItems = useMemo(() => {
    const raw = summary?.exposureResult;
    if (!raw || typeof raw !== 'object') return [];
    const obj = raw as Record<string, unknown>;
    const sectors = (obj.sectors ?? obj.sector_exposure ?? obj.items) as Record<string, unknown>[] | undefined;
    if (Array.isArray(sectors)) {
      return sectors.map((s) => ({
        name: String(s.name ?? s.sector ?? ''),
        value: Number(s.weight ?? s.exposure ?? s.ratio ?? 0),
      }));
    }
    return Object.entries(obj)
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 10)
      .map(([k, v]) => ({ name: k, value: Math.abs(Number(v)) }));
  }, [summary]);

  const allEmpty = !!summary && moduleCards.every((c) => c.status !== '成功');
  const partialDegraded =
    !!summary && moduleCards.some((c) => c.status === '成功') && moduleCards.some((c) => c.status !== '成功');
  const showInitialEmptyState = !summary && !loading && !error;
  const availableModuleCount = moduleCards.filter((item) => item.status === '成功').length;
  const displayPortfolio = portfolioId || (topCards.portfolioId !== '-' ? topCards.portfolioId : '未选择');
  const latestRiskRefreshAt =
    [summaryQ.dataUpdatedAt, varQ.dataUpdatedAt]
      .filter((value): value is number => typeof value === 'number' && value > 0)
      .sort((left, right) => right - left)[0] ?? null;
  const latestRiskRefreshText = latestRiskRefreshAt
    ? new Date(latestRiskRefreshAt).toLocaleString('zh-CN')
    : '尚未获取';

  const handlePrimaryRiskAction = useCallback(async () => {
    if (submittedQs) {
      await Promise.allSettled([summaryQ.refetch(), varQ.refetch()]);
    } else {
      setLookbackDays('252');
    }
    setLastPrimaryRefreshAt(new Date().toLocaleString('zh-CN'));
  }, [submittedQs, summaryQ, varQ]);

  const pageActions = useMemo(
    () => [
      {
        id: 'risk.refresh',
        label: '刷新风险分析',
        description: '刷新风险汇总和 VaR 数据',
        keywords: ['刷新', '风险'],
        scope: 'page' as const,
        pageKey: 'risk',
        run: async () => {
          await Promise.allSettled([summaryQ.refetch(), varQ.refetch()]);
          return { message: '已刷新风险分析数据' };
        },
      },
      {
        id: 'risk.set-lookback',
        label: '切到 252 天窗口',
        description: '将风险观察窗口切到 252 天',
        keywords: ['252天', '窗口'],
        scope: 'page' as const,
        pageKey: 'risk',
        run: () => {
          setLookbackDays('252');
          return { message: '已切到 252 天窗口' };
        },
      },
    ],
    [summaryQ, varQ],
  );

  usePageActions(pageActions);

  const riskSummaryText = `组合 ${portfolioId || String(summary?.portfolioId ?? '未选择')}，回看 ${lookbackDays} 天，降级状态 ${summary?.degraded ? '是' : '否'}。`;
  const riskEvidence = useMemo(
    () => [
      { label: '组合', value: displayPortfolio },
      { label: '窗口', value: `${lookbackDays} 天` },
      { label: '模块覆盖', value: `${availableModuleCount}/${moduleCards.length}` },
      { label: '降级状态', value: summary?.degraded ? '已降级' : '正常' },
      { label: '最近抓取', value: latestRiskRefreshText },
    ],
    [availableModuleCount, displayPortfolio, latestRiskRefreshText, lookbackDays, moduleCards.length, summary?.degraded],
  );
  const riskLinks = useMemo(
    () => [
      { id: 'risk-open-portfolio', label: '去组合页', href: '/portfolio' },
      { id: 'risk-open-performance', label: '去绩效中心', href: '/performance' },
      { id: 'risk-open-execution', label: '去执行中心', href: '/execution' },
      { id: 'risk-open-data', label: '去数据中心', href: '/data?from=risk' },
    ],
    [],
  );
  const riskNotes = useMemo(() => {
    const notes = [...(summary?.degradeReasons ?? [])];
    if (allEmpty) notes.push('当前风险结果为空，建议先确认组合和窗口是否有效。');
    if (partialDegraded) notes.push('部分模块结果不可用，建议先查看降级原因再解释图表。');
    return notes;
  }, [allEmpty, partialDegraded, summary?.degradeReasons]);
  const riskResult = buildLocalResultContract({
    summary: riskSummaryText,
    status: error ? 'unavailable' : showInitialEmptyState || allEmpty ? 'empty' : summary?.degraded ? 'degraded' : 'ready',
    pageActions,
    preferredActionIds: ['risk.refresh', 'risk.set-lookback'],
    recommendedLinks: riskLinks,
    recommendedNextActions: [
      '先确认组合和回看窗口，再解释 VaR、压力和暴露结果。',
      summary?.degraded ? '当前存在降级模块，先看原因再解释图表。' : '只有在总览异常时再钻到单模块图表。',
      '需要执行动作时再跳绩效、组合或执行中心。',
    ],
    evidence: riskEvidence,
    riskNotes,
    emptyState: {
      title: '还没有形成风险分析结果',
      description: '先选择组合和窗口，再触发一次风险汇总。',
      example: 'portfolioId=1，lookbackDays=252',
    },
    degradedState: summary?.degraded ? {
      title: '风险页当前处于降级态',
      description: '请先处理模块降级原因，再继续解释风险结论。',
      reason: summary.degradeReasons?.join('；') || '部分模块结果暂不可用',
    } : null,
    freshness: summary?.meta?.fetchedAt ? { updatedAt: summary.meta.fetchedAt, label: '风险抓取时间' } : null,
    platformMeta: {
      sourceTool: 'risk-summary',
      degraded: summary?.degraded ?? false,
      fallbackReason: summary?.degradeReasons ?? [],
    },
    workbenchTask: defaultWorkbenchTask('risk', `风险复盘：${displayPortfolio}`, `/risk?lookbackDays=${encodeURIComponent(lookbackDays)}`, 'risk-review', {
      portfolioId: portfolioId || summary?.portfolioId || null,
      lookbackDays: Number(lookbackDays),
    }),
  });

  usePageContext({
    pageKey: 'risk',
    title: '风险分析',
    summary: riskSummaryText,
    primaryGoal: '锁定组合和观察窗口后，快速判断当前最需要处理的风险点。',
    requiredInputs: ['portfolioId', 'lookbackDays'],
    objectType: portfolioId || summary?.portfolioId ? 'portfolio' : 'workspace',
    objectId: portfolioId || String(summary?.portfolioId ?? 'risk'),
    resultType: 'risk-summary',
    tags: [`${lookbackDays} 天`, summary?.degraded ? '已降级' : '正常', allEmpty ? '空结果' : '有结果'],
    suggestions: [
      '总结当前 VaR、压力测试和暴露结果的核心风险',
      '指出当前风险页最需要补的上下文或数据',
      '把风险分析整理成执行层面的行动建议',
    ],
    recommendedNextActions: riskResult.recommendedNextActions,
    recommendedActions: riskResult.recommendedActions,
    recommendedLinks: riskResult.recommendedLinks,
    evidenceSummary: evidenceToSummary(riskResult.evidence),
    riskNotes: riskResult.riskNotes ?? [],
    freshness: riskResult.freshness ?? null,
    dataFreshness: riskResult.freshness?.updatedAt ?? null,
    degradedReason: summary?.degradeReasons ?? [],
    raw: {
      portfolioId: portfolioId || summary?.portfolioId || null,
      lookbackDays,
      degraded: summary?.degraded ?? false,
      allEmpty,
      partialDegraded,
    },
  });

  useEffect(() => {
    if (!workbenchHydrated) return;
    let appliedWorkspaceDefaults = false;
    const deferredUpdates: Array<() => void> = [];
    const nextPortfolioId = !portfolioId && workbenchContext.portfolioId
      ? workbenchContext.portfolioId
      : portfolioId;
    const nextLookbackDays =
      typeof workbenchContext.lookbackDays === 'number' &&
      !searchParams.get('lookbackDays') &&
      lookbackDays !== String(workbenchContext.lookbackDays)
        ? String(workbenchContext.lookbackDays)
        : lookbackDays;
    if (!portfolioId && workbenchContext.portfolioId) {
      appliedWorkspaceDefaults = true;
      deferredUpdates.push(() => setPortfolioId(workbenchContext.portfolioId!));
    }
    if (
      typeof workbenchContext.lookbackDays === 'number' &&
      !searchParams.get('lookbackDays') &&
      lookbackDays !== String(workbenchContext.lookbackDays)
    ) {
      appliedWorkspaceDefaults = true;
      deferredUpdates.push(() => setLookbackDays(String(workbenchContext.lookbackDays)));
    }
    applyingWorkspaceDefaultsRef.current = appliedWorkspaceDefaults;
    if (!deferredUpdates.length) return;
    const timer = window.setTimeout(() => {
      deferredUpdates.forEach((apply) => apply());
      const hasExplicitPortfolio = Boolean(searchParams.get('portfolioId'));
      const hasExplicitLookback = Boolean(searchParams.get('lookbackDays'));
      if (!hasExplicitPortfolio || !hasExplicitLookback) {
        router.replace(`${pathname}?${buildRiskQueryString(nextPortfolioId, nextLookbackDays)}`, { scroll: false });
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    lookbackDays,
    pathname,
    portfolioId,
    router,
    searchParams,
    workbenchContext.lookbackDays,
    workbenchContext.portfolioId,
    workbenchHydrated,
  ]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    if (applyingWorkspaceDefaultsRef.current) {
      applyingWorkspaceDefaultsRef.current = false;
      return;
    }
    updateWorkbenchContext({
      portfolioId: portfolioId || null,
      lookbackDays: Number.isFinite(Number(lookbackDays)) ? Number(lookbackDays) : null,
    });
  }, [lookbackDays, portfolioId, updateWorkbenchContext, workbenchHydrated]);

  const currentView = useMemo<Record<string, unknown>>(
    () => ({ portfolioId, lookbackDays }),
    [lookbackDays, portfolioId],
  );

  const applyView = useCallback((snapshot: Record<string, unknown>) => {
    if (typeof snapshot.portfolioId === 'string') {
      setPortfolioId(snapshot.portfolioId);
    }
    if (typeof snapshot.lookbackDays === 'string' || typeof snapshot.lookbackDays === 'number') {
      setLookbackDays(String(snapshot.lookbackDays));
    }
  }, []);

  const primaryContent = (
    <>
      {from || task ? (
        <div className="panel-soft mb-4 rounded-[24px] px-4 py-3 text-sm text-text-secondary">
          上下文跳转
          {from ? ` · 来源: ${from}` : ''}
          {from === 'home' ? ' · 来自首页快捷入口' : ''}
          {task ? ` · 任务：${task}` : ''}
        </div>
      ) : null}
      <section className="page-hero mb-4 p-4 sm:p-5">
        <div className={`grid gap-5 ${compactLayout ? '' : 'xl:grid-cols-[minmax(0,1fr)_320px]'}`}>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">风险工作台</Badge>
              <Badge variant={displayPortfolio !== '未选择' ? 'success' : 'warning'}>
                {displayPortfolio !== '未选择' ? `组合 ${displayPortfolio}` : '等待选择组合'}
              </Badge>
              <Badge variant={summary?.degraded ? 'warning' : 'neutral'}>
                {summary?.degraded ? '部分模块降级' : '工作台稳定'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-3 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2rem]">
              风险分析工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-6 text-text-secondary sm:text-[15px]">
              先确认组合和观察窗口，再进入参数与结果区；排障信息和原始响应可按需展开查看。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  void handlePrimaryRiskAction();
                }}
                data-testid="page-primary-action"
                data-action-testid="risk-refresh-action"
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                {submittedQs ? '刷新当前风险' : '准备 252 天窗口'}
              </button>
              <Link href="/portfolio" className={`${HERO_SECONDARY_BUTTON_CLS} no-underline text-inherit`}>
                去组合页
              </Link>
            </div>
            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前组合 {displayPortfolio} ｜ 观察窗口 {lookbackDays} 天 ｜ 当前视图 {RESULT_TABS.find((item) => item.key === resultTab)?.label}
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                模块覆盖 {availableModuleCount}/{moduleCards.length} ｜ 降级 {summary?.degraded ? '是' : '否'} ｜ 缓存 {summary?.meta?.cache?.hit ? '命中' : '待刷新'}
              </p>
            </div>
            {compactLayout ? (
              <details className="mt-3 rounded-[22px] border border-white/45 bg-white/24 px-4 py-3">
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开建议顺序与下一步</summary>
                <div className="mt-3 space-y-3">
                  <div className={NOTE_CARD_CLS}>1. 先确认组合与窗口，再看 VaR 是否已经形成可比基线。</div>
                  <div className={NOTE_CARD_CLS}>2. 如果压力测试与暴露结论冲突，优先检查模块状态与降级原因。</div>
                  <div className={NOTE_CARD_CLS}>3. 只有在结果异常或缺失时，再去排障面板看原始响应。</div>
                </div>
              </details>
            ) : null}
          </div>

          {!compactLayout ? (
            <details className={SIDE_PANEL_CLS} open>
              <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                建议顺序与下一步
              </summary>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>1. 先确认组合与窗口，再看 VaR 是否已经形成可比基线。</div>
                <div className={NOTE_CARD_CLS}>2. 如果压力测试与暴露结论冲突，优先检查模块状态与降级原因。</div>
                <div className={NOTE_CARD_CLS}>3. 只有在结果异常或缺失时，再去排障面板看原始响应。</div>
                <div className="mt-4">
                  <AskAiButton
                    summary={`组合 ${displayPortfolio}，回看 ${lookbackDays} 天，模块完成 ${availableModuleCount}/${moduleCards.length}`}
                    prompt="请总结当前风险分析结果，并指出最需要处理的风险点"
                  />
                </div>
              </div>
            </details>
          ) : null}
        </div>
      </section>

      {!compactLayout ? (
        <ProgressiveWorkbenchSection pageKey="risk" title="风险结果工作台" result={riskResult} summaryMode="strip" />
      ) : null}

      {!loading && !error && (showInitialEmptyState || allEmpty || partialDegraded) ? (
        <PageStatusCard
          status={partialDegraded ? 'degraded' : 'empty'}
          title={partialDegraded ? '当前风险结果不完整' : '先选择组合再启动风险分析'}
          reason={
            partialDegraded
              ? (summary?.degradeReasons?.join('；') || '部分模块结果暂不可用')
              : '当前还没有可解释的风险结果，请先锁定组合与观察窗口。'
          }
          freshness={latestRiskRefreshText}
          primaryAction={(
            <button type="button" onClick={() => { void handlePrimaryRiskAction(); }} className={HERO_PRIMARY_BUTTON_CLS}>
              {submittedQs ? '刷新风险结果' : '准备 252 天窗口'}
            </button>
          )}
          secondaryAction={<Link href="/portfolio" className={`${HERO_SECONDARY_BUTTON_CLS} no-underline text-inherit`}>去组合页</Link>}
          example="portfolioId=1，lookbackDays=252"
          className="mb-4"
        />
      ) : null}

      {loading ? <LoadingState text="加载风险分析中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">参数配置</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">参数工作台</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              先选择组合与回看窗口；常用模板和辅助动作可在“更多选项”里处理。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            最近抓取：{summary?.meta?.fetchedAt ? new Date(summary.meta.fetchedAt).toLocaleString('zh-CN') : '尚未获取'}
          </div>
        </div>

        <form onSubmit={onLoad} className="mt-4 space-y-4">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,240px)_minmax(0,180px)_auto] xl:items-end">
            <label htmlFor="risk-portfolio-id" className="grid gap-2">
              <span className="text-xs font-medium uppercase tracking-[0.12em] text-text-muted">组合 ID</span>
              <input
                id="risk-portfolio-id"
                value={portfolioId}
                onChange={(e) => setPortfolioId(e.target.value)}
                placeholder="可选，不填则尝试自动选择"
                className={WORKBENCH_INPUT_CLS}
              />
            </label>
            <label htmlFor="risk-lookback-days" className="grid gap-2">
              <span className="text-xs font-medium uppercase tracking-[0.12em] text-text-muted">回看天数</span>
              <input
                id="risk-lookback-days"
                value={lookbackDays}
                onChange={(e) => setLookbackDays(e.target.value)}
                placeholder="252"
                className={WORKBENCH_INPUT_CLS}
              />
            </label>
            <div className="flex flex-wrap items-center gap-2 xl:justify-end">
              <button type="submit" className={HERO_PRIMARY_BUTTON_CLS}>
                查询风险
              </button>
              {submittedQs ? (
                <button
                  type="button"
                  onClick={() => {
                    void Promise.allSettled([summaryQ.refetch(), varQ.refetch()]);
                  }}
                  className={HERO_SECONDARY_BUTTON_CLS}
                >
                  刷新数据
                </button>
              ) : null}
            </div>
          </div>

          <details className="rounded-[22px] border border-glass-border bg-white/35 px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-text-primary">更多选项</summary>
            <div className="mt-3 flex flex-wrap gap-2">
              {LOOKBACK_PRESETS.map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setLookbackDays(String(days))}
                  className={`${CHIP_BUTTON_CLS} ${lookbackDays === String(days) ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                >
                  {days} 天模板
                </button>
              ))}
            </div>
          </details>
        </form>
      </div>

      {showInitialEmptyState && !compactLayout ? (
        <div className="panel-soft mt-4 rounded-[28px] p-5">
          <h3 className="mt-0">还没有可分析的风险上下文</h3>
          <p className="mb-3 text-sm text-text-secondary">
            如果还没有组合或模拟持仓，这里不会直接给出有意义的 VaR、压力测试和暴露结果。
          </p>
          <div className="flex gap-2 flex-wrap">
            <Link href="/portfolio" className={`${HERO_PRIMARY_BUTTON_CLS} no-underline text-inherit`}>
              去创建组合
            </Link>
            <Link href="/paper-trading" className={`${HERO_SECONDARY_BUTTON_CLS} no-underline text-inherit`}>
              去模拟交易
            </Link>
          </div>
        </div>
      ) : null}

      <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">结果视图</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">风险结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              先查看当前结果视图；如结果缺失或降级，再展开原始响应与排障说明。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            可用模块：<span className="font-medium text-text-primary">{availableModuleCount}</span> / {moduleCards.length}
          </div>
        </div>
        <div className="mt-4">
          <TabBar tabs={RESULT_TABS} active={resultTab} onChange={(key) => setResultTab(key as RiskResultTab)} />
        </div>
        <SectionCard tabAttached>
          {resultTab === 'overview' ? (
            <>
              {allEmpty ? (
                <div className="rounded-[24px] border border-amber-200/70 bg-[linear-gradient(180deg,rgba(255,248,236,0.82),rgba(255,244,225,0.65))] p-4">
                  <h3 className="mt-0 text-base">暂无可用风险结果</h3>
                  <p className="m-0 text-sm text-text-secondary">
                    当前组合或账户还没有足够数据来生成 VaR、压力测试和暴露分析。先补充持仓，再重新运行风险分析会更有意义。
                  </p>
                </div>
              ) : null}
              {partialDegraded ? (
                <div className="mb-4 rounded-[24px] border border-warning/20 bg-warning/5 px-4 py-3 text-sm text-text-secondary">
                  检测到部分降级，建议先核对成功模块，再结合降级原因判断是否需要回到上游数据源排查。
                </div>
              ) : null}
              {summary?.degraded && summary.degradeReasons?.length ? (
                <MetaLine>降级原因：{summary.degradeReasons.join(' | ')}</MetaLine>
              ) : null}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard title="组合ID" value={topCards.portfolioId} />
                <KpiCard title="回看天数" value={topCards.lookbackDays} />
                <KpiCard title="降级状态" value={topCards.degraded} />
                <KpiCard title="缓存" value={topCards.cache} />
              </div>
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {moduleCards.map((m) => (
                  <div key={m.key} className="metric-tile rounded-[24px] p-4">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="font-medium text-text-primary">{m.title}</span>
                      <Badge variant={m.status === '成功' ? 'success' : m.status === '降级' ? 'warning' : 'neutral'}>
                        {m.status}
                      </Badge>
                    </div>
                    <div className="text-sm leading-7 text-text-secondary">{m.brief}</div>
                    {m.reason ? <div className="mt-2 text-xs text-warning">原因：{m.reason}</div> : null}
                  </div>
                ))}
              </div>
            </>
          ) : null}

          {resultTab === 'var' ? (
            varBarItems.length > 0 ? (
              <div className="space-y-4">
                <div className={NOTE_CARD_CLS}>用金额、百分比和波动率一起看，避免只盯单一 VaR 指标造成误判。</div>
                <BarChart items={varBarItems} height={240} yAxisName="VaR" colorByValue />
              </div>
            ) : (
              <EmptyState text="运行风险分析后，这里会显示 VaR 分布。" />
            )
          ) : null}

          {resultTab === 'stress' ? (
            stressItems.length > 0 ? (
              <div className="space-y-4">
                <div className={NOTE_CARD_CLS}>优先关注冲击最大的几个场景，看它们是否与近期持仓结构一致。</div>
                <BarChart items={stressItems} height={220} yAxisName="影响(%)" colorByValue />
              </div>
            ) : (
              <EmptyState text="运行风险分析后，这里会显示压力测试场景。" />
            )
          ) : null}

          {resultTab === 'exposure' ? (
            exposureItems.length > 0 ? (
              <div className="space-y-4">
                <div className={NOTE_CARD_CLS}>如果暴露过度集中，可以结合压力场景一起判断是否需要先做仓位修正。</div>
                <PieChart data={exposureItems} donut height={220} />
              </div>
            ) : (
              <EmptyState text="运行风险分析后，这里会显示风险暴露分布。" />
            )
          ) : null}
        </SectionCard>
      </div>
    </>
  );

  const summaryPanel = (
    <div className={SIDE_PANEL_CLS}>
      <div className="text-sm font-medium text-text-primary">风险工作区摘要</div>
      <div className="mt-3 grid gap-3 text-xs text-text-secondary">
        <div className="metric-tile rounded-[22px] p-3">
          <div>组合：{displayPortfolio}</div>
          <div className="mt-1">窗口：{lookbackDays} 天</div>
          <div className="mt-1">降级：{summary?.degraded ? '是' : '否'}</div>
          <div className="mt-1">模块：{availableModuleCount} / {moduleCards.length}</div>
        </div>
        <div className="metric-tile rounded-[22px] p-3">
          <div>缓存：{topCards.cache}</div>
          <div className="mt-1">
            抓取：{summary?.meta?.fetchedAt ? new Date(summary.meta.fetchedAt).toLocaleString('zh-CN') : '未知'}
          </div>
        </div>
      </div>
    </div>
  );

  const debugPanel = (
    <div className="grid gap-3">
      <div className={SIDE_PANEL_CLS}>
        <div className="text-sm font-medium text-text-primary">模块健康度</div>
        <div className="mt-3 space-y-3">
          {moduleCards.map((item) => (
            <div key={item.key} className={NOTE_CARD_CLS}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text-primary">{item.title}</span>
                <span
                  className={
                    item.status === '成功'
                      ? 'text-success'
                      : item.status === '降级'
                        ? 'text-warning'
                        : 'text-text-muted'
                  }
                >
                  {item.status}
                </span>
              </div>
              <div className="mt-1 leading-6">{item.brief}</div>
            </div>
          ))}
        </div>
      </div>
      {summary || varQ.data != null ? (
        <SectionCard className="p-4 sm:p-5">
          <h3 className="mt-0">排障与原始响应</h3>
          <p className="text-sm text-text-secondary mt-1 mb-3">
            只有在需要排查数据源异常或降级原因时，再展开这里查看原始返回。
          </p>
          {summary ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-text-secondary text-sm">查看风险汇总原始数据（summary）</summary>
              <pre className="mt-1 text-xs surface-muted p-3 rounded-xl overflow-auto max-h-[300px] font-mono">
                {JSON.stringify(summary, null, 2)}
              </pre>
            </details>
          ) : null}
          {varQ.data != null ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-text-secondary text-sm">查看 VaR 原始数据（varOnly）</summary>
              <pre className="mt-1 text-xs surface-muted p-3 rounded-xl overflow-auto max-h-[300px] font-mono">
                {JSON.stringify(varQ.data, null, 2)}
              </pre>
            </details>
          ) : null}
        </SectionCard>
      ) : null}
    </div>
  );

  const secondaryContent = summaryPanel;
  const mobileSummary = (
    <div className="panel-soft rounded-[20px] px-3 py-2 text-xs text-text-secondary">
      组合 {displayPortfolio} ｜ {lookbackDays} 天 ｜ 模块 {availableModuleCount}/{moduleCards.length}
    </div>
  );

  return (
    <PageContainer>
      <WorkspaceToolbar
        pageKey="risk"
        currentView={currentView}
        onApplyView={applyView}
        supportsPagePanels
        mobileSummaryMode="hidden"
      />
      <WorkspaceSplitLayout
        pageKey="risk"
        primary={primaryContent}
        secondary={secondaryContent}
        secondaryPanels={[
          { key: 'summary', label: '摘要', content: summaryPanel },
          { key: 'debug', label: '排障', content: debugPanel },
        ]}
        mobileSummary={mobileSummary}
        maxDefaultSections={0}
      />
    </PageContainer>
  );
}
