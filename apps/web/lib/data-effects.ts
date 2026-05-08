import { apiKeys } from '@/lib/query-keys';

export const DATA_EFFECT_EVENT_PREFIX = 'aiask:data-effect:';
export const DATA_EFFECT_BROADCAST_EVENT = 'aiask:data-effect';

export type FrontendDataEffect =
  | 'alerts.changed'
  | 'auth.profile.updated'
  | 'auth.security.updated'
  | 'auth.sessions.changed'
  | 'execution.changed'
  | 'notifications.changed'
  | 'paper-trading.changed'
  | 'portfolio.changed'
  | 'strategy.changed'
  | 'watchlist.changed';

export type MutationRefreshContract = {
  effect: FrontendDataEffect;
  description: string;
  queryKeys: ReadonlyArray<readonly unknown[]>;
  affectedSurfaces: readonly string[];
  affectedDomRegions: readonly string[];
  expectedFields: readonly string[];
};

export type FrontendDataEffectDetail = {
  effect: FrontendDataEffect;
  path?: string;
  data?: unknown;
};

const DATA_EFFECT_CONTRACTS: Record<FrontendDataEffect, MutationRefreshContract> = {
  'alerts.changed': {
    effect: 'alerts.changed',
    description: '告警规则变更后，告警列表、首页摘要和相关通知入口应刷新。',
    queryKeys: [apiKeys.alerts()],
    affectedSurfaces: ['alerts', 'home'],
    affectedDomRegions: ['alerts-list', 'home-alert-summary'],
    expectedFields: ['rule count', 'latest alert status'],
  },
  'auth.profile.updated': {
    effect: 'auth.profile.updated',
    description: '用户资料或偏好修改后，资料页、设置页、首页和用户态导航应同步。',
    queryKeys: [apiKeys.auth()],
    affectedSurfaces: ['settings', 'settings-security', 'user', 'home'],
    affectedDomRegions: ['profile form', 'header user summary', 'dashboard preferences'],
    expectedFields: ['nickname', 'riskLevel', 'avatarUrl', 'preferences'],
  },
  'auth.security.updated': {
    effect: 'auth.security.updated',
    description: '安全设置变更后，2FA 状态与用户偏好应刷新。',
    queryKeys: [apiKeys.auth()],
    affectedSurfaces: ['settings-security', 'settings', 'user'],
    affectedDomRegions: ['2fa status', 'transaction confirmation toggles'],
    expectedFields: ['totpEnabled', 'transactionConfirmations'],
  },
  'auth.sessions.changed': {
    effect: 'auth.sessions.changed',
    description: '会话吊销后，安全页会话列表与相关状态应刷新。',
    queryKeys: [apiKeys.auth(), apiKeys.audit()],
    affectedSurfaces: ['settings', 'settings-audit-log'],
    affectedDomRegions: ['session list', 'audit log'],
    expectedFields: ['active sessions', 'audit entries'],
  },
  'execution.changed': {
    effect: 'execution.changed',
    description: '执行路由或回执变更后，执行、模拟盘、绩效与风控链路应同步。',
    queryKeys: [apiKeys.execution(), apiKeys.paper(), apiKeys.risk()],
    affectedSurfaces: ['execution', 'paper-trading', 'performance', 'risk', 'home'],
    affectedDomRegions: ['execution tasks', 'pending orders', 'performance summary', 'risk summary'],
    expectedFields: ['executionId', 'artifactId', 'pending orders', 'risk metrics'],
  },
  'notifications.changed': {
    effect: 'notifications.changed',
    description: '通知读写后，通知页与铃铛未读角标应同步。',
    queryKeys: [apiKeys.notifications()],
    affectedSurfaces: ['notifications', 'global-bell'],
    affectedDomRegions: ['notification list', 'notification bell'],
    expectedFields: ['unread count', 'read state', 'visible rows'],
  },
  'paper-trading.changed': {
    effect: 'paper-trading.changed',
    description: '模拟盘写操作后，资产、持仓、绩效、风控和执行概览应同步。',
    queryKeys: [apiKeys.paper(), apiKeys.execution(), apiKeys.risk()],
    affectedSurfaces: ['paper-trading', 'performance', 'risk', 'execution', 'home'],
    affectedDomRegions: ['summary cards', 'positions', 'performance chart', 'risk cards'],
    expectedFields: ['total value', 'nav history', 'pending orders', 'trust status'],
  },
  'portfolio.changed': {
    effect: 'portfolio.changed',
    description: '组合结构变更后，组合、绩效、风控和首页组合摘要应同步。',
    queryKeys: [apiKeys.portfolio(), apiKeys.risk()],
    affectedSurfaces: ['portfolio', 'performance', 'risk', 'home', 'strategy-market'],
    affectedDomRegions: ['portfolio list', 'portfolio detail', 'performance attribution', 'risk summary'],
    expectedFields: ['portfolio count', 'holdings', 'attribution', 'risk metrics'],
  },
  'strategy.changed': {
    effect: 'strategy.changed',
    description: '策略收藏、创建、运行或删除后，策略、组合和模拟盘入口应同步。',
    queryKeys: [apiKeys.strategy(), apiKeys.portfolio(), apiKeys.paper()],
    affectedSurfaces: ['strategy-market', 'strategy-detail', 'portfolio', 'paper-trading'],
    affectedDomRegions: ['strategy list', 'strategy detail', 'portfolio cart', 'linked strategy context'],
    expectedFields: ['favorite state', 'strategy count', 'linked account context'],
  },
  'watchlist.changed': {
    effect: 'watchlist.changed',
    description: '自选股变更后，自选列表、首页摘要和引用自选的页面应同步。',
    queryKeys: [],
    affectedSurfaces: ['watchlist', 'market', 'stock', 'home'],
    affectedDomRegions: ['watchlist groups', 'watchlist badge', 'recent watchlist summary'],
    expectedFields: ['group count', 'item count', 'star state'],
  },
};

export function getMutationRefreshContract(effect: FrontendDataEffect): MutationRefreshContract {
  return DATA_EFFECT_CONTRACTS[effect];
}

export function getMutationRefreshContracts(
  effects: readonly FrontendDataEffect[] | undefined,
): MutationRefreshContract[] {
  if (!effects?.length) return [];
  const seen = new Set<FrontendDataEffect>();
  return effects.filter((effect) => {
    if (seen.has(effect)) return false;
    seen.add(effect);
    return true;
  }).map((effect) => getMutationRefreshContract(effect));
}

export function getInvalidateKeysForEffects(effects: readonly FrontendDataEffect[] | undefined): Array<readonly unknown[]> {
  return getMutationRefreshContracts(effects).flatMap((contract) => contract.queryKeys);
}

export function getDataEffectEventName(effect: FrontendDataEffect) {
  return `${DATA_EFFECT_EVENT_PREFIX}${effect}`;
}

export function dispatchFrontendDataEffects(
  effects: readonly FrontendDataEffect[] | undefined,
  buildDetail?: (effect: FrontendDataEffect) => FrontendDataEffectDetail,
) {
  if (typeof window === 'undefined' || !effects?.length) return;
  const seen = new Set<FrontendDataEffect>();
  for (const effect of effects) {
    if (seen.has(effect)) continue;
    seen.add(effect);
    const detail = buildDetail ? buildDetail(effect) : { effect };
    window.dispatchEvent(new CustomEvent(DATA_EFFECT_BROADCAST_EVENT, { detail }));
    window.dispatchEvent(new CustomEvent(getDataEffectEventName(effect), { detail }));
  }
}
