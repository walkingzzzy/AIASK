'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import CollapsibleSectionCard from '@/components/collapsible-section-card';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import { Badge, DataTable, PageContainer, SectionCard } from '@/components/ui';
import { EmptyState, ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useMobile } from '@/hooks/use-mobile';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type { SkillDescriptor, SkillExecutionMode, SkillStatus, WorkspaceSharedContext } from '@aiask/shared-types';

type SkillStatusFilter = 'all' | SkillStatus;

type SkillTriggerResponse = {
  success?: boolean;
  message?: string;
  skill?: SkillDescriptor;
  execution?: unknown;
  result?: unknown;
  source?: string;
  meta?: {
    backend_requested?: string;
    backend_used?: string;
    fallback_used?: boolean;
    fallback_reason?: unknown;
    latency_ms?: number;
  };
};

type WorkspaceContextPatch = Partial<{
  [K in keyof WorkspaceSharedContext]: WorkspaceSharedContext[K] | null;
}>;

function normalizeSkillStatus(value: unknown): SkillStatus {
  return value === 'deprecated' || value === 'registered' ? value : 'executable';
}

function normalizeExecutionMode(value: unknown, status: SkillStatus, executable: boolean): SkillExecutionMode {
  if (value === 'deprecated' || value === 'no_handler' || value === 'orchestrated') return value;
  if (status === 'deprecated') return 'deprecated';
  return executable ? 'orchestrated' : 'no_handler';
}

function normalizeSkill(item: unknown): SkillDescriptor | null {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
  const record = item as Record<string, unknown>;
  const id = typeof record.id === 'string' ? record.id.trim() : '';
  if (!id) return null;

  const executable = Boolean(record.executable);
  const status = normalizeSkillStatus(record.status);
  return {
    id,
    name: typeof record.name === 'string' && record.name.trim() ? record.name.trim() : undefined,
    category: typeof record.category === 'string' && record.category.trim() ? record.category.trim() : undefined,
    description:
      typeof record.description === 'string' && record.description.trim() ? record.description.trim() : undefined,
    path: typeof record.path === 'string' && record.path.trim() ? record.path.trim() : undefined,
    status,
    executable: status === 'executable' && executable,
    deprecated: status === 'deprecated',
    handler_available: typeof record.handler_available === 'boolean' ? record.handler_available : undefined,
    execution_mode: normalizeExecutionMode(record.execution_mode, status, executable),
    input_schema:
      record.input_schema && typeof record.input_schema === 'object' && !Array.isArray(record.input_schema)
        ? (record.input_schema as Record<string, unknown>)
        : undefined,
    output_schema:
      record.output_schema && typeof record.output_schema === 'object' && !Array.isArray(record.output_schema)
        ? (record.output_schema as Record<string, unknown>)
        : undefined,
    supported_tasks: Array.isArray(record.supported_tasks)
      ? record.supported_tasks.map((entry) => String(entry)).filter(Boolean)
      : undefined,
  };
}

function normalizeSkills(raw: unknown): SkillDescriptor[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((item) => normalizeSkill(item)).filter((item): item is SkillDescriptor => item != null);
}

function statusBadgeVariant(status: SkillStatus) {
  if (status === 'executable') return 'success' as const;
  if (status === 'deprecated') return 'danger' as const;
  return 'warning' as const;
}

function modeBadgeVariant(mode?: SkillExecutionMode) {
  if (mode === 'orchestrated') return 'info' as const;
  if (mode === 'deprecated') return 'danger' as const;
  return 'neutral' as const;
}

function buildWorkspacePayload(context: ReturnType<typeof selectActiveWorkspace>['context']) {
  const payload: Record<string, unknown> = {};
  if (context.stockCode) {
    payload.code = context.stockCode;
    payload.stock_code = context.stockCode;
  }
  if (context.eventCode) payload.event_code = context.eventCode;
  if (context.accountId) payload.account_id = context.accountId;
  if (context.portfolioId) payload.portfolio_id = context.portfolioId;
  if (context.executionId) payload.execution_id = context.executionId;
  if (context.artifactId) payload.artifact_id = context.artifactId;
  if (context.benchmark) payload.benchmark = context.benchmark;
  if (typeof context.days === 'number' && context.days > 0) payload.days = context.days;
  if (typeof context.lookbackDays === 'number' && context.lookbackDays > 0)
    payload.lookback_days = context.lookbackDays;
  if (context.sourcePage) payload.source_page = context.sourcePage;
  if (context.taskType) payload.task_type = context.taskType;
  if (context.resultType) payload.result_type = context.resultType;
  return payload;
}

function stringifyPayload(payload: Record<string, unknown>) {
  return JSON.stringify(payload, null, 2);
}

function inferWorkspacePatch(payload: Record<string, unknown>): WorkspaceContextPatch {
  const patch: WorkspaceContextPatch = {};
  const code = [payload.code, payload.stock_code, payload.symbol, payload.ticker].find(
    (value) => typeof value === 'string' && value.trim(),
  );
  if (typeof code === 'string' && code.trim()) patch.stockCode = code.trim();

  const eventCode = payload.event_code;
  if (typeof eventCode === 'string' && eventCode.trim()) patch.eventCode = eventCode.trim();

  const accountId = [payload.accountId, payload.account_id].find((value) => typeof value === 'string' && value.trim());
  if (typeof accountId === 'string' && accountId.trim()) patch.accountId = accountId.trim();

  const portfolioId = [payload.portfolioId, payload.portfolio_id].find(
    (value) => (typeof value === 'string' && value.trim()) || (typeof value === 'number' && Number.isFinite(value)),
  );
  if (portfolioId != null) patch.portfolioId = String(portfolioId);

  const executionId = [payload.executionId, payload.execution_id].find(
    (value) => typeof value === 'string' && value.trim(),
  );
  if (typeof executionId === 'string' && executionId.trim()) patch.executionId = executionId.trim();

  const artifactId = [payload.artifactId, payload.artifact_id].find(
    (value) => typeof value === 'string' && value.trim(),
  );
  if (typeof artifactId === 'string' && artifactId.trim()) patch.artifactId = artifactId.trim();

  if (typeof payload.benchmark === 'string' && payload.benchmark.trim()) patch.benchmark = payload.benchmark.trim();

  const days = Number(payload.days);
  if (Number.isFinite(days) && days > 0) patch.days = Math.trunc(days);

  const lookbackDays = Number(payload.lookbackDays ?? payload.lookback_days);
  if (Number.isFinite(lookbackDays) && lookbackDays > 0) patch.lookbackDays = Math.trunc(lookbackDays);

  const sourcePage = payload.sourcePage ?? payload.source_page;
  if (typeof sourcePage === 'string' && sourcePage.trim()) patch.sourcePage = sourcePage.trim();

  const taskType = payload.taskType ?? payload.task_type;
  if (typeof taskType === 'string' && taskType.trim()) patch.taskType = taskType.trim();

  const resultType = payload.resultType ?? payload.result_type;
  if (typeof resultType === 'string' && resultType.trim()) patch.resultType = resultType.trim();

  return patch;
}

function parsePayloadText(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('payload 必须是 JSON 对象');
  }
  return parsed as Record<string, unknown>;
}

function shortSkillName(skill: SkillDescriptor) {
  return skill.name || skill.id;
}

export default function SkillsPage() {
  const router = useRouter();
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const searchParams = useStableSearchParams();
  const requestedSkillId = searchParams.get('skill') ?? '';
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const skillsQ = useApiQuery<SkillDescriptor[]>('/v1/skills', {
    parse: (raw) => normalizeSkills(raw),
    staleTime: 60_000,
  });
  const triggerSkillApi = useApiMutation<SkillTriggerResponse>({
    successToast: false,
  });

  const [keyword, setKeyword] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<SkillStatusFilter>('all');
  const [selectedSkillId, setSelectedSkillId] = useState(requestedSkillId);
  const [payloadText, setPayloadText] = useState('{}');
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const [lastSkillsRefreshAt, setLastSkillsRefreshAt] = useState<string | null>(null);

  const skills = useMemo(() => skillsQ.data ?? [], [skillsQ.data]);
  const skillsBootstrapping = skillsQ.isPending && skills.length === 0;
  const skillsUnavailable = skillsQ.serviceUnavailable && skills.length === 0;
  const categories = useMemo(
    () => [...new Set(skills.map((skill) => skill.category).filter((entry): entry is string => Boolean(entry)))].sort(),
    [skills],
  );
  const filteredSkills = useMemo(
    () =>
      skills.filter((skill) => {
        if (categoryFilter !== 'all' && skill.category !== categoryFilter) return false;
        if (statusFilter !== 'all' && skill.status !== statusFilter) return false;
        if (!keyword.trim()) return true;
        const lower = keyword.trim().toLowerCase();
        return [
          skill.id,
          skill.name ?? '',
          skill.description ?? '',
          skill.category ?? '',
          ...(skill.supported_tasks ?? []),
        ].some((entry) => entry.toLowerCase().includes(lower));
      }),
    [categoryFilter, keyword, skills, statusFilter],
  );

  const requestedSkillExists = useMemo(
    () => Boolean(requestedSkillId) && skills.some((skill) => skill.id === requestedSkillId),
    [requestedSkillId, skills],
  );
  const selectedSkillIdExists = useMemo(
    () => Boolean(selectedSkillId) && skills.some((skill) => skill.id === selectedSkillId),
    [selectedSkillId, skills],
  );
  const preferredSkillId = requestedSkillExists ? requestedSkillId : selectedSkillIdExists ? selectedSkillId : '';
  const defaultSkill = useMemo(
    () =>
      filteredSkills.find((skill) => skill.executable) ??
      skills.find((skill) => skill.executable) ??
      filteredSkills[0] ??
      skills[0] ??
      null,
    [filteredSkills, skills],
  );
  const selectedSkill = useMemo(
    () =>
      filteredSkills.find((skill) => skill.id === preferredSkillId) ??
      skills.find((skill) => skill.id === preferredSkillId) ??
      defaultSkill,
    [defaultSkill, filteredSkills, preferredSkillId, skills],
  );
  const activeSkillId = selectedSkill?.id ?? preferredSkillId;
  const workspacePayload = useMemo(() => buildWorkspacePayload(workbenchContext), [workbenchContext]);
  const executionResult = triggerSkillApi.data;
  const latestSkillsRefreshText = skillsQ.dataUpdatedAt
    ? new Date(skillsQ.dataUpdatedAt).toLocaleString('zh-CN')
    : '等待首个技能快照';

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (activeSkillId) params.set('skill', activeSkillId);
    else params.delete('skill');
    const nextQs = params.toString();
    if (nextQs !== searchParams.toString()) {
      router.replace(nextQs ? `/skills?${nextQs}` : '/skills', { scroll: false });
    }
  }, [activeSkillId, router, searchParams]);

  const fillWorkspacePayload = useCallback(() => {
    setPayloadError(null);
    setPayloadText(stringifyPayload(workspacePayload));
  }, [workspacePayload]);

  const refreshSkills = useCallback(async () => {
    await skillsQ.refetch();
    setLastSkillsRefreshAt(new Date().toLocaleString('zh-CN'));
  }, [skillsQ]);

  const applySkillsView = useCallback((snapshot: Record<string, unknown>) => {
    if (typeof snapshot.keyword === 'string') setKeyword(snapshot.keyword);
    if (typeof snapshot.categoryFilter === 'string') setCategoryFilter(snapshot.categoryFilter);
    if (
      snapshot.statusFilter === 'all' ||
      snapshot.statusFilter === 'registered' ||
      snapshot.statusFilter === 'executable' ||
      snapshot.statusFilter === 'deprecated'
    ) {
      setStatusFilter(snapshot.statusFilter);
    }
    if (typeof snapshot.selectedSkillId === 'string') setSelectedSkillId(snapshot.selectedSkillId);
    if (typeof snapshot.payloadText === 'string') setPayloadText(snapshot.payloadText);
    setPayloadError(null);
  }, []);

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      keyword,
      categoryFilter,
      statusFilter,
      selectedSkillId: activeSkillId,
      payloadText,
    }),
    [activeSkillId, categoryFilter, keyword, payloadText, statusFilter],
  );

  const runSelectedSkill = useCallback(async () => {
    if (!selectedSkill) {
      return { message: '当前没有可执行的技能' };
    }
    if (!selectedSkill.executable) {
      return { message: `技能 ${shortSkillName(selectedSkill)} 当前不可执行` };
    }

    try {
      const payload = parsePayloadText(payloadText);
      setPayloadError(null);
      const patch = inferWorkspacePatch(payload);
      if (Object.keys(patch).length > 0) {
        updateWorkbenchContext(patch);
      }
      const response = await triggerSkillApi.triggerAsync(
        `/v1/skills/${encodeURIComponent(selectedSkill.id)}/trigger`,
        { method: 'POST' },
        payload,
      );
      return { message: response.message || `已触发 ${shortSkillName(selectedSkill)}` };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setPayloadError(message);
      throw error;
    }
  }, [payloadText, selectedSkill, triggerSkillApi, updateWorkbenchContext]);

  const bookmarkSkillTask = useCallback(() => {
    if (!selectedSkill) return;
    addWorkbenchTask({
      pageKey: 'skills',
      title: `复查技能 ${shortSkillName(selectedSkill)}`,
      href: `/skills?skill=${encodeURIComponent(selectedSkill.id)}`,
      kind: 'skill-review',
      payload: {
        skillId: selectedSkill.id,
        status: selectedSkill.status,
        category: selectedSkill.category ?? null,
      },
    });
  }, [addWorkbenchTask, selectedSkill]);

  const pageActions = useMemo(
    () => [
      {
        id: 'skills.refresh',
        label: '刷新技能列表',
        description: '重新从 MCP 技能注册表拉取可用技能',
        keywords: ['刷新', '技能列表'],
        scope: 'page' as const,
        pageKey: 'skills',
        run: async () => {
          await refreshSkills();
          return { message: '已刷新技能列表' };
        },
      },
      {
        id: 'skills.fill-workspace-payload',
        label: '填充工作区上下文',
        description: '把当前工作区里的股票、账户、组合、执行等上下文注入技能参数',
        keywords: ['工作区上下文', 'payload'],
        scope: 'page' as const,
        pageKey: 'skills',
        run: () => {
          fillWorkspacePayload();
          return { message: '已填充工作区上下文' };
        },
      },
      {
        id: 'skills.toggle-executable',
        label: statusFilter === 'executable' ? '显示全部技能' : '只看可执行技能',
        description: '在所有技能和可执行技能之间切换',
        keywords: ['可执行', '筛选'],
        scope: 'page' as const,
        pageKey: 'skills',
        run: () => {
          setStatusFilter((prev) => (prev === 'executable' ? 'all' : 'executable'));
          return { message: statusFilter === 'executable' ? '已切回全部技能' : '已切到可执行技能' };
        },
      },
      {
        id: 'skills.trigger-selected',
        label: selectedSkill ? `执行 ${shortSkillName(selectedSkill)}` : '执行当前技能',
        description: '按当前 JSON payload 触发选中的技能',
        keywords: ['执行技能', '触发'],
        scope: 'page' as const,
        pageKey: 'skills',
        run: async () => runSelectedSkill(),
      },
    ],
    [fillWorkspacePayload, refreshSkills, runSelectedSkill, selectedSkill, statusFilter],
  );

  usePageActions(pageActions);
  const skillsSummary = `当前技能中心已加载 ${skills.length} 个技能，筛选后剩余 ${filteredSkills.length} 个，当前聚焦 ${selectedSkill ? shortSkillName(selectedSkill) : '未选择技能'}。`;
  const skillsEvidence = [
    { label: '技能总数', value: String(skills.length) },
    { label: '筛选后结果', value: String(filteredSkills.length) },
    { label: '状态筛选', value: statusFilter === 'all' ? '全部状态' : statusFilter },
    { label: '分类筛选', value: categoryFilter === 'all' ? '全部分类' : categoryFilter },
    { label: '当前技能', value: selectedSkill ? shortSkillName(selectedSkill) : '未选择技能' },
  ];
  const skillsLinks = [
    { id: 'skills-open-assistant-link', label: '继续问 Copilot', href: '/assistant' },
    { id: 'skills-open-strategy-market-link', label: '策略超市', href: '/strategy-market?from=skills' },
    { id: 'skills-open-data-link', label: '数据中心', href: '/data' },
    { id: 'skills-open-research-link', label: '研究中心', href: '/research' },
  ];
  const skillsRiskNotes = [
    ...(skillsUnavailable ? ['当前技能注册表不可用，目录可能不完整。'] : []),
    ...((selectedSkill && !selectedSkill.executable) ? [`当前技能 ${shortSkillName(selectedSkill)} 暂不可执行。`] : []),
    ...(payloadError ? [`当前 payload 存在错误：${payloadError}`] : []),
  ];
  const skillsResult = buildLocalResultContract({
    summary: skillsSummary,
    availableViews: filteredSkills.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['skills.refresh', 'skills.fill-workspace-payload', 'skills.toggle-executable', 'skills.trigger-selected'],
    recommendedLinks: skillsLinks,
    evidence: skillsEvidence,
    riskNotes: skillsRiskNotes,
    freshness: lastSkillsRefreshAt ? { updatedAt: lastSkillsRefreshAt, label: '技能同步时间' } : null,
    platformMeta: {
      sourceTool: 'skills-registry',
      sourceChain: ['skills', categoryFilter, statusFilter],
      degraded: skillsUnavailable,
      fallbackReason: skillsQ.error ? [skillsQ.error] : undefined,
    },
    workbenchTask: defaultWorkbenchTask(
      'skills',
      `复查技能${selectedSkill ? ` ${shortSkillName(selectedSkill)}` : ''}`,
      selectedSkill ? `/skills?skill=${encodeURIComponent(selectedSkill.id)}` : '/skills',
      'skill-review',
      {
        selectedSkillId: selectedSkill?.id ?? null,
        statusFilter,
        categoryFilter,
        keyword,
      },
    ),
  });

  usePageContext({
    pageKey: 'skills',
    title: '技能中心',
    summary: skillsSummary,
    objectType: 'tool-registry',
    objectId: selectedSkill?.id ?? `${statusFilter}:${categoryFilter}:${keyword || 'all'}`,
    resultType: 'skill-catalog',
    tags: [
      `${filteredSkills.length} 个结果`,
      statusFilter === 'all' ? '全部状态' : statusFilter,
      categoryFilter === 'all' ? '全部分类' : categoryFilter,
    ],
    suggestions: [
      selectedSkill ? `执行 ${shortSkillName(selectedSkill)}` : '先筛出可执行技能',
      '把当前工作区上下文填入技能参数',
      '总结当前技能最适合做什么',
    ],
    recommendedActions: skillsResult.recommendedActions ?? [],
    recommendedLinks: skillsResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(skillsResult.evidence),
    riskNotes: skillsResult.riskNotes ?? [],
    freshness: skillsResult.freshness ?? null,
    raw: {
      keyword,
      categoryFilter,
      statusFilter,
      selectedSkillId: activeSkillId,
      filteredCount: filteredSkills.length,
      totalCount: skills.length,
    },
  });

  return (
    <PageContainer>
      <div className="mb-3">
        <h1 className="m-0 text-lg font-semibold">技能中心</h1>
        {!compactLayout ? (
        <p className="mb-0 mt-1 text-xs text-text-secondary">
          这里直接消费 MCP 技能注册表，负责浏览能力边界、校验可执行性，并把技能触发接进工作区与 Copilot。
        </p>
        ) : null}
      </div>

      {!compactLayout ? (
      <details className="panel-soft mt-4 rounded-[24px] p-4">
        <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">展开视图工具</summary>
        <div className="mt-4">
          <WorkspaceToolbar
            pageKey="skills"
            currentView={currentView}
            onApplyView={applySkillsView}
            supportsPagePanels
            mobileSummaryMode="hidden"
          />
        </div>
      </details>
      ) : null}

      {!compactLayout ? (
      <CollapsibleSectionCard
        title="技能总览与筛选策略"
        summary="技能目录、可执行状态和推荐使用方式统一下沉到这一层。默认直接进入技能工作区，只有需要重新理解能力边界时再展开。"
        className="mt-4"
        badge={<Badge variant="neutral">{filteredSkills.length} / {skills.length || 0}</Badge>}
        defaultOpen
      >
      <SectionCard className="border-0 bg-transparent p-0 shadow-none">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">
                总计 {skillsBootstrapping ? '同步中' : skillsUnavailable ? '暂不可用' : skills.length}
              </Badge>
              <Badge variant="success">
                可执行 {skillsBootstrapping || skillsUnavailable ? '--' : skills.filter((skill) => skill.status === 'executable').length}
              </Badge>
              <Badge variant="warning">
                仅注册 {skillsBootstrapping || skillsUnavailable ? '--' : skills.filter((skill) => skill.status === 'registered').length}
              </Badge>
              <Badge variant="danger">
                已废弃 {skillsBootstrapping || skillsUnavailable ? '--' : skills.filter((skill) => skill.status === 'deprecated').length}
              </Badge>
            </div>
            <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">
              技能中心不是新的对话入口，而是把后端已有的能力目录、可执行状态和触发结果显式化，便于用户理解“系统现在到底能做什么”。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  void refreshSkills();
                }}
                data-testid="page-primary-action"
                data-action-testid="skills-refresh-action"
                className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                刷新技能列表
              </button>
              <button
                type="button"
                onClick={fillWorkspacePayload}
                className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm"
              >
                填充工作区上下文
              </button>
            </div>
            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前技能
                {' '}
                {skillsBootstrapping ? '等待技能注册表' : selectedSkill ? shortSkillName(selectedSkill) : '未选择'}
                {' '}
                ｜ 筛选后
                {' '}
                {skillsBootstrapping || skillsUnavailable ? '--' : filteredSkills.length}
                {' / '}
                {skillsBootstrapping || skillsUnavailable ? '--' : skills.length}
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                {skillsBootstrapping
                  ? '技能注册表正在同步，稍后会自动恢复。'
                  : skillsUnavailable
                    ? '技能注册表暂不可用，页面会在服务恢复后自动重试。'
                    : selectedSkill
                  ? `状态 ${selectedSkill.status} ｜ 执行模式 ${selectedSkill.execution_mode ?? 'no_handler'} ｜ ${selectedSkill.executable ? '可触发' : '不可触发'}`
                  : '请先在右侧列表选择一个技能。'}
              </p>
              <p className="mt-2 mb-0 text-xs text-text-secondary">
                最近快照：{latestSkillsRefreshText}
                {lastSkillsRefreshAt ? ` ｜ 手动刷新：${lastSkillsRefreshAt}` : ''}
              </p>
            </div>
          </div>
          <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
            <div className="font-medium text-text-primary">推荐使用方式</div>
            <ol className="mb-0 mt-2 space-y-1 pl-4">
              <li>先按分类或可执行状态收窄范围。</li>
              <li>再把当前工作区上下文填进 payload，避免手工重复输入。</li>
              <li>最后将常用技能记入工作区任务，作为固定流程的一部分。</li>
            </ol>
          </div>
        </div>
      </SectionCard>
      </CollapsibleSectionCard>
      ) : null}

      <WorkspaceSplitLayout
        pageKey="skills"
        primary={
          <SectionCard className="h-full p-4">
            {skillsBootstrapping ? (
              <LoadingState text="正在同步技能注册表..." />
            ) : skillsUnavailable ? (
              <ErrorState
                text="技能注册表暂不可用，页面会在服务恢复后自动重试。"
                onRetry={() => void skillsQ.refetch()}
              />
            ) : !selectedSkill ? (
              <EmptyState
                text="还没有选中的技能。"
                hint="从左侧选择一个技能，查看它的执行状态、输入 schema 和触发结果。"
              />
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="m-0 text-base font-semibold text-text-primary">{shortSkillName(selectedSkill)}</h2>
                    <MetaLine>{selectedSkill.description ?? '该技能当前没有描述信息。'}</MetaLine>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={statusBadgeVariant(selectedSkill.status)}>{selectedSkill.status}</Badge>
                    <Badge variant={modeBadgeVariant(selectedSkill.execution_mode)}>
                      {selectedSkill.execution_mode ?? 'no_handler'}
                    </Badge>
                    <Badge variant={selectedSkill.executable ? 'success' : 'warning'}>
                      {selectedSkill.executable ? '可触发' : '不可触发'}
                    </Badge>
                  </div>
                </div>

                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
                    <div className="font-medium text-text-primary">技能标识</div>
                    <div className="mt-2 break-all font-mono">{selectedSkill.id}</div>
                    <div className="mt-2">分类：{selectedSkill.category ?? '未分类'}</div>
                    <div className="mt-1">Handler：{selectedSkill.handler_available ? '已接入' : '未声明'}</div>
                    {selectedSkill.path ? <div className="mt-1 break-all">路径：{selectedSkill.path}</div> : null}
                  </div>
                  <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
                    <div className="font-medium text-text-primary">支持任务</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(selectedSkill.supported_tasks ?? []).length > 0 ? (
                        selectedSkill.supported_tasks?.map((task) => (
                          <Badge key={task} variant="neutral">
                            {task}
                          </Badge>
                        ))
                      ) : (
                        <span>当前未声明 supported_tasks。</span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={fillWorkspacePayload}
                    className="rounded border border-glass-border px-3 py-1.5 text-sm"
                  >
                    填充工作区上下文
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setPayloadError(null);
                      setPayloadText('{}');
                    }}
                    className="rounded border border-glass-border px-3 py-1.5 text-sm"
                  >
                    清空参数
                  </button>
                  <button
                    type="button"
                    onClick={bookmarkSkillTask}
                    className="rounded border border-glass-border px-3 py-1.5 text-sm"
                  >
                    记入工作区任务
                  </button>
                  <button
                    type="button"
                    data-testid="skill-trigger-action"
                    onClick={() => {
                      void runSelectedSkill().catch(() => undefined);
                    }}
                    disabled={!selectedSkill.executable || triggerSkillApi.isPending}
                    className="rounded border border-primary px-3 py-1.5 text-sm text-primary disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {triggerSkillApi.isPending ? '执行中...' : '触发技能'}
                  </button>
                </div>

                <div className="mt-4">
                  <div className="mb-2 text-sm font-medium text-text-primary">技能参数 JSON</div>
                  <textarea
                    value={payloadText}
                    onChange={(event) => {
                      setPayloadError(null);
                      setPayloadText(event.target.value);
                    }}
                    className="min-h-[220px] w-full rounded-xl border border-glass-border bg-surface/70 p-3 font-mono text-xs leading-6"
                    spellCheck={false}
                  />
                  {payloadError ? <p className="mb-0 mt-2 text-xs text-danger">{payloadError}</p> : null}
                </div>

                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  <details className="rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                    <summary className="cursor-pointer text-sm font-medium text-text-primary">输入 Schema</summary>
                    <pre className="mb-0 mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-text-secondary">
                      {JSON.stringify(selectedSkill.input_schema ?? {}, null, 2)}
                    </pre>
                  </details>
                  <details className="rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                    <summary className="cursor-pointer text-sm font-medium text-text-primary">输出 Schema</summary>
                    <pre className="mb-0 mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-text-secondary">
                      {JSON.stringify(selectedSkill.output_schema ?? {}, null, 2)}
                    </pre>
                  </details>
                </div>

                <div className="mt-4 rounded-xl border border-glass-border bg-surface-alt/40 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-text-primary">最近一次触发结果</div>
                    {executionResult?.source ? <Badge variant="info">{executionResult.source}</Badge> : null}
                  </div>

                  {!triggerSkillApi.isPending && !executionResult && !triggerSkillApi.error ? (
                    <EmptyState
                      text="当前还没有触发结果。"
                      hint="先确认技能状态为 executable，再用上面的 JSON payload 触发一次。"
                      className="py-6"
                    />
                  ) : null}

                  {triggerSkillApi.error ? <ErrorState text={triggerSkillApi.error} /> : null}

                  {executionResult ? (
                    <>
                      <p className="mb-0 mt-3 text-sm text-text-primary">
                        {executionResult.message ?? `已执行 ${shortSkillName(selectedSkill)}`}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
                        {executionResult.meta?.backend_requested ? (
                          <Badge variant="neutral">请求后端 {executionResult.meta.backend_requested}</Badge>
                        ) : null}
                        {executionResult.meta?.backend_used ? (
                          <Badge variant="neutral">实际后端 {executionResult.meta.backend_used}</Badge>
                        ) : null}
                        {typeof executionResult.meta?.latency_ms === 'number' ? (
                          <Badge variant="neutral">耗时 {executionResult.meta.latency_ms}ms</Badge>
                        ) : null}
                        {executionResult.meta?.fallback_used ? <Badge variant="warning">使用回退</Badge> : null}
                      </div>
                      <details className="mt-3 rounded-xl border border-glass-border bg-surface/60 p-3">
                        <summary className="cursor-pointer text-sm font-medium text-text-primary">
                          查看执行结果 JSON
                        </summary>
                        <pre className="mb-0 mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-[11px] text-text-secondary">
                          {JSON.stringify(
                            executionResult.execution ?? executionResult.result ?? executionResult,
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </>
                  ) : null}
                </div>
              </>
            )}
          </SectionCard>
        }
        secondary={
          <SectionCard className="h-full p-4">
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="搜索技能 ID、名称、描述"
                className="min-w-[220px] flex-1 rounded border border-glass-border px-3 py-1.5 text-sm"
              />
              <select
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
                className="rounded border border-glass-border px-3 py-1.5 text-sm"
              >
                <option value="all">全部分类</option>
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as SkillStatusFilter)}
                className="rounded border border-glass-border px-3 py-1.5 text-sm"
              >
                <option value="all">全部状态</option>
                <option value="executable">可执行</option>
                <option value="registered">仅注册</option>
                <option value="deprecated">已废弃</option>
              </select>
            </div>

            {skillsBootstrapping ? <LoadingState text="加载技能注册表中..." /> : null}
            {skillsQ.error ? <ErrorState text={skillsQ.error} onRetry={() => void skillsQ.refetch()} /> : null}
            {!skillsBootstrapping && !skillsQ.error && filteredSkills.length === 0 ? (
              <EmptyState
                text="当前筛选条件下没有匹配的技能。"
                hint="可以先切回全部状态，再用工作区任务模板确认哪些能力最值得前端化。"
              />
            ) : null}

            {filteredSkills.length > 0 ? (
              <DataTable
                rows={filteredSkills.map((skill) => ({
                  id: skill.id,
                  name: shortSkillName(skill),
                  category: skill.category ?? '未分类',
                  status: skill.status,
                  executionMode: skill.execution_mode ?? 'no_handler',
                  executable: skill.executable ? '是' : '否',
                  description: skill.description ?? '',
                }))}
                rowKey="id"
                maxHeight={620}
                onRowClick={(row) => setSelectedSkillId(String(row.id ?? ''))}
                columns={[
                  {
                    key: 'name',
                    label: '技能',
                    render: (value, row) => (
                      <div>
                        <div className="font-medium text-text-primary">
                          {String(value)}
                          {String(row.id ?? '') === selectedSkill?.id ? (
                            <span className="ml-2 text-[11px] text-primary">当前</span>
                          ) : null}
                        </div>
                        <div className="mt-1 break-all font-mono text-[11px] text-text-muted">
                          {String(row.id ?? '')}
                        </div>
                      </div>
                    ),
                  },
                  { key: 'category', label: '分类', width: 120 },
                  {
                    key: 'status',
                    label: '状态',
                    width: 92,
                    render: (value) => (
                      <Badge variant={statusBadgeVariant(String(value) as SkillStatus)}>{String(value)}</Badge>
                    ),
                  },
                  {
                    key: 'executionMode',
                    label: '执行',
                    width: 110,
                    render: (value) => (
                      <Badge variant={modeBadgeVariant(String(value) as SkillExecutionMode)}>{String(value)}</Badge>
                    ),
                  },
                ]}
              />
            ) : null}
          </SectionCard>
        }
      />
    </PageContainer>
  );
}
