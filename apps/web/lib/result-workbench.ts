import type {
  ResultAction,
  ResultContract,
  ResultEvidenceItem,
  ResultFreshness,
  ResultLink,
  ResultPlatformMeta,
  ResultStateBlock,
  ResultStatus,
  ResultView,
  ResultWorkbenchTask,
} from '@aiask/shared-types';
import type { PageActionDefinition } from '@/lib/page-action-bus';
import type { WorkspacePageKey } from '@/store/workbench-store';

type LocalResultContractInput = {
  summary: string;
  status?: ResultStatus;
  availableViews?: ResultView[];
  pageActions?: PageActionDefinition[];
  preferredActionIds?: string[];
  primaryAction?: ResultAction | null;
  secondaryActions?: ResultAction[];
  recommendedLinks?: ResultLink[];
  recommendedNextActions?: string[];
  evidence?: ResultEvidenceItem[];
  riskNotes?: string[];
  emptyState?: ResultStateBlock | null;
  degradedState?: ResultStateBlock | null;
  freshness?: ResultFreshness | null;
  platformMeta?: ResultPlatformMeta | null;
  workbenchTask?: ResultWorkbenchTask | null;
};

function uniqueByKey<T>(items: T[], keyFn: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyFn(item);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function pageActionsToResultActions(
  actions: PageActionDefinition[],
  preferredActionIds: string[] = [],
  limit = 4,
): ResultAction[] {
  const order = preferredActionIds.length
    ? [
        ...preferredActionIds
          .map((id) => actions.find((action) => action.id === id))
          .filter((action): action is PageActionDefinition => Boolean(action)),
        ...actions.filter((action) => !preferredActionIds.includes(action.id)),
      ]
    : actions;
  return uniqueByKey(
    order
      .filter((action) => action.exposeToCopilot !== false)
      .slice(0, limit)
      .map((action) => ({
        id: action.id,
        actionId: action.id,
        label: action.label,
        description: action.description,
      })),
    (item) => `${item.actionId ?? item.id}:${item.label}`,
  );
}

export function evidenceToSummary(evidence: ResultEvidenceItem[] = [], limit = 5) {
  return evidence
    .slice(0, limit)
    .map((item) => `${item.label}：${item.value}`)
    .filter(Boolean);
}

export function defaultWorkbenchTask(
  pageKey: WorkspacePageKey,
  title: string,
  href: string,
  kind?: string,
  payload?: Record<string, unknown>,
): ResultWorkbenchTask {
  return {
    title,
    href,
    kind: kind ?? `${pageKey}-review`,
    payload,
  };
}

function uniqueStrings(items: string[] = []) {
  return uniqueByKey(items.filter(Boolean), (item) => item);
}

export function buildLocalResultContract(input: LocalResultContractInput): ResultContract {
  const availableViews = Array.from(
    new Set<ResultView>(['summary', ...(input.availableViews ?? []), 'next_step']),
  );
  const pageResultActions = pageActionsToResultActions(input.pageActions ?? [], input.preferredActionIds);
  const primaryAction = input.primaryAction ?? pageResultActions[0] ?? null;
  const secondaryActions = uniqueByKey(
    [
      ...(input.secondaryActions ?? []),
      ...pageResultActions.filter((action) => action.actionId !== primaryAction?.actionId),
    ],
    (item) => `${item.actionId ?? item.id}:${item.label}`,
  );
  const recommendedActions = uniqueByKey(
    [...(primaryAction ? [primaryAction] : []), ...secondaryActions],
    (item) => `${item.actionId ?? item.id}:${item.label}`,
  );
  return {
    summary: input.summary,
    status: input.status ?? (input.platformMeta?.degraded ? 'degraded' : 'ready'),
    availableViews,
    primaryAction,
    secondaryActions,
    recommendedActions,
    recommendedLinks: uniqueByKey(input.recommendedLinks ?? [], (item) => `${item.href}:${item.label}`),
    recommendedNextActions: uniqueStrings(input.recommendedNextActions),
    evidence: uniqueByKey(input.evidence ?? [], (item) => `${item.label}:${item.value}`),
    riskNotes: uniqueByKey((input.riskNotes ?? []).filter(Boolean), (item) => item),
    emptyState: input.emptyState ?? null,
    degradedState: input.degradedState ?? null,
    freshness: input.freshness ?? null,
    platformMeta: input.platformMeta ?? null,
    workbenchTask: input.workbenchTask ?? null,
  };
}

function asResultContract(value: unknown): Partial<ResultContract> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Partial<ResultContract>;
}

export function resolveResultContract(
  serverContract: unknown,
  localFallback: ResultContract,
): ResultContract {
  const server = asResultContract(serverContract);
  if (!server) return localFallback;

  return {
    summary:
      typeof server.summary === 'string' && server.summary.trim()
        ? server.summary
        : localFallback.summary,
    status: server.status ?? localFallback.status ?? 'ready',
    availableViews: Array.from(
      new Set<ResultView>([
        ...((server.availableViews as ResultView[] | undefined) ?? []),
        ...localFallback.availableViews,
      ]),
    ),
    primaryAction: server.primaryAction ?? localFallback.primaryAction ?? null,
    secondaryActions: uniqueByKey(
      [...(server.secondaryActions ?? []), ...(localFallback.secondaryActions ?? [])],
      (item) => `${item.actionId ?? item.id}:${item.label}`,
    ),
    recommendedActions: uniqueByKey(
      [...(server.recommendedActions ?? []), ...(localFallback.recommendedActions ?? [])],
      (item) => `${item.actionId ?? item.id}:${item.label}`,
    ),
    recommendedLinks: uniqueByKey(
      [...(server.recommendedLinks ?? []), ...(localFallback.recommendedLinks ?? [])],
      (item) => `${item.href}:${item.label}`,
    ),
    recommendedNextActions: uniqueStrings([
      ...(server.recommendedNextActions ?? []),
      ...(localFallback.recommendedNextActions ?? []),
    ]),
    evidence: uniqueByKey(
      [...(server.evidence ?? []), ...(localFallback.evidence ?? [])],
      (item) => `${item.label}:${item.value}`,
    ),
    riskNotes: uniqueByKey(
      [...(server.riskNotes ?? []), ...(localFallback.riskNotes ?? [])].filter(Boolean),
      (item) => item,
    ),
    emptyState: server.emptyState ?? localFallback.emptyState ?? null,
    degradedState: server.degradedState ?? localFallback.degradedState ?? null,
    freshness: server.freshness ?? localFallback.freshness ?? null,
    platformMeta: server.platformMeta ?? localFallback.platformMeta ?? null,
    skillSuggestions: uniqueByKey(
      [...(server.skillSuggestions ?? []), ...(localFallback.skillSuggestions ?? [])],
      (item) => `${item.skillId}:${item.label ?? ''}`,
    ),
    strategySuggestions: uniqueByKey(
      [...(server.strategySuggestions ?? []), ...(localFallback.strategySuggestions ?? [])],
      (item) => `${item.id}:${item.href ?? ''}`,
    ),
    workbenchTask: server.workbenchTask ?? localFallback.workbenchTask ?? null,
  };
}
