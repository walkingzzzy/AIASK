import type {
  ResultAction,
  ResultContract,
  ResultEvidenceItem,
  ResultFreshness,
  ResultLink,
  ResultPlatformMeta,
  ResultView,
  ResultWorkbenchTask,
} from '@aiask/shared-types';
import type { PageActionDefinition } from '@/lib/page-action-bus';
import type { WorkspacePageKey } from '@/store/workbench-store';

type LocalResultContractInput = {
  summary: string;
  availableViews?: ResultView[];
  pageActions?: PageActionDefinition[];
  preferredActionIds?: string[];
  recommendedLinks?: ResultLink[];
  evidence?: ResultEvidenceItem[];
  riskNotes?: string[];
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

export function buildLocalResultContract(input: LocalResultContractInput): ResultContract {
  const availableViews = Array.from(
    new Set<ResultView>(['summary', ...(input.availableViews ?? []), 'next_step']),
  );
  return {
    summary: input.summary,
    availableViews,
    recommendedActions: pageActionsToResultActions(input.pageActions ?? [], input.preferredActionIds),
    recommendedLinks: uniqueByKey(input.recommendedLinks ?? [], (item) => `${item.href}:${item.label}`),
    evidence: uniqueByKey(input.evidence ?? [], (item) => `${item.label}:${item.value}`),
    riskNotes: uniqueByKey((input.riskNotes ?? []).filter(Boolean), (item) => item),
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
    availableViews: Array.from(
      new Set<ResultView>([
        ...((server.availableViews as ResultView[] | undefined) ?? []),
        ...localFallback.availableViews,
      ]),
    ),
    recommendedActions: uniqueByKey(
      [...(server.recommendedActions ?? []), ...(localFallback.recommendedActions ?? [])],
      (item) => `${item.actionId ?? item.id}:${item.label}`,
    ),
    recommendedLinks: uniqueByKey(
      [...(server.recommendedLinks ?? []), ...(localFallback.recommendedLinks ?? [])],
      (item) => `${item.href}:${item.label}`,
    ),
    evidence: uniqueByKey(
      [...(server.evidence ?? []), ...(localFallback.evidence ?? [])],
      (item) => `${item.label}:${item.value}`,
    ),
    riskNotes: uniqueByKey(
      [...(server.riskNotes ?? []), ...(localFallback.riskNotes ?? [])].filter(Boolean),
      (item) => item,
    ),
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
