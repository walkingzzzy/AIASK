export const ONBOARDING_VERSION = 2;
export const ONBOARDING_SIGNAL_EVENT = 'onboarding:signal';

export type OnboardingStepId =
  | 'home'
  | 'market'
  | 'watchlist'
  | 'research'
  | 'strategy-market'
  | 'paper-trading'
  | 'risk-performance'
  | 'ai-config'
  | 'ai-tools';

export type OnboardingStepStatus = 'todo' | 'visited' | 'done' | 'skipped';
export type OnboardingOverlayMode = 'expanded' | 'minimized' | 'hidden';
export type OnboardingEntrySurface = 'overview' | 'workspace' | 'utility';

export type OnboardingStepState = {
  status: OnboardingStepStatus;
  visitedAt?: string;
  completedAt?: string;
  skippedAt?: string;
};

export type OnboardingSnapshot = {
  version: number;
  overlayMode: OnboardingOverlayMode;
  currentStepId: OnboardingStepId;
  entrySurface: OnboardingEntrySurface;
  routeScope: string;
  dismissedUntil?: string;
  lastCompletedStep?: OnboardingStepId;
  updatedAt: string;
  completedAt?: string;
  steps: Record<OnboardingStepId, OnboardingStepState>;
};

export type OnboardingStepAction = {
  label: string;
  href: string;
};

export type OnboardingStepDefinition = {
  id: OnboardingStepId;
  order: number;
  group: string;
  title: string;
  description: string;
  focus: string;
  outcome: string;
  completeOnVisit?: boolean;
  actions: OnboardingStepAction[];
  matchesPath: (pathname: string) => boolean;
};

export type OnboardingSignal =
  | { type: 'paper-trading.example-loaded' }
  | { type: 'paper-trading.submitted' }
  | { type: 'ai-config.saved' };

export const ONBOARDING_STEPS: OnboardingStepDefinition[] = [
  {
    id: 'home',
    order: 1,
    group: '总览',
    title: '先认识首页和系统地图',
    description: '先把市场、研究、策略、交易、AI 五条主线放到一张图里看，避免一开始就陷进单个页面。',
    focus: '先看首页概览，再从这里决定下一步是去看盘、研究、策略还是交易。',
    outcome: '知道系统的主路径从哪里开始，以及每个模块解决什么问题。',
    completeOnVisit: true,
    actions: [
      { label: '回到首页', href: '/' },
    ],
    matchesPath: (pathname) => pathname === '/',
  },
  {
    id: 'market',
    order: 2,
    group: '看盘',
    title: '浏览行情看板',
    description: '在行情页确认指数、板块、K 线和盘口这些基础观察入口是怎么组织的。',
    focus: '先确认你会从行情页找到标的、板块和分时，再决定是否进入研究或交易。',
    outcome: '知道系统里的“第一眼行情入口”在哪里。',
    actions: [
      { label: '打开行情看板', href: '/market?from=onboarding' },
      { label: '直接看上证指数', href: '/market?code=000001&tab=index&indexCode=000001&from=onboarding' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/market'),
  },
  {
    id: 'watchlist',
    order: 3,
    group: '看盘',
    title: '建立第一组自选',
    description: '把后续要持续跟踪的股票放进观察池，自选页才会真正成为工作台而不是空壳。',
    focus: '至少把 1 只股票加入当前分组，再观察自选如何串到行情、研究和交易。',
    outcome: '拥有一个可持续复用的观察池。',
    actions: [
      { label: '打开自选股', href: '/watchlist?from=onboarding' },
      { label: '从自选去研究', href: '/watchlist?from=onboarding#management-zone' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/watchlist'),
  },
  {
    id: 'research',
    order: 4,
    group: '研究',
    title: '查看研究页',
    description: '把新闻、公告、研报和盈利预测放到一个研究工作流里看，理解系统的证据层。',
    focus: '先确认个股研究入口和新闻切换，再决定是否需要去 AI 或策略模块继续深挖。',
    outcome: '知道“结论前的证据”主要从哪里看。',
    actions: [
      { label: '打开研究页', href: '/research?from=onboarding' },
      { label: '查看市场新闻', href: '/research?from=onboarding&tab=news' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/research'),
  },
  {
    id: 'strategy-market',
    order: 5,
    group: '策略',
    title: '浏览策略超市',
    description: '策略超市负责把候选策略、工厂状态和筛选能力放在一起，是系统里的策略入口。',
    focus: '先理解策略目录、榜单和工厂概览，不要把它当成单纯列表页。',
    outcome: '知道系统如何组织策略候选与运行态。',
    actions: [
      { label: '打开策略超市', href: '/strategy-market?from=onboarding' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/strategy-market'),
  },
  {
    id: 'paper-trading',
    order: 6,
    group: '交易',
    title: '体验模拟交易',
    description: '先载入示例单或走一次下单动作，理解交易区、账户分析和活动记录如何联动。',
    focus: '建议先载入示例单，再看订单、持仓、净值和账户侧栏。',
    outcome: '知道系统里的交易路径不只是表单，而是完整账户工作台。',
    actions: [
      { label: '打开模拟交易', href: '/paper-trading?from=onboarding' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/paper-trading'),
  },
  {
    id: 'risk-performance',
    order: 7,
    group: '闭环',
    title: '查看风险和绩效闭环',
    description: '交易不是终点，还要看风险、收益和归因，这一步是系统闭环的关键。',
    focus: '先看绩效，再跳到风险页，理解从执行到复盘的完整回路。',
    outcome: '知道交易之后如何做风控与复盘。',
    actions: [
      { label: '打开绩效分析', href: '/performance?mode=account&days=30&from=onboarding' },
      { label: '查看风险总览', href: '/risk?lookbackDays=252&from=onboarding' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/performance') || pathname.startsWith('/risk'),
  },
  {
    id: 'ai-config',
    order: 8,
    group: 'AI',
    title: '配置 AI 模型',
    description: '没有模型配置，AI 中心、Copilot 和智能增强能力都无法稳定工作。',
    focus: '在设置页完成 Base URL、API Key 和模型配置，再继续体验 AI 功能。',
    outcome: '系统里的 AI 能力被真正解锁。',
    actions: [
      { label: '打开 AI 配置', href: '/settings?tab=ai&from=onboarding' },
    ],
    matchesPath: (pathname) => pathname.startsWith('/settings'),
  },
  {
    id: 'ai-tools',
    order: 9,
    group: 'AI',
    title: '用 AI 扩展研究路径',
    description: '最后再去 AI 中心、智能搜索和模板入口，理解它们如何加速前面的市场、研究和交易流程。',
    focus: '至少访问 AI 中心、智能搜索或模板中心中的一个，把增强入口串到主工作流里。',
    outcome: '理解系统不是单页集合，而是有 AI 增强层的统一工作台。',
    actions: [
      { label: '打开 AI 中心', href: '/assistant?from=onboarding' },
      { label: '打开智能搜索', href: '/search?from=onboarding' },
      { label: '查看模板中心', href: '/workspace-templates?from=onboarding' },
    ],
    matchesPath: (pathname) =>
      pathname.startsWith('/assistant') || pathname.startsWith('/search') || pathname.startsWith('/workspace-templates'),
  },
];

const STEP_STATUS_RANK: Record<OnboardingStepStatus, number> = {
  todo: 0,
  visited: 1,
  skipped: 2,
  done: 3,
};

export function getOnboardingStorageKey(userId: string) {
  return `aiask.onboarding.v${ONBOARDING_VERSION}.${userId}`;
}

export function createDefaultOnboardingSnapshot(): OnboardingSnapshot {
  const steps = Object.fromEntries(
    ONBOARDING_STEPS.map((step) => [
      step.id,
      {
        status: 'todo',
      } satisfies OnboardingStepState,
    ]),
  ) as Record<OnboardingStepId, OnboardingStepState>;

  return {
    version: ONBOARDING_VERSION,
    overlayMode: 'expanded',
    currentStepId: ONBOARDING_STEPS[0].id,
    entrySurface: 'overview',
    routeScope: '/',
    updatedAt: new Date(0).toISOString(),
    steps,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isStepStatus(value: unknown): value is OnboardingStepStatus {
  return value === 'todo' || value === 'visited' || value === 'done' || value === 'skipped';
}

function isOverlayMode(value: unknown): value is OnboardingOverlayMode {
  return value === 'expanded' || value === 'minimized' || value === 'hidden';
}

function isEntrySurface(value: unknown): value is OnboardingEntrySurface {
  return value === 'overview' || value === 'workspace' || value === 'utility';
}

function readTimestamp(value: unknown) {
  if (typeof value !== 'string' || !value.trim()) return undefined;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : undefined;
}

function normalizeStepState(value: unknown): OnboardingStepState {
  const record = isRecord(value) ? value : {};
  return {
    status: isStepStatus(record.status) ? record.status : 'todo',
    visitedAt: readTimestamp(record.visitedAt),
    completedAt: readTimestamp(record.completedAt),
    skippedAt: readTimestamp(record.skippedAt),
  };
}

export function parseOnboardingSnapshot(value: unknown): OnboardingSnapshot | null {
  if (!isRecord(value)) return null;
  const base = createDefaultOnboardingSnapshot();
  const record = value;
  const rawSteps = isRecord(record.steps) ? record.steps : {};
  const steps = { ...base.steps };

  for (const step of ONBOARDING_STEPS) {
    steps[step.id] = normalizeStepState(rawSteps[step.id]);
  }

  return {
    version: typeof record.version === 'number' ? record.version : ONBOARDING_VERSION,
    overlayMode: isOverlayMode(record.overlayMode) ? record.overlayMode : base.overlayMode,
    currentStepId: ONBOARDING_STEPS.some((step) => step.id === record.currentStepId)
      ? (record.currentStepId as OnboardingStepId)
      : base.currentStepId,
    entrySurface: isEntrySurface(record.entrySurface) ? record.entrySurface : base.entrySurface,
    routeScope: typeof record.routeScope === 'string' && record.routeScope.trim() ? record.routeScope.trim() : base.routeScope,
    dismissedUntil: readTimestamp(record.dismissedUntil),
    lastCompletedStep: ONBOARDING_STEPS.some((step) => step.id === record.lastCompletedStep)
      ? (record.lastCompletedStep as OnboardingStepId)
      : undefined,
    updatedAt: readTimestamp(record.updatedAt) ?? base.updatedAt,
    completedAt: readTimestamp(record.completedAt),
    steps,
  };
}

function pickLaterTimestamp(...values: Array<string | undefined>) {
  const filtered = values.filter((value): value is string => Boolean(value));
  if (filtered.length === 0) return undefined;
  return filtered.sort().at(-1);
}

function mergeStepState(primary: OnboardingStepState, secondary: OnboardingStepState): OnboardingStepState {
  const winner =
    STEP_STATUS_RANK[primary.status] >= STEP_STATUS_RANK[secondary.status] ? primary.status : secondary.status;

  return {
    status: winner,
    visitedAt: pickLaterTimestamp(primary.visitedAt, secondary.visitedAt),
    completedAt: pickLaterTimestamp(primary.completedAt, secondary.completedAt),
    skippedAt: pickLaterTimestamp(primary.skippedAt, secondary.skippedAt),
  };
}

export function mergeOnboardingSnapshots(
  localSnapshot: OnboardingSnapshot | null,
  remoteSnapshot: OnboardingSnapshot | null,
): OnboardingSnapshot {
  const base = createDefaultOnboardingSnapshot();
  const left = localSnapshot ?? base;
  const right = remoteSnapshot ?? base;
  const steps = { ...base.steps };

  for (const step of ONBOARDING_STEPS) {
    steps[step.id] = mergeStepState(left.steps[step.id] ?? base.steps[step.id], right.steps[step.id] ?? base.steps[step.id]);
  }

  const completedAt = pickLaterTimestamp(left.completedAt, right.completedAt);
  const merged: OnboardingSnapshot = {
    version: ONBOARDING_VERSION,
    overlayMode: left.overlayMode ?? right.overlayMode ?? base.overlayMode,
    currentStepId: resolveCurrentStepId(steps, left.currentStepId ?? right.currentStepId ?? base.currentStepId),
    entrySurface: left.entrySurface ?? right.entrySurface ?? base.entrySurface,
    routeScope: left.routeScope || right.routeScope || base.routeScope,
    dismissedUntil: pickLaterTimestamp(left.dismissedUntil, right.dismissedUntil),
    lastCompletedStep: left.lastCompletedStep ?? right.lastCompletedStep,
    updatedAt: pickLaterTimestamp(left.updatedAt, right.updatedAt) ?? new Date().toISOString(),
    completedAt,
    steps,
  };

  return applyCompletionState(merged);
}

export function resolveCurrentStepId(
  steps: Record<OnboardingStepId, OnboardingStepState>,
  preferredId?: OnboardingStepId,
) {
  if (preferredId && steps[preferredId] && !isStepResolved(steps[preferredId].status)) {
    return preferredId;
  }

  const nextPending = ONBOARDING_STEPS.find((step) => !isStepResolved(steps[step.id].status));
  return nextPending?.id ?? ONBOARDING_STEPS[ONBOARDING_STEPS.length - 1].id;
}

export function isStepResolved(status: OnboardingStepStatus) {
  return status === 'done' || status === 'skipped';
}

export function deriveOnboardingProgress(snapshot: OnboardingSnapshot | null) {
  const total = ONBOARDING_STEPS.length;
  if (!snapshot) {
    return { total, done: 0, skipped: 0, visited: 0, percent: 0, completed: false };
  }

  let done = 0;
  let skipped = 0;
  let visited = 0;
  for (const step of ONBOARDING_STEPS) {
    const status = snapshot.steps[step.id].status;
    if (status === 'done') done += 1;
    if (status === 'skipped') skipped += 1;
    if (status === 'visited') visited += 1;
  }

  const completed = done + skipped === total;
  return {
    total,
    done,
    skipped,
    visited,
    percent: total > 0 ? Math.round(((done + skipped) / total) * 100) : 0,
    completed,
  };
}

export function applyCompletionState(snapshot: OnboardingSnapshot): OnboardingSnapshot {
  const progress = deriveOnboardingProgress(snapshot);
  const next: OnboardingSnapshot = {
    ...snapshot,
    currentStepId: resolveCurrentStepId(snapshot.steps, snapshot.currentStepId),
  };

  if (progress.completed) {
    return {
      ...next,
      completedAt: snapshot.completedAt ?? new Date().toISOString(),
      overlayMode: 'hidden',
    };
  }

  if (next.completedAt) {
    return {
      ...next,
      completedAt: undefined,
    };
  }

  return next;
}

export function dispatchOnboardingSignal(signal: OnboardingSignal) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent<OnboardingSignal>(ONBOARDING_SIGNAL_EVENT, { detail: signal }));
}

export function resolveOnboardingRouteScope(pathname: string) {
  const segment = pathname.split('/').filter(Boolean)[0];
  return segment ? `/${segment}` : '/';
}

export function resolveOnboardingEntrySurface(pathname: string): OnboardingEntrySurface {
  if (
    pathname === '/'
    || pathname.startsWith('/market')
    || pathname.startsWith('/risk')
    || pathname.startsWith('/performance')
  ) {
    return 'overview';
  }

  if (
    pathname.startsWith('/assistant')
    || pathname.startsWith('/strategy-market')
    || pathname.startsWith('/paper-trading')
    || pathname.startsWith('/research')
  ) {
    return 'workspace';
  }

  return 'utility';
}

export function prefersExpandedOnboarding(pathname: string, compactLayout: boolean) {
  if (compactLayout) return false;
  return pathname === '/' || pathname.startsWith('/market');
}

declare global {
  interface WindowEventMap {
    [ONBOARDING_SIGNAL_EVENT]: CustomEvent<OnboardingSignal>;
  }
}
