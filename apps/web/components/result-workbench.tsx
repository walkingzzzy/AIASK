'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type ReactNode, useMemo, useState } from 'react';
import { Badge, SectionCard, TabBar, useToast } from '@/components/ui';
import { FreshnessTag } from '@/components/ui/freshness-tag';
import { useApiQuery } from '@/hooks/use-api-query';
import { pageActionBus } from '@/lib/page-action-bus';
import { useWorkbenchStore, type WorkspacePageKey } from '@/store/workbench-store';
import type {
  ResultAction,
  ResultContract,
  ResultLink,
  ResultSkillSuggestion,
  ResultStrategySuggestion,
  ResultView,
} from '@aiask/shared-types';

type ResultWorkbenchProps = {
  pageKey: WorkspacePageKey;
  title?: string;
  result: ResultContract | null | undefined;
  compareContent?: ReactNode;
  visualContent?: ReactNode;
  extraActions?: ResultAction[];
  extraLinks?: ResultLink[];
  className?: string;
};

type SkillRegistryEntry = {
  id: string;
  name?: string;
  executable: boolean;
  supportedTasks: string[];
};

const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const ACTION_CHIP_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const ACTION_CARD_CLS =
  'w-full rounded-[22px] border border-white/60 bg-white/28 px-4 py-3 text-left shadow-[0_18px_34px_-28px_rgba(15,23,42,0.2)] transition hover:-translate-y-0.5';

function normalizeSkillRegistry(raw: unknown): SkillRegistryEntry[] {
  if (!Array.isArray(raw)) return [];
  const items: SkillRegistryEntry[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
    const record = item as Record<string, unknown>;
    const id = typeof record.id === 'string' ? record.id.trim() : '';
    if (!id) continue;
    items.push({
      id,
      name: typeof record.name === 'string' && record.name.trim() ? record.name.trim() : undefined,
      executable: Boolean(record.executable) && record.status !== 'deprecated',
      supportedTasks: Array.isArray(record.supported_tasks)
        ? record.supported_tasks.map((entry) => String(entry).trim()).filter(Boolean)
        : [],
    });
  }
  return items;
}

function uniqueActions(actions: ResultAction[]) {
  const seen = new Set<string>();
  return actions.filter((action) => {
    const key = `${action.actionId ?? action.id}::${action.label}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueLinks(links: ResultLink[]) {
  const seen = new Set<string>();
  return links.filter((link) => {
    const key = `${link.href}::${link.label}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueStrings(items: string[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (!item || seen.has(item)) return false;
    seen.add(item);
    return true;
  });
}

function buildStrategyHref(pageKey: string, suggestion: ResultStrategySuggestion) {
  if (suggestion.href) return suggestion.href;
  const params = new URLSearchParams();
  params.set('from', pageKey);
  if (suggestion.task) params.set('task', suggestion.task);
  if (suggestion.query) params.set('q', suggestion.query);
  if (suggestion.category) params.set('category', suggestion.category);
  const queryString = params.toString();
  return queryString ? `/strategy-market?${queryString}` : '/strategy-market';
}

function resolveWorkbenchJumpHref(pageKey: string, result: ResultContract, fallbackLinks: ResultLink[]) {
  const firstStrategy = result.strategySuggestions?.[0];
  if (firstStrategy) {
    return buildStrategyHref(pageKey, firstStrategy);
  }
  const firstLink = result.recommendedLinks?.[0] ?? fallbackLinks[0];
  if (firstLink?.href) {
    return firstLink.href;
  }
  return result.workbenchTask?.href ?? '/strategy-market';
}

function resolveSkillSuggestions(
  suggestions: ResultSkillSuggestion[],
  registry: SkillRegistryEntry[],
) {
  return suggestions.map((suggestion) => {
    const byTask = suggestion.supportedTask
      ? registry.find((entry) => entry.executable && entry.supportedTasks.includes(suggestion.supportedTask!))
      : null;
    const byId = registry.find((entry) => entry.executable && entry.id === suggestion.skillId) ?? null;
    const match = byTask ?? byId;
    return {
      ...suggestion,
      resolvedSkillId: match?.id ?? suggestion.skillId,
      resolvedLabel: match?.name ?? suggestion.label ?? match?.id ?? suggestion.skillId,
      executable: match?.executable ?? registry.length === 0,
    };
  });
}

function resolveViewTabs(result: ResultContract, compareContent?: ReactNode, visualContent?: ReactNode) {
  const views = Array.from(new Set<ResultView>(['summary', ...(result.availableViews ?? []), 'next_step']));
  return views.filter((view) => {
    if (view === 'compare') return Boolean(compareContent);
    if (view === 'visual') return Boolean(visualContent);
    return true;
  });
}

export default function ResultWorkbench({
  pageKey,
  title = '研究结果工作台',
  result,
  compareContent,
  visualContent,
  extraActions = [],
  extraLinks = [],
  className = '',
}: ResultWorkbenchProps) {
  const router = useRouter();
  const { toast } = useToast();
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const skillSuggestions = useMemo(() => result?.skillSuggestions ?? [], [result?.skillSuggestions]);
  const skillsQ = useApiQuery<SkillRegistryEntry[]>('/v1/skills', {
    enabled: skillSuggestions.length > 0,
    parse: normalizeSkillRegistry,
    staleTime: 60_000,
    nonFatal: true,
  });

  const mergedActions = uniqueActions([
    ...(result?.primaryAction ? [result.primaryAction] : []),
    ...(result?.secondaryActions ?? []),
    ...(result?.recommendedActions ?? []),
    ...extraActions,
  ]);
  const mergedLinks = useMemo(
    () => uniqueLinks([...(result?.recommendedLinks ?? []), ...extraLinks]),
    [extraLinks, result?.recommendedLinks],
  );
  const nextSteps = useMemo(
    () => uniqueStrings(result?.recommendedNextActions ?? []),
    [result?.recommendedNextActions],
  );
  const resolvedSkills = useMemo(
    () => resolveSkillSuggestions(skillSuggestions, skillsQ.data ?? []),
    [skillSuggestions, skillsQ.data],
  );
  const views = useMemo(
    () => (result ? resolveViewTabs(result, compareContent, visualContent) : []),
    [compareContent, result, visualContent],
  );
  const [activeView, setActiveView] = useState<ResultView>('summary');
  const resolvedActiveView = views.includes(activeView) ? activeView : views[0] ?? 'summary';

  const resolvedResult = result;
  if (!resolvedResult) return null;
  const activeResult: ResultContract = resolvedResult;

  async function runAction(action: ResultAction) {
    try {
      const actionId = action.actionId ?? action.id;
      const response = await pageActionBus.execute(actionId, action.payload);
      const message =
        response && typeof response === 'object' && 'message' in response
          ? String((response as { message?: unknown }).message ?? '已执行动作')
          : `${action.label} 已执行`;
      toast(message, 'success');
    } catch (error) {
      toast(error instanceof Error ? error.message : String(error), 'error');
    }
  }

  function addTaskFromResult() {
    const task = activeResult.workbenchTask;
    if (!task) return;
    addWorkbenchTask({
      pageKey,
      title: task.title,
      href: task.href,
      kind: task.kind,
      payload: task.payload,
    });
    toast('已写入工作台任务', 'success');
  }

  function addTaskAndJump() {
    addTaskFromResult();
    router.push(resolveWorkbenchJumpHref(pageKey, activeResult, mergedLinks));
  }

  return (
    <SectionCard className={`mt-0 p-4 sm:p-5 ${className}`}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="eyebrow">Result Workbench</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">{title}</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{activeResult.summary}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {activeResult.status === 'degraded' || activeResult.status === 'unavailable' ? (
              <Badge variant="warning">{activeResult.status === 'unavailable' ? '服务不可用' : '降级结果'}</Badge>
            ) : null}
            {activeResult.platformMeta?.sourceTool ? <Badge variant="info">{activeResult.platformMeta.sourceTool}</Badge> : null}
            {activeResult.platformMeta?.degraded ? <Badge variant="warning">降级结果</Badge> : null}
            {activeResult.freshness?.updatedAt ? (
              <FreshnessTag
                updatedAt={activeResult.freshness.updatedAt}
                label={activeResult.freshness.label ?? activeResult.platformMeta?.freshnessLabel ?? undefined}
                source={activeResult.platformMeta?.sourceTool ?? undefined}
              />
            ) : null}
          </div>
        </div>

        {views.length > 1 ? (
          <TabBar
            tabs={views.map((view) => ({
              key: view,
              label:
                view === 'summary'
                  ? '摘要'
                  : view === 'compare'
                    ? '对比'
                    : view === 'visual'
                      ? '可视化'
                      : '下一步',
            }))}
            active={resolvedActiveView}
            onChange={setActiveView}
          />
        ) : null}

        {resolvedActiveView === 'summary' ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(260px,0.85fr)]">
            <div className="space-y-4">
              {activeResult.evidence?.length ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {activeResult.evidence.map((item) => (
                    <div key={`${item.label}:${item.value}`} className="metric-tile rounded-[22px] p-4">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                        {item.label}
                      </div>
                      <div className="mt-3 text-sm font-semibold text-text-primary">{item.value}</div>
                    </div>
                  ))}
                </div>
              ) : null}

              {activeResult.riskNotes?.length ? (
                <div className="rounded-[22px] border border-warning/20 bg-warning/6 p-4">
                  <div className="text-sm font-semibold text-text-primary">风险与注意事项</div>
                  <div className="mt-3 flex flex-col gap-2">
                    {activeResult.riskNotes.map((note) => (
                      <div key={note} className="text-sm leading-6 text-text-secondary">
                        {note}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {activeResult.emptyState || activeResult.degradedState ? (
                <div className="rounded-[22px] border border-white/60 bg-white/24 p-4">
                  <div className="text-sm font-semibold text-text-primary">
                    {(activeResult.status === 'degraded' || activeResult.platformMeta?.degraded)
                      ? (activeResult.degradedState?.title ?? '当前页面已进入降级态')
                      : (activeResult.emptyState?.title ?? '当前页面仍在等待输入')}
                  </div>
                  <div className="mt-2 text-sm leading-6 text-text-secondary">
                    {(activeResult.status === 'degraded' || activeResult.platformMeta?.degraded)
                      ? (activeResult.degradedState?.description ?? '请先处理页面级降级原因，再继续解读下方结果。')
                      : (activeResult.emptyState?.description ?? '请先补齐关键输入，再继续执行。')}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="space-y-3">
              <div className="rounded-[22px] border border-white/60 bg-white/28 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">平台信息</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {activeResult.platformMeta?.sourceChain?.map((item) => (
                    <Badge key={item} variant="neutral">
                      {item}
                    </Badge>
                  ))}
                  {activeResult.freshness?.asOf ? <Badge variant="neutral">as of {activeResult.freshness.asOf}</Badge> : null}
                </div>
                {activeResult.platformMeta?.fallbackReason?.length ? (
                  <div className="mt-3 flex flex-col gap-2">
                    {activeResult.platformMeta.fallbackReason.map((reason) => (
                      <div key={reason} className="text-xs leading-6 text-text-secondary">
                        {reason}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-3 text-xs leading-6 text-text-secondary">当前结果未报告 fallback 或降级原因。</div>
                )}
                {activeResult.platformMeta?.referencePath ? (
                  <div className="mt-4">
                    <Link href={activeResult.platformMeta.referencePath} className={LINK_CHIP_CLS}>
                      查看数据说明
                    </Link>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {resolvedActiveView === 'compare' ? <div>{compareContent}</div> : null}
        {resolvedActiveView === 'visual' ? <div>{visualContent}</div> : null}

        {resolvedActiveView === 'next_step' ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-3">
              <div className="text-sm font-semibold text-text-primary">可执行动作</div>
              {nextSteps.length ? (
                <div className="rounded-[22px] border border-white/60 bg-white/24 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
                  <div className="mt-3 flex flex-col gap-2">
                    {nextSteps.map((step) => (
                      <div key={step} className="text-sm leading-6 text-text-secondary">
                        {step}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {mergedActions.length ? (
                mergedActions.map((action) => (
                  <button
                    key={`${action.actionId ?? action.id}:${action.label}`}
                    type="button"
                    onClick={() => {
                      void runAction(action);
                    }}
                    className={ACTION_CARD_CLS}
                  >
                    <div className="text-sm font-semibold text-text-primary">{action.label}</div>
                    {action.description ? (
                      <div className="mt-2 text-xs leading-6 text-text-secondary">{action.description}</div>
                    ) : null}
                  </button>
                ))
              ) : (
                <div className="rounded-[22px] border border-dashed border-white/60 bg-white/18 px-4 py-4 text-sm text-text-secondary">
                  当前结果没有额外动作，建议直接使用下面的跳转入口继续研究。
                </div>
              )}

              {activeResult.workbenchTask ? (
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={addTaskFromResult} className={ACTION_CHIP_CLS}>
                    写入工作台任务
                  </button>
                  <button type="button" onClick={addTaskAndJump} className={ACTION_CHIP_CLS}>
                    写入工作台并跳转
                  </button>
                </div>
              ) : null}
            </div>

            <div className="space-y-4">
              <div>
                <div className="text-sm font-semibold text-text-primary">推荐跳转</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {mergedLinks.map((link) => (
                    <Link key={`${link.href}:${link.label}`} href={link.href} className={LINK_CHIP_CLS}>
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>

              {resolvedSkills.length ? (
                <div>
                  <div className="text-sm font-semibold text-text-primary">推荐技能</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {resolvedSkills.map((skill) => (
                      <Link
                        key={`${skill.resolvedSkillId}:${skill.resolvedLabel}`}
                        href={`/skills?skill=${encodeURIComponent(skill.resolvedSkillId)}`}
                        className={LINK_CHIP_CLS}
                      >
                        {skill.resolvedLabel}
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}

              {activeResult.strategySuggestions?.length ? (
                <div>
                  <div className="text-sm font-semibold text-text-primary">推荐策略后续</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {activeResult.strategySuggestions.map((item) => (
                      <Link key={item.id} href={buildStrategyHref(pageKey, item)} className={LINK_CHIP_CLS}>
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}
