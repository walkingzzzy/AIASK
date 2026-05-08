import type { CopilotFrontendContext, CopilotPageContext, CopilotSurfaceRoute, CopilotTaskFlow } from './copilot-types';
import {
  COPILOT_SURFACE_MODULES,
  COPILOT_SURFACE_ROUTES,
  COPILOT_TASK_FLOWS,
  getCopilotSurfaceByPageKey,
  getCopilotSurfaceByPath,
} from './copilot-surface-registry';
import { normalizeStockCode, trustedUserStockCode } from './stock-code-utils';

type WorkspaceContextLike = {
  stockCode?: string | null;
  stockConfirmedAt?: string | null;
  sourcePage?: string | null;
  taskType?: string | null;
  resultType?: string | null;
};

type WorkspaceLike = {
  id?: string;
  name?: string;
  context?: WorkspaceContextLike;
};

type BuildFrontendContextInput = {
  pathname: string;
  search?: string;
  pageContext?: CopilotPageContext | null;
  activeWorkspace?: WorkspaceLike | null;
};

function trimArray(values: string[] | undefined, limit: number) {
  return (values ?? []).filter(Boolean).slice(0, limit);
}

function compactSurface(route: CopilotSurfaceRoute): CopilotSurfaceRoute {
  return {
    pageKey: route.pageKey,
    path: route.path,
    module: route.module,
    title: route.title,
    summary: route.summary,
    primaryGoal: route.primaryGoal,
    requiredInputs: trimArray(route.requiredInputs, 5),
    coreEntities: trimArray(route.coreEntities, 6),
    dataSources: trimArray(route.dataSources, 6),
    capabilities: trimArray(route.capabilities, 6),
    commonQuestions: trimArray(route.commonQuestions, 5),
    relatedPageKeys: trimArray(route.relatedPageKeys, 8),
    aliases: trimArray(route.aliases, 8),
    stockAware: route.stockAware,
    codeParam: route.codeParam,
    adminOnly: route.adminOnly,
    public: route.public,
  };
}

function resolveCurrentRoute(pathname: string, pageContext?: CopilotPageContext | null) {
  return getCopilotSurfaceByPageKey(pageContext?.pageKey) ?? getCopilotSurfaceByPath(pathname);
}

function resolveTaskFlow(currentPageKey: string | undefined): (CopilotTaskFlow & { currentStepIndex?: number }) | undefined {
  if (!currentPageKey) return undefined;
  for (const flow of COPILOT_TASK_FLOWS) {
    const currentStepIndex = flow.steps.findIndex((step) => step.pageKey === currentPageKey);
    if (currentStepIndex >= 0) {
      return { ...flow, currentStepIndex };
    }
  }
  return undefined;
}

function collectRelatedRoutes(currentRoute: CopilotSurfaceRoute | undefined, taskFlow: (CopilotTaskFlow & { currentStepIndex?: number }) | undefined) {
  const relatedKeys = new Set<string>();
  for (const key of currentRoute?.relatedPageKeys ?? []) relatedKeys.add(key);
  if (taskFlow?.currentStepIndex != null) {
    const previous = taskFlow.steps[taskFlow.currentStepIndex - 1]?.pageKey;
    const current = taskFlow.steps[taskFlow.currentStepIndex]?.pageKey;
    const next = taskFlow.steps[taskFlow.currentStepIndex + 1]?.pageKey;
    if (previous) relatedKeys.add(previous);
    if (current) relatedKeys.add(current);
    if (next) relatedKeys.add(next);
  }
  if (currentRoute?.pageKey) relatedKeys.delete(currentRoute.pageKey);
  return Array.from(relatedKeys)
    .map((key) => getCopilotSurfaceByPageKey(key))
    .filter((route): route is CopilotSurfaceRoute => Boolean(route))
    .slice(0, 8)
    .map(compactSurface);
}

export function buildCopilotFrontendContext({
  pathname,
  search = '',
  pageContext,
  activeWorkspace,
}: BuildFrontendContextInput): CopilotFrontendContext {
  const currentRoute = resolveCurrentRoute(pathname, pageContext);
  const taskFlow = resolveTaskFlow(currentRoute?.pageKey);
  const route = `${pathname}${search}`;
  const workspaceContext = activeWorkspace?.context ?? {};
  const stockCode =
    normalizeStockCode(pageContext?.selectedCode)
    || normalizeStockCode(pageContext?.stockCode)
    || trustedUserStockCode(workspaceContext.stockCode, workspaceContext.stockConfirmedAt)
    || undefined;

  return {
    generatedAt: Date.now(),
    route,
    appMap: {
      modules: COPILOT_SURFACE_MODULES.map((module) => ({
        ...module,
        pageKeys: COPILOT_SURFACE_ROUTES
          .filter((routeItem) => routeItem.module === module.module && !routeItem.public)
          .map((routeItem) => routeItem.pageKey),
      })),
      routes: COPILOT_SURFACE_ROUTES
        .filter((routeItem) => !routeItem.public)
        .map((routeItem) => ({
          pageKey: routeItem.pageKey,
          path: routeItem.path,
          module: routeItem.module,
          title: routeItem.title,
          summary: routeItem.summary,
          aliases: trimArray(routeItem.aliases, 6),
          stockAware: routeItem.stockAware,
          adminOnly: routeItem.adminOnly,
        })),
    },
    currentRoute: currentRoute ? compactSurface(currentRoute) : undefined,
    relatedRoutes: collectRelatedRoutes(currentRoute, taskFlow),
    taskFlow,
    workspaceContext: {
      workspaceId: activeWorkspace?.id,
      workspaceName: activeWorkspace?.name,
      stockCode,
      sourcePage: workspaceContext.sourcePage ?? undefined,
      taskType: workspaceContext.taskType ?? undefined,
      resultType: workspaceContext.resultType ?? undefined,
    },
  };
}
