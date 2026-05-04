'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PageContainer, TabBar, SectionCard, DataTable } from '@/components/ui';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { AskAiButton } from '@/components/ask-ai-button';
import { FreshnessTag } from '@/components/ui/freshness-tag';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import ResultWorkbench from '@/components/result-workbench';
import { usePageContext } from '@/hooks/use-page-context';
import { usePageActions } from '@/hooks/use-page-actions';
import { type PageActionDefinition } from '@/lib/page-action-bus';
import { useCopilotStore } from '@/store/copilot-store';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import { authedFetch, extractApiErrorMessage } from '@/lib/api';
import { exportCSV } from '@/lib/export';
import { fmtNum } from '@/lib/data-utils';
import type { ResultAction, ResultContract, ResultLink } from '@aiask/shared-types';

/* ── 类型 ── */
type ScreenerTab = 'semantic' | 'condition';
type ScreenResult = { code: string; name: string; score?: number; industry?: string; market_cap?: number; pe?: number; [k: string]: unknown };
type SavedFilter = { id: string; label: string; tab: ScreenerTab; query: string; conditions: string[]; savedAt: string };

const PRESET_CONDITIONS = [
  { label: 'ROE > 15%', value: 'roe>15' },
  { label: '市盈率 < 20', value: 'pe<20' },
  { label: '市值 > 100亿', value: 'market_cap>100' },
  { label: '营收增速 > 10%', value: 'revenue_growth>10' },
  { label: '净利润增速 > 20%', value: 'net_profit_growth>20' },
  { label: '股息率 > 3%', value: 'dividend_yield>3' },
  { label: '负债率 < 50%', value: 'debt_ratio<50' },
  { label: '流动比率 > 1.5', value: 'current_ratio>1.5' },
];

const SEMANTIC_EXAMPLES = ['高股息银行股', '新能源龙头', '白酒高端品牌', '半导体设备国产替代', '消费复苏受益股'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function readPath(value: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => {
    if (!isRecord(acc)) return undefined;
    return acc[key];
  }, value);
}

function extractScreenItems(payload: unknown): ScreenResult[] {
  const candidates = [
    readPath(payload, 'data.items'),
    readPath(payload, 'data.results'),
    readPath(payload, 'data.matched'),
    readPath(payload, 'data.stocks'),
    readPath(payload, 'data.data.items'),
    readPath(payload, 'data.data.results'),
    readPath(payload, 'data.data.matched'),
    readPath(payload, 'data.data.stocks'),
    readPath(payload, 'items'),
    readPath(payload, 'results'),
    readPath(payload, 'matched'),
    readPath(payload, 'stocks'),
    Array.isArray(payload) ? payload : null,
  ];

  const items = candidates.find(Array.isArray);
  return Array.isArray(items) ? items as ScreenResult[] : [];
}

function extractScreenError(payload: unknown): string | null {
  if (typeof payload === 'string') {
    return /error executing tool|validation error/i.test(payload) ? payload : null;
  }
  if (!isRecord(payload)) return null;

  const directError = readPath(payload, 'error');
  if (typeof directError === 'string' && directError.trim()) {
    return directError;
  }

  const toolCandidates = [
    readPath(payload, 'data.result'),
    readPath(payload, 'data.data.result'),
    readPath(payload, 'data'),
  ];
  for (const candidate of toolCandidates) {
    if (typeof candidate === 'string' && /error executing tool|validation error/i.test(candidate)) {
      return candidate;
    }
  }

  if (payload.success === false && typeof payload.message === 'string') {
    return payload.message;
  }
  return null;
}

function loadSavedFilters(): SavedFilter[] {
  if (typeof window === 'undefined') return [];
  try {
    return JSON.parse(localStorage.getItem('screener:saved_filters') ?? '[]') as SavedFilter[];
  } catch {
    return [];
  }
}

function saveSavedFilters(filters: SavedFilter[]) {
  if (typeof window === 'undefined') return;
  localStorage.setItem('screener:saved_filters', JSON.stringify(filters));
}

export default function ScreenerPage() {
  const workbenchHydrated = useWorkbenchStore((s) => s.hydrated);
  const workbenchContext = useWorkbenchStore((s) => selectActiveWorkspace(s).context);
  const updateWorkbenchContext = useWorkbenchStore((s) => s.updateContext);
  const setDockOpen = useCopilotStore((s) => s.setDockOpen);
  const setPendingInject = useCopilotStore((s) => s.setPendingInject);

  const [tab, setTab] = useState<ScreenerTab>('semantic');
  const [query, setQuery] = useState((workbenchContext as Record<string, unknown>).screenerQuery as string ?? '');
  const [conditions, setConditions] = useState<string[]>([]);
  const [conditionInput, setConditionInput] = useState('');
  const [results, setResults] = useState<ScreenResult[]>([]);
  const [isPending, setIsPending] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [lastResponse, setLastResponse] = useState<Record<string, unknown> | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setSavedFilters(loadSavedFilters());
  }, []);

  /* ── 当前视图快照 ── */
  const currentView = useMemo<Record<string, unknown>>(
    () => ({ tab, query, conditions }),
    [tab, query, conditions],
  );
  const resultContract = useMemo(
    () => ((readPath(lastResponse, 'data.result_contract') ?? null) as ResultContract | null),
    [lastResponse],
  );
  const hasScreenOutcome = results.length > 0 || Boolean(resultContract);
  const primaryResult = results[0] ?? null;
  const primaryCode = String(primaryResult?.code ?? '').trim();
  const primaryName = String(primaryResult?.name ?? primaryCode).trim();
  const screenResultLinks = useMemo<ResultLink[]>(
    () =>
      primaryCode
        ? [
            { id: 'screener-stock', label: '个股详情', href: `/stock?code=${encodeURIComponent(primaryCode)}` },
            { id: 'screener-fundamental', label: '基本面', href: `/fundamental?code=${encodeURIComponent(primaryCode)}` },
            { id: 'screener-technical', label: '技术分析', href: `/technical?code=${encodeURIComponent(primaryCode)}` },
            { id: 'screener-watchlist', label: '查看自选股', href: '/watchlist' },
          ]
        : [
            { id: 'screener-market', label: '去行情看板', href: '/market' },
            { id: 'screener-research', label: '继续研究页', href: '/research' },
          ],
    [primaryCode],
  );
  const screenResultSummary = resultContract?.summary ?? (results.length > 0
    ? `当前筛到 ${results.length} 只股票，优先结果 ${primaryName || primaryCode || '未命名'}。`
    : hasScreenOutcome
      ? `当前${tab === 'semantic' ? '语义选股' : '条件组合'}已执行，但暂未命中可继续查看的股票结果。`
      : '等待输入选股条件并执行。');
  const screenEvidenceSummary = useMemo(
    () => resultContract?.evidence?.map((item) => `${item.label}：${item.value}`) ?? [],
    [resultContract?.evidence],
  );
  const screenResultActions = useMemo<ResultAction[]>(
    () =>
      results.length > 0
        ? [
            {
              id: 'screener.open-copilot-followup',
              actionId: 'screener.open-copilot-followup',
              label: '打开 Copilot 解读筛选结果',
              description: '把当前选股结果注入 Copilot，继续做研究与排序。',
            },
          ]
        : [],
    [results.length],
  );
  const screenCompareContent = useMemo(() => {
    if (results.length < 2) return null;
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {results.slice(0, 3).map((row, index) => (
          <div key={`${row.code || row.name || 'candidate'}-${index}`} className="metric-tile rounded-[22px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{row.code}</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{row.name || row.code}</div>
            <div className="mt-2 text-xs leading-6 text-text-secondary">
              行业 {String(row.industry ?? '未知')} ｜ 匹配分 {fmtNum(Number(row.score ?? 0), 2)}
            </div>
          </div>
        ))}
      </div>
    );
  }, [results]);
  const screenVisualContent = useMemo(() => {
    const counts = results.reduce<Record<string, number>>((acc, row) => {
      const key = String(row.industry ?? '未知');
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    const items = Object.entries(counts).sort((left, right) => right[1] - left[1]).slice(0, 6);
    if (items.length === 0) return null;
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map(([industry, count]) => (
          <div key={industry} className="metric-tile rounded-[22px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">行业分布</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{industry}</div>
            <div className="mt-2 text-xs text-text-secondary">{count} 只候选股票</div>
          </div>
        ))}
      </div>
    );
  }, [results]);

  const applyView = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (snapshot.tab === 'condition') setTab('condition');
      else setTab('semantic');
      if (typeof snapshot.query === 'string') setQuery(snapshot.query);
      if (Array.isArray(snapshot.conditions)) setConditions(snapshot.conditions as string[]);
    },
    [],
  );

  /* ── PageContext ── */
  usePageContext(useMemo(() => ({
    pageKey: 'screener',
    title: '条件选股',
    summary: results.length > 0
      ? `当前筛选到 ${results.length} 只股票，模式：${tab === 'semantic' ? '语义选股' : '条件组合'}`
      : hasScreenOutcome
        ? `当前${tab === 'semantic' ? '语义选股' : '条件组合'}已执行，但暂未命中可继续查看的股票结果。`
      : '条件选股工作台，支持自然语言和条件组合选股',
    stockCode: primaryCode || undefined,
    objectType: results.length > 0 ? 'stock-list' : hasScreenOutcome ? 'screen-result' : undefined,
    objectId: primaryCode || (tab === 'semantic' ? query : conditions.join('|')) || undefined,
    resultType: hasScreenOutcome ? 'screen-result' : undefined,
    tags: ['选股', 'screener', tab],
    suggestions: [
      '把筛选结果里市值最小的加入自选',
      '解释当前筛选条件的逻辑',
      '对结果按行业做分类汇总',
      '生成当前结果的简要分析',
    ],
    recommendedActions: screenResultActions,
    recommendedLinks: screenResultLinks,
    evidenceSummary: screenEvidenceSummary,
    riskNotes: resultContract?.riskNotes ?? [],
    freshness: resultContract?.freshness ?? null,
    raw: { tab, query, conditions, resultCount: results.length, primaryCode },
  }), [
    conditions,
    primaryCode,
    query,
    resultContract?.freshness,
    resultContract?.riskNotes,
    results.length,
    screenEvidenceSummary,
    screenResultActions,
    screenResultLinks,
    tab,
    hasScreenOutcome,
  ]));

  /* ── PageActions ── */
  const runScreen = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setIsPending(true);
    setErrorMsg(null);
    setLastResponse(null);

    try {
      let url: string;
      if (tab === 'semantic') {
        if (!query.trim()) { setErrorMsg('请输入选股描述'); setIsPending(false); return; }
        url = `/v1/screener/semantic?q=${encodeURIComponent(query.trim())}&limit=50`;
      } else {
        if (conditions.length === 0) { setErrorMsg('请至少添加一个选股条件'); setIsPending(false); return; }
        url = `/v1/screener/condition?conditions=${encodeURIComponent(conditions.join('|'))}&limit=50`;
      }

      const resp = await authedFetch(url, { signal: ctrl.signal });
      const json = await resp.json().catch(() => null);
      if (!resp.ok) {
        throw new Error(extractApiErrorMessage(json, `HTTP ${resp.status}`));
      }
      const toolError = extractScreenError(json);
      if (toolError) {
        throw new Error(toolError);
      }
      const items = extractScreenItems(json);
      setLastResponse(isRecord(json) ? json : null);
      setResults(items);
      setUpdatedAt(Date.now());
      if (workbenchHydrated) {
        const first = items[0] ?? null;
        const firstCode = String(first?.code ?? '').trim();
        updateWorkbenchContext({
          stockCode: firstCode || null,
          screenerQuery: tab === 'semantic' ? query : null,
          sourcePage: 'screener',
          taskType: tab === 'semantic' ? 'semantic_screen' : 'condition_screen',
          resultType: 'screen-result',
        });
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setErrorMsg((e as Error).message);
    } finally {
      setIsPending(false);
    }
  }, [tab, query, conditions, workbenchHydrated, updateWorkbenchContext]);

  const pageActions = useMemo<PageActionDefinition[]>(() => [
    {
      id: 'screener.open-copilot-followup',
      label: '打开 Copilot 解读筛选结果',
      description: '把当前选股结果注入 Copilot，继续做研究与排序。',
      scope: 'page',
      pageKey: 'screener',
      run: () => {
        if (!screenResultSummary) {
          throw new Error('当前还没有可解读的筛选结果');
        }
        setPendingInject({
          prompt: `请解读当前${tab === 'semantic' ? '语义选股' : '条件组合'}结果，并给出下一步研究建议。`,
          contextPatch: {
            ...(primaryCode ? { stockCode: primaryCode } : {}),
            summary: screenResultSummary,
            resultType: 'screen-result',
            recommendedActions: screenResultActions,
            recommendedLinks: screenResultLinks,
            evidenceSummary: screenEvidenceSummary,
            riskNotes: resultContract?.riskNotes ?? [],
            freshness: resultContract?.freshness ?? null,
            raw: {
              tab,
              query,
              conditions,
              resultCount: results.length,
              primaryCode,
            },
          },
        });
        setDockOpen(true);
        return { message: '已打开 Copilot 并注入筛选结果' };
      },
    },
    {
      id: 'screener.set-query',
      label: '填入语义选股条件',
      description: 'AI 填入自然语言选股条件并执行',
      scope: 'page',
      pageKey: 'screener',
      run: (payload) => {
        if (typeof payload?.query === 'string') {
          setTab('semantic');
          setQuery(payload.query as string);
        }
      },
    },
    {
      id: 'screener.add-condition',
      label: '添加条件',
      description: 'AI 添加一个量化选股条件',
      scope: 'page',
      pageKey: 'screener',
      run: (payload) => {
        if (typeof payload?.condition === 'string') {
          setTab('condition');
          setConditions((prev) => [...new Set([...prev, payload.condition as string])]);
        }
      },
    },
    {
      id: 'screener.run',
      label: '执行选股',
      scope: 'page',
      pageKey: 'screener',
      run: () => void runScreen(),
    },
  ], [
    conditions,
    primaryCode,
    query,
    resultContract?.freshness,
    resultContract?.riskNotes,
    results.length,
    runScreen,
    screenEvidenceSummary,
    screenResultActions,
    screenResultLinks,
    screenResultSummary,
    setDockOpen,
    setPendingInject,
    tab,
  ]);

  usePageActions(pageActions);

  function saveCurrentFilter() {
    const filter: SavedFilter = {
      id: `filter_${Date.now()}`,
      label: tab === 'semantic' ? (query.slice(0, 20) || '语义筛选') : (conditions.slice(0, 2).join(', ') || '条件筛选'),
      tab,
      query,
      conditions,
      savedAt: new Date().toISOString(),
    };
    const next = [filter, ...savedFilters].slice(0, 10);
    setSavedFilters(next);
    saveSavedFilters(next);
  }

  function applyFilter(f: SavedFilter) {
    setTab(f.tab);
    setQuery(f.query);
    setConditions(f.conditions);
  }

  function deleteSavedFilter(id: string) {
    const next = savedFilters.filter((f) => f.id !== id);
    setSavedFilters(next);
    saveSavedFilters(next);
  }

  function addCondition(val: string) {
    const v = val.trim();
    if (!v || conditions.includes(v)) return;
    setConditions((prev) => [...prev, v]);
    setConditionInput('');
  }

  const columns = useMemo(() => [
    {
      key: 'code', label: '代码', width: 90,
      render: (v: unknown, row: Record<string, unknown>) =>
        <StockLink code={String(v ?? '')} name={String(row.name ?? '')} />,
    },
    { key: 'name', label: '名称', width: 100 },
    { key: 'industry', label: '行业' },
    {
      key: 'score', label: '匹配分',
      render: (v: unknown) => v != null ? <span className="font-mono text-primary">{fmtNum(Number(v), 2)}</span> : '—',
    },
    {
      key: 'market_cap', label: '市值(亿)',
      render: (v: unknown) => v != null ? fmtNum(Number(v), 1) : '—',
    },
    { key: 'pe', label: 'PE', render: (v: unknown) => v != null ? fmtNum(Number(v), 1) : '—' },
    {
      key: '_actions', label: '操作', width: 130,
      render: (_v: unknown, row: Record<string, unknown>) => {
        const code = String(row.code ?? '');
        const name = String(row.name ?? '');
        const industry = String(row.industry ?? '未知');
        const score = fmtNum(Number(row.score ?? 0), 2);
        return (
          <div className="flex items-center gap-1">
            <WatchlistButton code={code} name={name} size="sm" />
            <AskAiButton
              stockCode={code}
              summary={`${name}，行业：${industry}，得分：${score}`}
              prompt={`请分析 ${code} ${name} 的投资价值`}
              iconOnly
            />
          </div>
        );
      },
    },
  ], []);

  const primaryContent = (
    <>
      <WorkspaceToolbar pageKey="screener" currentView={currentView} onApplyView={applyView} />
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <TabBar
          tabs={[{ key: 'semantic', label: '语义选股' }, { key: 'condition', label: '条件组合' }]}
          active={tab}
          onChange={(k) => setTab(k as ScreenerTab)}
        />
        {results.length > 0 && updatedAt ? (
          <FreshnessTag updatedAt={updatedAt} source="MCP screener_manager" />
        ) : null}
        {results.length > 0 ? (
          <span className="text-xs text-text-secondary">共 {results.length} 只</span>
        ) : null}
      </div>

      {tab === 'semantic' ? (
        <SectionCard className="mb-4">
          <div className="font-semibold text-sm mb-2">自然语言选股</div>
          <div className="flex gap-2 mb-3">
            <input
              className="flex-1 input-field text-sm"
              placeholder="例如：高股息银行股、新能源龙头、市值 200 亿以下的半导体..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void runScreen(); }}
            />
            <button className="btn-primary px-4" onClick={() => void runScreen()} disabled={isPending}>
              {isPending ? '筛选中…' : '开始筛选'}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {SEMANTIC_EXAMPLES.map((ex) => (
              <button
                key={ex}
                className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary hover:bg-surface-alt transition"
                onClick={() => { setQuery(ex); }}
              >
                {ex}
              </button>
            ))}
          </div>
        </SectionCard>
      ) : (
        <SectionCard className="mb-4">
          <div className="font-semibold text-sm mb-2">条件组合选股</div>
          <div className="flex gap-2 mb-3">
            <input
              className="flex-1 input-field text-sm"
              placeholder="输入条件，例如：roe>15 或 pe<20"
              value={conditionInput}
              onChange={(e) => setConditionInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') addCondition(conditionInput); }}
            />
            <button className="btn-secondary px-3" onClick={() => addCondition(conditionInput)}>添加</button>
            <button className="btn-primary px-4" onClick={() => void runScreen()} disabled={isPending || conditions.length === 0}>
              {isPending ? '筛选中…' : '执行筛选'}
            </button>
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {PRESET_CONDITIONS.map((p) => (
              <button
                key={p.value}
                onClick={() => addCondition(p.value)}
                className={`rounded-full border px-3 py-1 text-xs transition ${conditions.includes(p.value) ? 'border-primary text-primary bg-primary/10' : 'border-glass-border text-text-secondary hover:bg-surface-alt'}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {conditions.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {conditions.map((c) => (
                <span key={c} className="inline-flex items-center gap-1 rounded-full bg-primary/10 border border-primary/30 px-3 py-0.5 text-xs text-primary">
                  {c}
                  <button onClick={() => setConditions((prev) => prev.filter((x) => x !== c))} className="hover:text-red-400 ml-1">✕</button>
                </span>
              ))}
              <button className="text-xs text-text-secondary hover:text-red-400" onClick={() => setConditions([])}>清空</button>
            </div>
          ) : null}
        </SectionCard>
      )}

      {resultContract ? (
        <ResultWorkbench
          pageKey="screener"
          title="筛选结果下一步"
          result={resultContract}
          compareContent={screenCompareContent}
          visualContent={screenVisualContent}
          extraActions={screenResultActions}
          extraLinks={screenResultLinks}
        />
      ) : null}

      {results.length > 0 ? (
        <div className="flex items-center gap-2 mb-3">
          <button className="btn-secondary text-xs px-3 py-1" onClick={() => exportCSV(results, `screener_${Date.now()}.csv`)}>
            导出 CSV
          </button>
          <button className="btn-secondary text-xs px-3 py-1" onClick={saveCurrentFilter}>
            保存筛选器
          </button>
          <AskAiButton
            prompt={`当前筛选到 ${results.length} 只股票（${tab === 'semantic' ? query : conditions.join('，')}），请帮我分析筛选结果并给出投资建议`}
            label="AI 分析结果"
          />
        </div>
      ) : null}

      {errorMsg ? <ErrorState text={errorMsg} onRetry={() => void runScreen()} /> : null}
      {isPending ? <LoadingState /> : null}
      {!isPending && !errorMsg && results.length === 0 && !resultContract ? (
        <EmptyState text="暂无筛选结果，请输入选股条件后点击执行" />
      ) : null}
      {!isPending && results.length > 0 ? (
        <SectionCard>
          <div className="font-semibold text-sm mb-2">筛选结果（{results.length} 只）</div>
          <DataTable columns={columns} rows={results as Record<string, unknown>[]} rowKey="code" />
        </SectionCard>
      ) : null}
    </>
  );

  const secondaryContent = savedFilters.length > 0 ? (
    <div className="p-4">
      <div className="font-semibold text-sm mb-3">已保存筛选器</div>
      <div className="flex flex-col gap-2">
        {savedFilters.map((f) => (
          <div key={f.id} className="flex items-center gap-2 rounded-lg border border-glass-border px-3 py-2 text-sm">
            <button className="flex-1 text-left hover:text-primary transition" onClick={() => applyFilter(f)}>
              <div className="font-medium truncate">{f.label}</div>
              <div className="text-xs text-text-secondary">{new Date(f.savedAt).toLocaleDateString('zh-CN')}</div>
            </button>
            <button className="text-xs text-text-secondary hover:text-red-400" onClick={() => deleteSavedFilter(f.id)}>✕</button>
          </div>
        ))}
      </div>
    </div>
  ) : <></>;

  return (
    <PageContainer>
      <h1 className="m-0 border-b border-glass-border px-4 py-2 text-lg font-bold">条件选股</h1>
      <WorkspaceSplitLayout pageKey="screener" primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
