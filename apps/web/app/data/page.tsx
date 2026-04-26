'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import ResponsiveResultWorkbench from '@/components/responsive-result-workbench';
import {
  PageContainer,
  TabBar,
  SectionCard,
  StockCodeInput,
  KpiCard,
  KpiGrid,
  DataTable,
  Badge,
} from '@/components/ui';
import { PieChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, extractObject, fmtAmount, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

import {
  CHIP_BUTTON_CLS,
  FIELD_CLS,
  HERO_PRIMARY_BUTTON_CLS,
  HERO_SECONDARY_BUTTON_CLS,
  NOTE_CARD_CLS,
  RESOURCE_PRESETS,
  SIDE_PANEL_CLS,
  TABS,
  type ResourceKey,
  type Tab,
} from './data-page/config';
import { buildResourcePath, buildResourceSummaryRows, isRecord, normalizeOptionRow } from './data-page/helpers';

export default function DataPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const [tab, setTab] = useState<Tab>('option');
  const { code, setCode, codeError, setCodeError, validate, trimmedCode } = useStockCode('');
  const [underlying, setUnderlying] = useState('');
  const [underlyingError, setUnderlyingError] = useState<string | null>(null);
  const [resourceKind, setResourceKind] = useState<ResourceKey>('toolCatalog');
  const [resourceId, setResourceId] = useState('');
  const [resourceError, setResourceError] = useState<string | null>(null);
  const [queryPath, setQueryPath] = useState<string | null>(null);
  const { data, isFetching: isPending, error, refetch, dataUpdatedAt } = useApiQuery<unknown>(queryPath, { critical: true });
  const activeResourcePreset = (RESOURCE_PRESETS.find((item) => item.key === resourceKind) ??
    RESOURCE_PRESETS[0]) as (typeof RESOURCE_PRESETS)[number];
  const resourceRequiresId = activeResourcePreset.requiresId === true;
  const resourceInputLabel = activeResourcePreset.inputLabel;
  const resourcePlaceholder = activeResourcePreset.placeholder;
  const resourceDescription = activeResourcePreset.description;

  function submit() {
    let path: string;
    setUnderlyingError(null);
    setResourceError(null);

    if (tab === 'option') {
      const trimmedUnderlying = underlying.trim();
      if (!trimmedUnderlying) {
        setUnderlyingError('请输入真实的 ETF 期权标的代码');
        return;
      }
      path = `/data/option-chain?underlying=${encodeURIComponent(trimmedUnderlying)}`;
    } else if (tab === 'calendar') {
      path = '/data/trading-dates?count=30';
    } else if (tab === 'ipo') {
      path = '/data/ipo';
    } else if (tab === 'cb') {
      if (!trimmedCode) {
        setCodeError('请输入可转债代码');
        return;
      }
      path = `/data/cb?code=${encodeURIComponent(trimmedCode)}`;
    } else if (tab === 'resource') {
      const resolvedId = resourceId.trim();
      if (resourceRequiresId && !resolvedId) {
        setResourceError(`请输入${resourceInputLabel}`);
        return;
      }
      path = buildResourcePath(resourceKind, resolvedId);
    } else {
      if (!validate()) return;
      path = `/data/capital?code=${encodeURIComponent(trimmedCode)}`;
    }

    if (path === queryPath) refetch();
    else setQueryPath(path);
  }

  const optionRows = useMemo(
    () =>
      extractArray(data, 'options', 'calls', 'puts', 'chain')
        .map((row) => normalizeOptionRow(row))
        .filter((row) => row.strike != null || row.lastPrice != null || row.type),
    [data],
  );
  const calendarRows = extractArray(data, 'dates', 'tradingDates') as Array<Record<string, unknown>>;
  const ipoRows = extractArray(data, 'ipos', 'list', 'data') as Array<Record<string, unknown>>;
  const cbObj = tab === 'cb' ? (extractObject(data) as Record<string, unknown>) || null : null;
  const capObj = tab === 'capital' ? (extractObject(data) as Record<string, unknown>) || null : null;
  const resourceEnvelope = tab === 'resource' && isRecord(data) ? data : null;
  const resourceResult = resourceEnvelope?.result ?? null;
  const resourceObject = useMemo(
    () => (tab === 'resource' ? ((extractObject(resourceResult) as Record<string, unknown>) || {}) : {}),
    [resourceResult, tab],
  );
  const resourceTableRows = useMemo(
    () =>
      tab === 'resource'
        ? (extractArray(
            resourceResult,
            'tools',
            'items',
            'records',
            'datasets',
            'models',
            'factors',
            'strategies',
            'experiments',
            'runs',
            'checks',
            'alerts',
            'steps',
            'results',
          ) as Array<Record<string, unknown>>)
        : [],
    [resourceResult, tab],
  );
  const resourceSummaryRows = useMemo(
    () => (tab === 'resource' ? buildResourceSummaryRows(resourceObject) : []),
    [resourceObject, tab],
  );
  const resourceJson = useMemo(() => {
    if (tab !== 'resource') return '';
    try {
      return JSON.stringify(resourceResult ?? {}, null, 2);
    } catch {
      return '{"error":"resource_result_not_serializable"}';
    }
  }, [resourceResult, tab]);
  const resourceStatus = String(
    resourceObject.status ?? resourceObject.overall_status ?? resourceObject.current_status ?? resourceObject.name ?? 'resource',
  );
  const activeTabLabel = TABS.find((item) => item.key === tab)?.label ?? '数据';
  const resultCount =
    tab === 'option'
      ? optionRows.length
      : tab === 'calendar'
        ? calendarRows.length
        : tab === 'ipo'
          ? ipoRows.length
          : tab === 'resource'
            ? resourceTableRows.length || resourceSummaryRows.length || (resourceResult ? 1 : 0)
          : data
            ? 1
            : 0;
  const focusTarget =
    tab === 'option'
      ? underlying.trim() || '待输入 ETF 标的'
      : tab === 'calendar'
        ? '最近 30 个交易日'
      : tab === 'ipo'
        ? '最近 IPO 窗口'
        : tab === 'resource'
          ? resourceId.trim() || activeResourcePreset.label
          : trimmedCode || '待输入';
  const tabDescription =
    tab === 'option'
      ? '适合观察 ETF 期权链的行权价、成交量、持仓量与隐含波动率。'
      : tab === 'calendar'
        ? '适合确认开市、休市与节假日节奏，给后续策略或提醒页做时间参照。'
        : tab === 'ipo'
        ? '适合快速查看最近新股与新债窗口，判断一级市场供给节奏。'
        : tab === 'resource'
          ? '适合直接查看 MCP 资源对象，把 workflow、run、dataset、model、strategy 的结构化摘要拉出来核对。'
          : tab === 'cb'
            ? '适合用单只转债快速看价格、转股价值和溢价率。'
            : '适合用股本结构确认流通盘、限售盘与总市值的关系。';
  const latestDataRefreshAt = data && dataUpdatedAt ? dataUpdatedAt : null;
  const dataSummary = `当前聚焦 ${activeTabLabel}，目标 ${focusTarget}，结果 ${resultCount} 条，状态 ${isPending ? '加载中' : data ? '已返回' : '待查询'}。`;
  const pageActions = [
    {
      id: 'data.submit',
      label: `查询${activeTabLabel}`,
      description: '按当前类别和输入项发起查询',
      keywords: ['查询', '数据'],
      scope: 'page' as const,
      pageKey: 'data',
      run: async () => {
        submit();
        return { message: `已触发${activeTabLabel}查询` };
      },
    },
    {
      id: 'data.switch-market',
      label: '跳到行情看板',
      description: '带着当前查询目标切到行情页继续查看',
      keywords: ['行情', '跳转'],
      scope: 'page' as const,
      pageKey: 'data',
      run: () => {
        window.location.href = '/market';
        return { message: '已跳到行情看板' };
      },
    },
    {
      id: 'data.switch-technical',
      label: '跳到技术分析',
      description: '带着当前查询目标继续查看技术面',
      keywords: ['技术分析', '跳转'],
      scope: 'page' as const,
      pageKey: 'data',
      run: () => {
        window.location.href = '/technical';
        return { message: '已跳到技术分析' };
      },
    },
    {
      id: 'data.clear',
      label: '清空当前输入',
      description: '清空当前页的输入与查询上下文',
      keywords: ['清空', '重置'],
      scope: 'page' as const,
      pageKey: 'data',
      run: () => {
        setUnderlying('');
        setUnderlyingError(null);
        setCode('');
        setCodeError(null);
        setResourceId('');
        setResourceError(null);
        setQueryPath(null);
        return { message: '已清空当前输入' };
      },
    },
  ];
  usePageActions(pageActions);
  const dataEvidence = useMemo(
    () =>
      [
        { label: '当前类别', value: activeTabLabel },
        { label: '当前目标', value: focusTarget },
        { label: '结果条数', value: String(resultCount) },
        { label: '状态', value: isPending ? '加载中' : data ? '已返回' : '待查询' },
        ...(queryPath ? [{ label: '查询路径', value: queryPath }] : []),
      ].slice(0, 5),
    [activeTabLabel, data, focusTarget, isPending, queryPath, resultCount],
  );
  const dataRiskNotes = useMemo(() => {
    const notes: string[] = [];
    if (error) notes.push(`当前查询失败：${error}`);
    if (!error && !isPending && data && resultCount === 0) notes.push('当前查询已返回，但结果为空，需要调整类别或输入。');
    if (tab === 'resource' && resourceRequiresId && !resourceId.trim()) notes.push(`该资源类型需要先填写${resourceInputLabel}。`);
    return notes;
  }, [data, error, isPending, resourceId, resourceInputLabel, resourceRequiresId, resultCount, tab]);
  const dataLinks = useMemo(
    () => [
      { id: 'data-open-copilot-link', label: '继续问 Copilot', href: '/assistant' },
      { id: 'data-open-market-link', label: '跳到行情看板', href: '/market' },
      { id: 'data-open-technical-link', label: '跳到技术分析', href: '/technical' },
      { id: 'data-open-research-link', label: '跳到研究中心', href: '/research' },
    ],
    [],
  );
  const dataResult = buildLocalResultContract({
    summary: dataSummary,
    availableViews: resultCount > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['data.submit', 'data.switch-market', 'data.switch-technical', 'data.clear'],
    recommendedLinks: dataLinks,
    evidence: dataEvidence,
    riskNotes: dataRiskNotes,
    freshness: latestDataRefreshAt ? { label: '最近查询', asOf: new Date(latestDataRefreshAt).toISOString() } : null,
    platformMeta: {
      sourceTool: 'data-workspace',
      sourceChain: ['data', tab],
      degraded: Boolean(error),
      fallbackReason: error ? [error] : undefined,
    },
    workbenchTask: defaultWorkbenchTask(
      'data',
      `复查${activeTabLabel}`,
      queryPath ? `/data?tab=${encodeURIComponent(tab)}` : '/data',
      'data-review',
      { tab, queryPath, focusTarget, resultCount },
    ),
  });
  const showResultPanel = !compactLayout || isPending || Boolean(data) || Boolean(error);
  usePageContext({
    pageKey: 'data',
    title: '数据中心工作台',
    summary: dataSummary,
    stockCode: tab === 'cb' || tab === 'capital' ? trimmedCode || undefined : undefined,
    objectType: tab === 'resource' ? 'tool-registry' : tab === 'option' ? 'option-chain' : 'stock-data',
    objectId: focusTarget,
    resultType: `data-${tab}`,
    tags: [activeTabLabel, `${resultCount} 条结果`, isPending ? '加载中' : data ? '已返回' : '待查询'],
    suggestions: [
      `总结当前${activeTabLabel}最值得继续追问的点`,
      '把当前数据整理成下一步动作',
      '推荐我下一步该跳到哪个研究页',
    ],
    recommendedActions: dataResult.recommendedActions ?? [],
    recommendedLinks: dataResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(dataResult.evidence),
    riskNotes: dataResult.riskNotes ?? [],
    freshness: dataResult.freshness ?? null,
    raw: {
      tab,
      focusTarget,
      resultCount,
      queryPath,
      resourceKind,
      resourceId,
      pending: isPending,
      hasData: Boolean(data),
    },
  });

  function renderStarterState() {
    if (tab === 'option') {
      return (
        <EmptyState
          text="先输入真实的 ETF 期权标的，再加载期权链"
          hint="建议直接使用你当前关注的 ETF 标的代码发起查询，结果区会返回对应行权价、成交量和持仓量。"
        />
      );
    }
    if (tab === 'calendar') {
      return (
        <EmptyState
          text="加载最近 30 个交易日，快速确认节假日与开市节奏"
          hint="上方操作区会直接触发查询，返回后会展示最近交易日清单。"
        />
      );
    }
    if (tab === 'ipo') {
      return <EmptyState text="这里适合看最近的新股与新债申购安排" hint="直接使用上方查询按钮即可加载最近申购窗口。" />;
    }
    if (tab === 'cb') {
      return (
        <EmptyState
          text="请输入可转债代码后再查询"
          hint="这里不再预填样例代码，直接输入你要核对的真实转债代码即可。"
        />
      );
    }
    if (tab === 'resource') {
      return (
        <EmptyState
          text="先选择资源类型，再读取 MCP 资源对象"
          hint="无 ID 资源可直接读取；需要 ID 的资源类型必须提供真实对象标识。"
          action={
            <>
              <button
                type="button"
                onClick={() => {
                  setResourceKind('toolCatalog');
                  setResourceId('');
                }}
                className={CHIP_BUTTON_CLS}
              >
                工具目录
              </button>
              <button
                type="button"
                onClick={() => {
                  setResourceKind('governanceReport');
                  setResourceId('');
                }}
                className={CHIP_BUTTON_CLS}
              >
                治理总览
              </button>
            </>
          }
        />
      );
    }
    return (
      <EmptyState
        text="请输入股票代码后查看股本结构"
        hint="输入真实股票代码后，结果区会返回总股本、流通股和市值结构。"
      />
    );
  }

  function renderData() {
    if (!data) return null;

    if (tab === 'resource' && resourceEnvelope) {
      return (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)]">
            <div className="space-y-4">
              <div className="panel-soft rounded-[24px] p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Resource URI</div>
                <div className="mt-3 break-all text-sm font-medium text-text-primary">
                  {String(resourceEnvelope.resourceUri ?? '-')}
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className={NOTE_CARD_CLS}>
                    资源类型：<span className="font-medium text-text-primary">{activeResourcePreset.label}</span>
                  </div>
                  <div className={NOTE_CARD_CLS}>
                    当前状态：<span className="font-medium text-text-primary">{resourceStatus}</span>
                  </div>
                  <div className={NOTE_CARD_CLS}>
                    摘要字段：<span className="font-medium text-text-primary">{resourceSummaryRows.length}</span>
                  </div>
                  <div className={NOTE_CARD_CLS}>
                    明细行数：<span className="font-medium text-text-primary">{resourceTableRows.length}</span>
                  </div>
                </div>
              </div>

              {resourceSummaryRows.length ? (
                <DataTable
                  rows={resourceSummaryRows}
                  columns={[
                    { key: 'field', label: '字段', sortable: true },
                    { key: 'value', label: '值' },
                  ]}
                  maxHeight={320}
                />
              ) : (
                <EmptyState
                  text="当前资源没有直接可展示的标量摘要"
                  hint="这通常意味着结果以数组或深层对象为主，右侧可以直接看原始 JSON。"
                />
              )}
            </div>

            <div className="panel-soft rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Raw JSON</div>
              <pre className="mt-3 max-h-[520px] overflow-auto rounded-[22px] bg-slate-950/90 p-4 text-xs leading-6 text-slate-100">
                {resourceJson}
              </pre>
            </div>
          </div>

          {resourceTableRows.length ? (
            <DataTable rows={resourceTableRows} searchable maxHeight={460} onExport={() => exportCSV(resourceTableRows, `resource-${resourceKind}`)} />
          ) : (
            <EmptyState
              text="当前资源没有可平铺的列表数据"
              hint="如果这个对象更偏摘要类资源，左侧字段表和右侧 JSON 通常已经足够完成核对。"
            />
          )}
        </div>
      );
    }

    if (tab === 'option') {
      if (!optionRows.length) return <EmptyState text="无期权数据" />;
      return (
        <DataTable
          rows={optionRows}
          columns={[
            {
              key: 'strike',
              label: '行权价',
              align: 'right' as const,
              sortable: true,
              render: (value) => fmtNum(Number(value), 2),
            },
            { key: 'lastPrice', label: '最新价', align: 'right' as const, render: (value) => fmtNum(Number(value), 4) },
            {
              key: 'volume',
              label: '成交量',
              align: 'right' as const,
              sortable: true,
              render: (value) => fmtNum(Number(value), 0),
            },
            {
              key: 'openInterest',
              label: '持仓量',
              align: 'right' as const,
              sortable: true,
              render: (value) => fmtNum(Number(value), 0),
            },
            {
              key: 'impliedVol',
              label: '隐含波动率',
              align: 'right' as const,
              render: (value) => (value != null ? `${fmtNum(Number(value) * 100, 2)}%` : '-'),
            },
            {
              key: 'type',
              label: '类型',
              render: (value) => (
                <Badge variant={value === 'Call' || value === 'call' ? 'success' : 'danger'}>
                  {String(value ?? '-')}
                </Badge>
              ),
            },
          ]}
          onExport={() => exportCSV(optionRows, 'option-chain')}
        />
      );
    }

    if (tab === 'calendar') {
      if (!calendarRows.length) return <EmptyState text="无交易日历数据" />;
      return (
        <DataTable
          rows={calendarRows}
          columns={[
            { key: 'date', label: '日期', sortable: true },
            { key: 'dayOfWeek', label: '星期' },
            {
              key: 'isTrading',
              label: '交易日',
              render: (value) => <Badge variant={value ? 'success' : 'neutral'}>{value ? '是' : '否'}</Badge>,
            },
          ]}
          onExport={() => exportCSV(calendarRows, 'trading-calendar')}
        />
      );
    }

    if (tab === 'ipo') {
      if (!ipoRows.length) return <EmptyState text="无 IPO 数据" />;
      return (
        <DataTable
          rows={ipoRows}
          columns={[
            { key: 'code', label: '代码', sortable: true },
            { key: 'name', label: '名称', sortable: true },
            { key: 'ipoDate', label: '上市日期', sortable: true },
            {
              key: 'price',
              label: '发行价',
              align: 'right' as const,
              render: (value) => (value != null ? fmtNum(Number(value), 2) : '-'),
            },
            { key: 'industry', label: '行业' },
            {
              key: 'status',
              label: '状态',
              render: (value) => {
                const statusText = String(value ?? '');
                const isListed =
                  statusText.includes('上市') || statusText.includes('listed') || statusText === 'listed';
                return <Badge variant={isListed ? 'success' : 'warning'}>{statusText || '-'}</Badge>;
              },
            },
          ]}
          onExport={() => exportCSV(ipoRows, 'ipo-list')}
        />
      );
    }

    if (tab === 'cb' && cbObj) {
      return (
        <KpiGrid cols={3}>
          <KpiCard title="价格" value={fmtNum(Number(cbObj.price ?? 0), 2)} />
          <KpiCard title="转股价" value={fmtNum(Number(cbObj.conversionPrice ?? cbObj.conversion_price ?? 0), 2)} />
          <KpiCard title="转股价值" value={fmtNum(Number(cbObj.conversionValue ?? cbObj.conversion_value ?? 0), 2)} />
          <KpiCard title="溢价率" value={fmtNum(Number(cbObj.premium ?? 0) * 100, 2)} suffix="%" />
          <KpiCard title="评级" value={String(cbObj.rating ?? '-')} />
          <KpiCard title="到期日" value={String(cbObj.maturityDate ?? cbObj.maturity_date ?? '-')} />
        </KpiGrid>
      );
    }

    if (tab === 'capital' && capObj) {
      const totalShares = Number(capObj.totalShares ?? capObj.total_shares ?? 0);
      const floatShares = Number(capObj.floatShares ?? capObj.float_shares ?? 0);
      const restrictedShares = totalShares - floatShares;
      const marketCap = Number(capObj.marketCap ?? capObj.market_cap ?? 0);
      const pieData = [
        ...(floatShares > 0 ? [{ name: '流通股', value: floatShares, color: COLORS.primary }] : []),
        ...(restrictedShares > 0 ? [{ name: '限售股', value: restrictedShares, color: COLORS.warning }] : []),
      ];

      return (
        <div className="space-y-4">
          <KpiGrid cols={3}>
            <KpiCard title="总股本" value={fmtAmount(totalShares)} />
            <KpiCard title="流通股" value={fmtAmount(floatShares)} />
            <KpiCard title="总市值" value={fmtAmount(marketCap)} />
          </KpiGrid>
          {pieData.length > 0 ? <PieChart data={pieData} donut /> : null}
        </div>
      );
    }

    return <EmptyState text="无数据" />;
  }

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Data Workspace</Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={queryPath ? 'success' : 'warning'}>
                {queryPath ? '已建立查询上下文' : '等待首次查询'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              数据中心工作台
            </h1>
            <p className="mb-0 mt-3 hidden max-w-3xl text-sm leading-7 text-text-secondary sm:block sm:text-[15px]">
              这一页负责补齐交易链路中最常被临时查找的数据块。先决定是查期权、日历、IPO、可转债还是股本结构，再在结果区完成对比和导出。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={submit}
                disabled={isPending}
                aria-label={
                  tab === 'option'
                    ? '页头查询期权链'
                    : tab === 'calendar'
                      ? '页头加载交易日历'
                      : tab === 'ipo'
                        ? '页头查询IPO信息'
                        : tab === 'cb'
                          ? '页头查询可转债'
                          : tab === 'resource'
                            ? '页头读取资源对象'
                            : '页头查询股本'
                }
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                {isPending ? '加载中...' : `查询${activeTabLabel}`}
              </button>
              <button
                type="button"
                onClick={() => {
                  setUnderlying('');
                  setUnderlyingError(null);
                  setCode('');
                  setCodeError(null);
                  setResourceId('');
                  setResourceError(null);
                  setQueryPath(null);
                }}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                清空当前输入
              </button>
            </div>

            <div className="mt-5 hidden gap-3 xl:grid xl:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前类别</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">{tabDescription}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前目标</div>
                <div className="mt-3 text-lg font-semibold text-text-primary">{focusTarget}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">结果条数</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{resultCount}</div>
                <div className="mt-1 text-xs text-text-secondary">用于判断当前结果是否足够继续对比</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">状态</div>
                <div className="mt-3 text-lg font-semibold text-text-primary">
                  {isPending ? '加载中' : data ? '已返回' : '待查询'}
                </div>
              </div>
            </div>
          </div>

          <div className="hidden gap-3 xl:grid">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前查询焦点</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{focusTarget}</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  类别：<span className="font-medium text-text-primary">{activeTabLabel}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  结果条数：<span className="font-medium text-text-primary">{resultCount}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  下一步：
                  <span className="font-medium text-text-primary">
                    {tab === 'option'
                      ? '比对波动率与持仓量'
                      : tab === 'calendar'
                        ? '确认时间窗口'
                      : tab === 'ipo'
                        ? '补一级市场供给'
                        : tab === 'resource'
                          ? '核对对象关系与治理状态'
                          : tab === 'cb'
                            ? '看溢价与转股价值'
                            : '确认流通盘与市值'}
                  </span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关联跳转</div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href="/market" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  行情看板
                </Link>
                <Link href="/technical" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  技术分析
                </Link>
                <Link href="/fund-flow" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  资金流向
                </Link>
                <Link href="/valuation" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  估值分析
                </Link>
                <Link href="/macro" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  宏观数据
                </Link>
                <Link href="/research" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  研究中心
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      <ResponsiveResultWorkbench pageKey="data" title="数据结果工作台" result={dataResult} />

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Data Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">查询工作台</h2>
            <p className="mb-0 mt-2 hidden text-sm leading-7 text-text-secondary sm:block">
              先切换数据类别，再填写对应输入项。查询区只负责决定目标，不把结果阅读和筛选动作揉在一起。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前类别：<span className="font-medium text-text-primary">{activeTabLabel}</span>
          </div>
        </div>

        <div className="mt-4">
          <TabBar
            tabs={TABS}
            active={tab}
            onChange={(key) => {
              setTab(key);
              setQueryPath(null);
              setResourceError(null);
            }}
          />
        </div>

        <SectionCard tabAttached>
          {tab === 'option' ? (
            <div className="grid gap-4 xl:grid-cols-[220px_auto] xl:items-end">
              <label htmlFor="data-option-underlying" className="grid gap-2 text-xs text-text-secondary">
                <span className="font-medium uppercase tracking-[0.12em] text-text-muted">期权标的代码</span>
                <input
                  id="data-option-underlying"
                  value={underlying}
                  onChange={(e) => {
                    setUnderlying(e.target.value);
                    setUnderlyingError(null);
                  }}
                  placeholder="输入真实 ETF 标的代码"
                  className={FIELD_CLS}
                />
                {underlyingError ? <span className="text-xs text-error">{underlyingError}</span> : null}
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isPending}
                  onClick={submit}
                  aria-label="查询期权链工作台"
                  className={HERO_PRIMARY_BUTTON_CLS}
                >
                  查询期权链
                </button>
                <div className="text-sm text-text-secondary">不会自动预填标的代码，查询结果只来自当前输入。</div>
              </div>
            </div>
          ) : null}

          {tab === 'calendar' ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isPending}
                onClick={submit}
                aria-label="加载交易日历工作台"
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                加载交易日历
              </button>
              <div className="text-sm text-text-secondary">默认返回最近 30 个交易日，用来确认节假日与开市节奏。</div>
            </div>
          ) : null}

          {tab === 'ipo' ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isPending}
                onClick={submit}
                aria-label="查询IPO信息工作台"
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                查询 IPO 信息
              </button>
              <div className="text-sm text-text-secondary">适合快速查看最近新股与新债申购窗口。</div>
            </div>
          ) : null}

          {tab === 'cb' ? (
            <div className="grid gap-4 xl:grid-cols-[260px_auto] xl:items-end">
              <StockCodeInput
                id="data-cb-code"
                label="可转债代码"
                value={code}
                onChange={setCode}
                error={codeError}
                placeholder="如 123039"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isPending}
                  onClick={submit}
                  aria-label="查询可转债工作台"
                  className={HERO_PRIMARY_BUTTON_CLS}
                >
                  查询可转债
                </button>
                <div className="text-sm text-text-secondary">使用真实转债代码后再进入价格、转股价值和溢价率核对。</div>
              </div>
            </div>
          ) : null}

          {tab === 'resource' ? (
            <div className="grid gap-4 xl:grid-cols-[240px_260px_auto] xl:items-end">
              <label htmlFor="data-resource-kind" className="grid gap-2 text-xs text-text-secondary">
                <span className="font-medium uppercase tracking-[0.12em] text-text-muted">资源类型</span>
                <select
                  id="data-resource-kind"
                  value={resourceKind}
                  onChange={(e) => {
                    const nextKind = e.target.value as ResourceKey;
                    setResourceKind(nextKind);
                    setResourceId('');
                    setResourceError(null);
                    setQueryPath(null);
                  }}
                  className={FIELD_CLS}
                >
                  {RESOURCE_PRESETS.map((item) => (
                    <option key={item.key} value={item.key}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>

              <label htmlFor="data-resource-id" className="grid gap-2 text-xs text-text-secondary">
                <span className="font-medium uppercase tracking-[0.12em] text-text-muted">{resourceInputLabel}</span>
                <input
                  id="data-resource-id"
                  value={resourceId}
                  onChange={(e) => {
                    setResourceId(e.target.value);
                    setResourceError(null);
                  }}
                  placeholder={resourcePlaceholder}
                  disabled={!resourceRequiresId}
                  className={FIELD_CLS}
                />
              </label>

              <div className="grid gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                    读取资源对象
                  </button>
                </div>
                <div className="text-sm text-text-secondary">{resourceDescription}</div>
                {resourceError ? <div className="text-xs text-error">{resourceError}</div> : null}
              </div>
            </div>
          ) : null}

          {tab === 'capital' ? (
            <div className="grid gap-4 xl:grid-cols-[260px_auto] xl:items-end">
              <StockCodeInput
                id="data-capital-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
                placeholder="如 600519"
              />
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={isPending}
                  onClick={submit}
                  aria-label="查询股本工作台"
                  className={HERO_PRIMARY_BUTTON_CLS}
                >
                  查询股本
                </button>
                <div className="text-sm text-text-secondary">只在填写真实股票代码后返回股本和市值结构。</div>
              </div>
            </div>
          ) : null}
        </SectionCard>
      </div>

      {showResultPanel ? (
      <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Result View</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">查询结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              结果区负责查看、比对和导出。先确认返回是否完整，再决定跳去行情、技术或估值页继续联动。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前目标：<span className="font-medium text-text-primary">{focusTarget}</span>
          </div>
        </div>

        {isPending ? <LoadingState text="加载中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
        {!isPending && !data && !error ? renderStarterState() : null}
        {renderData()}
      </div>
      ) : null}
    </PageContainer>
  );
}
