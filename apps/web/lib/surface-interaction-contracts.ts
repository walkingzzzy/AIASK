import surfaceCatalog from '@/e2e/realworld/catalog.json';
import { getMutationRefreshContract, type FrontendDataEffect } from '@/lib/data-effects';

type SurfaceMutationMode = 'none' | 'transient' | 'persistent' | 'destructive';
type SurfaceEmptyStatePolicy = 'allow-empty' | 'seed-required' | 'error-state-required';

type CatalogSurfaceEntry = {
  surfaceId: string;
  label: string;
  route: string;
  family: string;
  proofMode: string;
  mutationMode: SurfaceMutationMode;
  readProofRequired: boolean;
  writeProofRequired: boolean;
  emptyStatePolicy: SurfaceEmptyStatePolicy;
  scenarioSet: readonly string[];
  seedDependencies: readonly string[];
  cleanupStrategy: string;
  mutationRisk: 'none' | 'low' | 'medium' | 'high';
  artifactKey: string;
  budgetClass: string;
};

export type DependentDisplayProof = {
  effect?: FrontendDataEffect;
  actionName?: string;
  triggerApi?: string;
  affectedSurfaces: readonly string[];
  domRegions: readonly string[];
  expectedFields: readonly string[];
};

export type SurfaceWriteActionContract = {
  actionName: string;
  triggerApi: string;
  effect?: FrontendDataEffect;
  affectedSurfaces: readonly string[];
  affectedDomRegions: readonly string[];
  expectedFields: readonly string[];
};

export type SurfaceInteractionContract = {
  surfaceId: string;
  label: string;
  route: string;
  family: string;
  proofMode: string;
  mutationMode: SurfaceMutationMode;
  readProofRequired: boolean;
  writeProofRequired: boolean;
  emptyStatePolicy: SurfaceEmptyStatePolicy;
  scenarioSet: readonly string[];
  seedDependencies: readonly string[];
  cleanupStrategy: string;
  artifactKey: string;
  readProof: readonly string[];
  sourceProof: readonly string[];
  dependencyProofs: readonly DependentDisplayProof[];
  staleProof: readonly string[];
  writeActions: readonly SurfaceWriteActionContract[];
};

const typedSurfaceCatalog = surfaceCatalog as readonly CatalogSurfaceEntry[];

function dedupe(values: readonly string[]) {
  return values.filter((value, index, list) => list.indexOf(value) === index);
}

function effectWriteAction(
  actionName: string,
  triggerApi: string,
  effect: FrontendDataEffect,
): SurfaceWriteActionContract {
  const contract = getMutationRefreshContract(effect);
  return {
    actionName,
    triggerApi,
    effect,
    affectedSurfaces: contract.affectedSurfaces,
    affectedDomRegions: contract.affectedDomRegions,
    expectedFields: contract.expectedFields,
  };
}

function writeAction(
  actionName: string,
  triggerApi: string,
  affectedSurfaces: readonly string[],
  affectedDomRegions: readonly string[],
  expectedFields: readonly string[],
): SurfaceWriteActionContract {
  return {
    actionName,
    triggerApi,
    affectedSurfaces,
    affectedDomRegions,
    expectedFields,
  };
}

const SURFACE_WRITE_ACTIONS: Partial<Record<string, readonly SurfaceWriteActionContract[]>> = {
  'admin-cache': [
    writeAction(
      '清理缓存前缀',
      'POST /admin/cache/clear',
      ['admin-cache', 'admin', 'admin-dead-letters'],
      ['cache summary', 'clear receipt', 'admin overview cards'],
      ['clearedCount', 'cache backend status', 'queue snapshot'],
    ),
  ],
  'admin-dead-letters': [
    writeAction(
      '重试死信任务',
      'POST /admin/dead-letters/:id/retry',
      ['admin-dead-letters', 'admin'],
      ['dead-letter table', 'retry receipt', 'overview badges'],
      ['row status', 'retry count', 'queue size'],
    ),
    writeAction(
      '清空死信队列',
      'POST /admin/dead-letters/clear',
      ['admin-dead-letters', 'admin'],
      ['dead-letter table', 'clear receipt', 'overview badges'],
      ['queue size', 'cleared count', 'latest processed timestamp'],
    ),
  ],
  alerts: [
    effectWriteAction('创建告警规则', 'POST /alerts/create', 'alerts.changed'),
    effectWriteAction('删除告警规则', 'DELETE /alerts/delete?alertId=:id', 'alerts.changed'),
  ],
  events: [
    writeAction(
      '订阅事件标的',
      'POST /event/subscribe',
      ['events', 'stock', 'research'],
      ['subscription summary', 'event timeline', 'focus code badge'],
      ['subscribed flag', 'subscription count', 'important event rows'],
    ),
    writeAction(
      '取消订阅事件标的',
      'POST /event/unsubscribe',
      ['events', 'stock', 'research'],
      ['subscription summary', 'event timeline', 'focus code badge'],
      ['subscribed flag', 'subscription count', 'important event rows'],
    ),
  ],
  execution: [
    effectWriteAction('提交执行路由', 'POST /paper-trading/route-execution', 'execution.changed'),
    effectWriteAction('同步真实订单事件', 'POST /execution/live/orders/:orderId/sync', 'execution.changed'),
    effectWriteAction('撤销真实订单', 'POST /execution/live/orders/:orderId/cancel', 'execution.changed'),
  ],
  notifications: [
    effectWriteAction('标记通知已读', 'POST /notifications/mark-read', 'notifications.changed'),
    effectWriteAction('全部标记已读', 'POST /notifications/mark-all-read', 'notifications.changed'),
    effectWriteAction('删除通知', 'DELETE /notifications/delete', 'notifications.changed'),
  ],
  'paper-trading': [
    effectWriteAction('刷新模拟盘价格', 'POST /paper-trading/update-prices', 'paper-trading.changed'),
    effectWriteAction('下达模拟订单', 'POST /paper-trading/order', 'paper-trading.changed'),
    effectWriteAction('撤销模拟订单', 'POST /paper-trading/cancel', 'paper-trading.changed'),
    effectWriteAction('校准账本', 'POST /paper-trading/reconcile', 'paper-trading.changed'),
  ],
  portfolio: [
    effectWriteAction('创建组合', 'POST /portfolio/create', 'portfolio.changed'),
    effectWriteAction('添加持仓', 'POST /portfolio/add-holding', 'portfolio.changed'),
    effectWriteAction('删除组合', 'DELETE /portfolio/delete?portfolioId=:id', 'portfolio.changed'),
  ],
  settings: [
    effectWriteAction('更新资料与偏好', 'POST /auth/profile', 'auth.profile.updated'),
    effectWriteAction('吊销安全会话', 'POST /auth/sessions/revoke', 'auth.sessions.changed'),
  ],
  'settings-security': [
    effectWriteAction('启用双重验证', 'POST /auth/2fa/verify', 'auth.security.updated'),
    effectWriteAction('禁用双重验证', 'POST /auth/2fa/disable', 'auth.security.updated'),
    effectWriteAction('切换交易确认偏好', 'POST /auth/profile', 'auth.security.updated'),
  ],
  'strategy-detail': [
    effectWriteAction('收藏或取消收藏策略', 'POST|DELETE /strategy-market/:id/favorite', 'strategy.changed'),
    effectWriteAction('更新个人策略', 'PATCH /strategy-market/:id', 'strategy.changed'),
    effectWriteAction('复制策略到个人空间', 'POST /strategy-market/:id/fork', 'strategy.changed'),
    effectWriteAction('删除个人策略', 'DELETE /strategy-market/:id', 'strategy.changed'),
    effectWriteAction('创建模拟盘上下文', 'POST /strategy-market/:id/paper-session', 'strategy.changed'),
  ],
  'strategy-market': [
    effectWriteAction('收藏或取消收藏策略', 'POST|DELETE /strategy-market/:id/favorite', 'strategy.changed'),
    effectWriteAction('创建个人策略', 'POST /strategy-market/create', 'strategy.changed'),
    effectWriteAction('删除个人策略', 'DELETE /strategy-market/:id', 'strategy.changed'),
  ],
  user: [
    effectWriteAction('更新用户风险偏好', 'POST /auth/profile', 'auth.profile.updated'),
  ],
  watchlist: [
    effectWriteAction('创建或删除自选分组', 'local watchlist store mutation', 'watchlist.changed'),
    effectWriteAction('增删自选股票', 'local watchlist store mutation', 'watchlist.changed'),
  ],
};

function buildReadProof(entry: CatalogSurfaceEntry): readonly string[] {
  const proofs = [`${entry.label}主数据区可见并完成首屏渲染`];

  if (entry.proofMode === 'route-read') {
    proofs.push('公共路由表单与主 CTA 可见');
  } else if (entry.budgetClass === 'table') {
    proofs.push('表格或列表主体渲染稳定');
  } else if (entry.budgetClass === 'workspace') {
    proofs.push('工作区主面板与上下文摘要渲染稳定');
  } else {
    proofs.push('摘要区、主卡片或结果区渲染稳定');
  }

  if (entry.scenarioSet.includes('workflow')) {
    proofs.push('关键工作流入口与结果区同时可见');
  }

  if (entry.emptyStatePolicy === 'allow-empty') {
    proofs.push('空结果时显示明确空态，而不是成功壳子里的旧值');
  }
  if (entry.emptyStatePolicy === 'seed-required') {
    proofs.push('缺少 seed 时显示缺口说明，不冒充成功态');
  }
  if (entry.emptyStatePolicy === 'error-state-required') {
    proofs.push('阻断性错误时显示错误态，而不是空壳成功态');
  }

  return dedupe(proofs);
}

function buildSourceProof(entry: CatalogSurfaceEntry): readonly string[] {
  if (entry.mutationMode === 'none') {
    return dedupe([
      '切换筛选、参数、分页或标签后，当前视图立即反映新的数据集合',
      '局部交互结束后，当前页不保留上一次实体或查询条件的旧值',
    ]);
  }

  if (entry.mutationMode === 'transient') {
    return dedupe([
      '本页主要交互完成后，主摘要区和结果区立即刷新',
      '工作流提交、运行或确认后，当前页能显示新的状态、计数或结果回执',
    ]);
  }

  if (entry.mutationMode === 'destructive') {
    return dedupe([
      '危险操作必须先确认，再更新本页主列表、摘要和回执区',
      '删除或清空后，本页不会继续展示已移除实体或旧计数',
    ]);
  }

  return dedupe([
    '写操作完成后，本页主列表、摘要卡、badge 和详情区会立即更新',
    '成功回执出现后，无需手动刷新即可看到最终状态和数字变化',
  ]);
}

function buildStaleProof(entry: CatalogSurfaceEntry): readonly string[] {
  const proofs = [
    '切换实体、路由参数或工作区上下文后，不残留上一实体的摘要、表格或 badge',
    '空集合显示明确 0 或空态，不混用 - 和旧数字',
  ];

  if (entry.emptyStatePolicy === 'seed-required') {
    proofs.push('seed 缺失时只显示缺口说明，不复用历史成功数据');
  }
  if (entry.mutationMode === 'persistent' || entry.mutationMode === 'destructive') {
    proofs.push('写操作回退或删除后，源页与关联页都不再显示旧实体或旧计数');
  }

  return dedupe(proofs);
}

function buildDependencyProofs(actions: readonly SurfaceWriteActionContract[]): readonly DependentDisplayProof[] {
  return actions.map((action) => ({
    effect: action.effect,
    actionName: action.actionName,
    triggerApi: action.triggerApi,
    affectedSurfaces: action.affectedSurfaces,
    domRegions: action.affectedDomRegions,
    expectedFields: action.expectedFields,
  }));
}

function buildContract(entry: CatalogSurfaceEntry): SurfaceInteractionContract {
  const writeActions = SURFACE_WRITE_ACTIONS[entry.surfaceId] ?? [];

  return {
    surfaceId: entry.surfaceId,
    label: entry.label,
    route: entry.route,
    family: entry.family,
    proofMode: entry.proofMode,
    mutationMode: entry.mutationMode,
    readProofRequired: entry.readProofRequired,
    writeProofRequired: entry.writeProofRequired,
    emptyStatePolicy: entry.emptyStatePolicy,
    scenarioSet: entry.scenarioSet,
    seedDependencies: entry.seedDependencies,
    cleanupStrategy: entry.cleanupStrategy,
    artifactKey: entry.artifactKey,
    readProof: buildReadProof(entry),
    sourceProof: buildSourceProof(entry),
    dependencyProofs: buildDependencyProofs(writeActions),
    staleProof: buildStaleProof(entry),
    writeActions,
  };
}

export const surfaceInteractionContracts: Record<string, SurfaceInteractionContract> = Object.fromEntries(
  typedSurfaceCatalog.map((entry) => [entry.surfaceId, buildContract(entry)]),
);

export function getSurfaceInteractionContract(surfaceId: string) {
  return surfaceInteractionContracts[surfaceId] ?? null;
}
