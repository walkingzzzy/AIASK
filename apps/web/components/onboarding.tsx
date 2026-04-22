'use client';

import Link from 'next/link';
import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { getLlmConfig } from '@/lib/chat-api';
import {
  ONBOARDING_SIGNAL_EVENT,
  ONBOARDING_STEPS,
  applyCompletionState,
  createDefaultOnboardingSnapshot,
  deriveOnboardingProgress,
  dispatchOnboardingSignal,
  getOnboardingStorageKey,
  isStepResolved,
  mergeOnboardingSnapshots,
  parseOnboardingSnapshot,
  prefersExpandedOnboarding,
  resolveOnboardingEntrySurface,
  resolveOnboardingRouteScope,
  type OnboardingSignal,
  type OnboardingOverlayMode,
  type OnboardingSnapshot,
  type OnboardingStepDefinition,
  type OnboardingStepId,
  type OnboardingStepState,
  type OnboardingStepStatus,
} from '@/lib/onboarding';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { useAuthStore } from '@/store/auth-store';
import { useWatchlistStore } from '@/store/watchlist-store';

type OnboardingStepEntry = OnboardingStepDefinition & {
  state: OnboardingStepState;
  statusLabel: string;
  isCurrent: boolean;
};

type OnboardingContextValue = {
  ready: boolean;
  overlayMode: OnboardingOverlayMode;
  snapshot: OnboardingSnapshot | null;
  steps: OnboardingStepEntry[];
  currentStep: OnboardingStepEntry | null;
  matchedStep: OnboardingStepEntry | null;
  nextStep: OnboardingStepEntry | null;
  progress: ReturnType<typeof deriveOnboardingProgress>;
  expand: () => void;
  minimize: () => void;
  hide: () => void;
  selectStep: (stepId: OnboardingStepId) => void;
  completeStep: (stepId: OnboardingStepId) => void;
  skipStep: (stepId: OnboardingStepId) => void;
  restart: () => void;
};

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

function readRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function readOnboardingSnapshotFromLocalStorage(storageKey: string | null) {
  if (!storageKey || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    return parseOnboardingSnapshot(JSON.parse(raw));
  } catch {
    return null;
  }
}

function hasAiConfig(value: Awaited<ReturnType<typeof getLlmConfig>>) {
  return Boolean(value?.hasStoredApiKey && value.baseUrl?.trim() && value.model?.trim());
}

function stepStatusLabel(status: OnboardingStepStatus) {
  if (status === 'done') return '已完成';
  if (status === 'skipped') return '已跳过';
  if (status === 'visited') return '已到达';
  return '待开始';
}

function stepStatusTone(status: OnboardingStepStatus) {
  if (status === 'done') return 'border-success/20 bg-success/10 text-success';
  if (status === 'skipped') return 'border-warning/20 bg-warning/10 text-warning';
  if (status === 'visited') return 'border-primary/20 bg-primary/10 text-primary';
  return 'border-border bg-surface-alt text-text-secondary';
}

function findMatchedStepId(pathname: string) {
  return ONBOARDING_STEPS.find((step) => step.matchesPath(pathname))?.id ?? null;
}

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const hydrated = useHydrated();
  const pathname = useStablePathname() ?? '/';
  const compactOnboarding = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const groups = useWatchlistStore((state) => state.groups);
  const onboardingApi = useApiMutation<Record<string, unknown>>({ successToast: false, errorToast: false });

  const [snapshot, setSnapshot] = useState<OnboardingSnapshot | null>(null);
  const [ready, setReady] = useState(false);
  const userIdRef = useRef<string | null>(null);
  const dirtyRef = useRef(false);
  const lastPersistedRef = useRef<string | null>(null);

  const storageKey = user?.id ? getOnboardingStorageKey(user.id) : null;
  const watchlistCount = useMemo(
    () => groups.reduce((total, group) => total + group.items.length, 0),
    [groups],
  );
  const matchedStepId = findMatchedStepId(pathname);

  const refreshAiConfig = useCallback(async () => {
    if (!user?.id) return;
    const config = await getLlmConfig();
    if (!hasAiConfig(config)) return;
    setSnapshot((current) => {
      if (!current) return current;
      const previous = current.steps['ai-config'];
      if (previous.status === 'done') return current;
      const now = new Date().toISOString();
      dirtyRef.current = true;
      return applyCompletionState({
        ...current,
        updatedAt: now,
        steps: {
          ...current.steps,
          'ai-config': {
            status: 'done',
            visitedAt: previous.visitedAt ?? now,
            completedAt: now,
            skippedAt: undefined,
          },
        },
      });
    });
  }, [user?.id]);

  const updateSnapshot = useCallback((updater: (current: OnboardingSnapshot) => OnboardingSnapshot) => {
    setSnapshot((current) => {
      if (!current) return current;
      const next = applyCompletionState(updater(current));
      const previousSerialized = JSON.stringify(current);
      const nextSerialized = JSON.stringify(next);
      if (previousSerialized === nextSerialized) return current;
      dirtyRef.current = true;
      return next;
    });
  }, []);

  const markStep = useCallback(
    (stepId: OnboardingStepId, status: OnboardingStepStatus) => {
      updateSnapshot((current) => {
        const previous = current.steps[stepId];
        const now = new Date().toISOString();
        if (status === 'visited' && previous.status !== 'todo' && previous.visitedAt) {
          return current;
        }

        if (status === 'done' && previous.status === 'done') {
          return current;
        }

        if (status === 'skipped' && isStepResolved(previous.status)) {
          return current;
        }

        return {
          ...current,
          currentStepId: stepId,
          lastCompletedStep: status === 'done' ? stepId : current.lastCompletedStep,
          dismissedUntil: status === 'done' ? undefined : current.dismissedUntil,
          overlayMode: status === 'done' && current.overlayMode === 'expanded' ? 'minimized' : current.overlayMode,
          updatedAt: now,
          steps: {
            ...current.steps,
            [stepId]: {
              status:
                status === 'visited'
                  ? previous.status === 'todo'
                    ? 'visited'
                    : previous.status
                  : status,
              visitedAt: previous.visitedAt ?? now,
              completedAt: status === 'done' ? now : status === 'skipped' ? undefined : previous.completedAt,
              skippedAt: status === 'skipped' ? now : status === 'done' ? undefined : previous.skippedAt,
            },
          },
        };
      });
    },
    [updateSnapshot],
  );

  const selectStep = useCallback(
    (stepId: OnboardingStepId) => {
      updateSnapshot((current) => ({
        ...current,
        currentStepId: stepId,
        overlayMode: 'expanded',
        dismissedUntil: undefined,
        updatedAt: new Date().toISOString(),
      }));
    },
    [updateSnapshot],
  );

  const minimize = useCallback(() => {
    updateSnapshot((current) => ({
      ...current,
      overlayMode: 'minimized',
      updatedAt: new Date().toISOString(),
    }));
  }, [updateSnapshot]);

  const expand = useCallback(() => {
    updateSnapshot((current) => ({
      ...current,
      overlayMode: 'expanded',
      dismissedUntil: undefined,
      updatedAt: new Date().toISOString(),
    }));
  }, [updateSnapshot]);

  const hide = useCallback(() => {
    const dismissedUntil = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    updateSnapshot((current) => ({
      ...current,
      overlayMode: 'hidden',
      dismissedUntil,
      updatedAt: new Date().toISOString(),
    }));
  }, [updateSnapshot]);

  const completeStep = useCallback((stepId: OnboardingStepId) => markStep(stepId, 'done'), [markStep]);
  const skipStep = useCallback((stepId: OnboardingStepId) => markStep(stepId, 'skipped'), [markStep]);

  const restart = useCallback(() => {
    const next = createDefaultOnboardingSnapshot();
    next.updatedAt = new Date().toISOString();
    if (matchedStepId) {
      next.currentStepId = matchedStepId;
    }
    dirtyRef.current = true;
    setSnapshot(next);
  }, [matchedStepId]);

  useEffect(() => {
    if (!hydrated) return;
    if (!user?.id) {
      userIdRef.current = null;
      lastPersistedRef.current = null;
      dirtyRef.current = false;
      setSnapshot(null);
      setReady(true);
      return;
    }

    if (userIdRef.current === user.id && snapshot) {
      setReady(true);
      return;
    }

    const serverSnapshot = parseOnboardingSnapshot(readRecord(user.preferences).onboarding);
    const localSnapshot = readOnboardingSnapshotFromLocalStorage(storageKey);
    const mergedSnapshot = mergeOnboardingSnapshots(localSnapshot, serverSnapshot);
    const mergedSerialized = JSON.stringify(mergedSnapshot);
    const serverSerialized = serverSnapshot ? JSON.stringify(serverSnapshot) : null;

    userIdRef.current = user.id;
    lastPersistedRef.current = serverSerialized ?? (localSnapshot ? null : mergedSerialized);
    dirtyRef.current = Boolean(localSnapshot) && mergedSerialized !== serverSerialized;
    setSnapshot(mergedSnapshot);
    setReady(true);
    void refreshAiConfig();
  }, [hydrated, refreshAiConfig, snapshot, storageKey, user]);

  useEffect(() => {
    if (!hydrated || !storageKey || !snapshot) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(snapshot));
    } catch {}
  }, [hydrated, snapshot, storageKey]);

  useEffect(() => {
    if (!hydrated || !user?.id || !snapshot || !dirtyRef.current) return;
    const serialized = JSON.stringify(snapshot);
    if (serialized === lastPersistedRef.current) {
      dirtyRef.current = false;
      return;
    }

    const timer = window.setTimeout(() => {
      void onboardingApi
        .triggerAsync('/auth/profile', { method: 'POST' }, { preferences: { onboarding: snapshot } })
        .then(() => {
          lastPersistedRef.current = serialized;
          dirtyRef.current = false;
          if (!user) return;
          setUser({
            ...user,
            preferences: {
              ...(user.preferences ?? {}),
              onboarding: snapshot,
            },
          });
        })
        .catch(() => {});
    }, 500);

    return () => window.clearTimeout(timer);
  }, [hydrated, onboardingApi, setUser, snapshot, user]);

  useEffect(() => {
    if (!ready || !snapshot || !matchedStepId) return;
    const matchedDefinition = ONBOARDING_STEPS.find((step) => step.id === matchedStepId);
    if (!matchedDefinition) return;
    if (matchedDefinition.completeOnVisit) {
      completeStep(matchedStepId);
      return;
    }
    markStep(matchedStepId, 'visited');
  }, [completeStep, markStep, matchedStepId, ready, snapshot]);

  useEffect(() => {
    if (!ready) return;
    const routeScope = resolveOnboardingRouteScope(pathname);
    const entrySurface = resolveOnboardingEntrySurface(pathname);
    const keepExpanded = prefersExpandedOnboarding(pathname, compactOnboarding);
    updateSnapshot((current) => {
      const activeDismissal =
        current.dismissedUntil && Date.parse(current.dismissedUntil) > Date.now()
          ? current.dismissedUntil
          : undefined;
      const shouldRestore = current.overlayMode === 'hidden' && !activeDismissal && !current.completedAt;
      const nextOverlayMode =
        shouldRestore
          ? (keepExpanded ? 'expanded' : 'minimized')
          : current.overlayMode === 'expanded' && !keepExpanded
            ? 'minimized'
            : current.overlayMode;
      if (
        current.routeScope === routeScope
        && current.entrySurface === entrySurface
        && current.dismissedUntil === activeDismissal
        && current.overlayMode === nextOverlayMode
      ) {
        return current;
      }
      return {
        ...current,
        routeScope,
        entrySurface,
        dismissedUntil: activeDismissal,
        overlayMode: nextOverlayMode,
        updatedAt: new Date().toISOString(),
      };
    });
  }, [compactOnboarding, pathname, ready, updateSnapshot]);

  useEffect(() => {
    if (!ready || watchlistCount <= 0) return;
    completeStep('watchlist');
  }, [completeStep, ready, watchlistCount]);

  useEffect(() => {
    if (!hydrated) return;
    const handleSignal = (event: CustomEvent<OnboardingSignal>) => {
      if (event.detail.type === 'paper-trading.example-loaded' || event.detail.type === 'paper-trading.submitted') {
        completeStep('paper-trading');
        return;
      }
      if (event.detail.type === 'ai-config.saved') {
        void refreshAiConfig();
      }
    };

    window.addEventListener(ONBOARDING_SIGNAL_EVENT, handleSignal as EventListener);
    return () => {
      window.removeEventListener(ONBOARDING_SIGNAL_EVENT, handleSignal as EventListener);
    };
  }, [completeStep, hydrated, refreshAiConfig]);

  const progress = useMemo(() => deriveOnboardingProgress(snapshot), [snapshot]);

  const stepEntries = useMemo<OnboardingStepEntry[]>(() => {
    const baseSnapshot = snapshot ?? createDefaultOnboardingSnapshot();
    return ONBOARDING_STEPS.map((step) => ({
      ...step,
      state: baseSnapshot.steps[step.id],
      statusLabel: stepStatusLabel(baseSnapshot.steps[step.id].status),
      isCurrent: baseSnapshot.currentStepId === step.id,
    }));
  }, [snapshot]);

  const currentStep = useMemo(
    () => stepEntries.find((step) => step.id === (snapshot?.currentStepId ?? ONBOARDING_STEPS[0].id)) ?? null,
    [snapshot?.currentStepId, stepEntries],
  );
  const matchedStep = useMemo(
    () => stepEntries.find((step) => step.id === matchedStepId) ?? null,
    [matchedStepId, stepEntries],
  );
  const nextStep = useMemo(
    () => stepEntries.find((step) => !isStepResolved(step.state.status)) ?? null,
    [stepEntries],
  );

  const value = useMemo<OnboardingContextValue>(
    () => ({
      ready,
      overlayMode: snapshot?.overlayMode ?? 'expanded',
      snapshot,
      steps: stepEntries,
      currentStep,
      matchedStep,
      nextStep,
      progress,
      expand,
      minimize,
      hide,
      selectStep,
      completeStep,
      skipStep,
      restart,
    }),
    [
      completeStep,
      currentStep,
      expand,
      hide,
      matchedStep,
      minimize,
      nextStep,
      progress,
      ready,
      restart,
      selectStep,
      skipStep,
      snapshot,
      stepEntries,
    ],
  );

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>;
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useOnboarding must be used within <OnboardingProvider>');
  }
  return context;
}

function StepStatusBadge({ status }: { status: OnboardingStepStatus }) {
  return (
    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${stepStatusTone(status)}`}>
      {stepStatusLabel(status)}
    </span>
  );
}

export function Onboarding({ className = '' }: { className?: string }) {
  const compactOnboarding = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const { ready, overlayMode, progress, currentStep, matchedStep, nextStep, expand, minimize } =
    useOnboarding();
  const effectiveOverlayMode = compactOnboarding ? 'minimized' : overlayMode;
  const sectionClassName =
    effectiveOverlayMode === 'minimized'
      ? 'panel-soft rounded-[20px] px-3 py-2.5 sm:px-4 sm:py-3'
      : 'panel-soft rounded-[24px] p-4 sm:p-5';

  if (!ready || !currentStep || progress.completed || overlayMode === 'hidden') {
    return null;
  }

  if (
    effectiveOverlayMode === 'minimized'
    && matchedStep
    && matchedStep.id !== currentStep.id
    && isStepResolved(matchedStep.state.status)
  ) {
    return null;
  }

  return (
    <section className={`${sectionClassName} ${className}`} data-testid="onboarding-banner">
      {effectiveOverlayMode === 'minimized' ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
              快速上手
            </span>
            <div className="min-w-0 text-sm font-semibold text-text-primary">
              第 {currentStep.order} 步 · {currentStep.title}
            </div>
            <span className="text-xs text-text-secondary">
              {progress.done + progress.skipped}/{progress.total} 步
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={expand} className="action-chip cursor-pointer text-sm text-text-primary">
              展开当前步骤
            </button>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary">
                快速上手
              </span>
              <span className="rounded-full border border-border px-2.5 py-1 text-[11px] text-text-secondary">
                第 {currentStep.order} 步 / 共 {progress.total} 步
              </span>
              <StepStatusBadge status={currentStep.state.status} />
              {matchedStep?.id === currentStep.id ? (
                <span className="rounded-full border border-success/20 bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success">
                  当前页面
                </span>
              ) : null}
            </div>
            <h3 className="mb-0 mt-3 text-lg font-semibold text-text-primary">{currentStep.title}</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{currentStep.focus}</p>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-alt/70">
              <div
                className="h-full rounded-full bg-[linear-gradient(90deg,rgba(11,107,203,0.92),rgba(61,146,255,0.78))]"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                href={currentStep.actions[0]?.href ?? '/'}
                className="inline-flex items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white no-underline shadow-[0_18px_34px_-24px_rgba(11,107,203,0.48)] transition hover:-translate-y-0.5"
              >
                {currentStep.actions[0]?.label ?? '打开当前步骤'}
              </Link>
              {nextStep && nextStep.id !== currentStep.id ? (
                <Link href={nextStep.actions[0]?.href ?? '/'} className="action-chip text-sm no-underline text-inherit">
                  {nextStep.actions[0]?.label ?? '打开下一步'}
                </Link>
              ) : null}
              <button
                type="button"
                onClick={minimize}
                className="action-chip cursor-pointer text-sm text-text-primary"
              >
                最小化
              </button>
            </div>
          </div>

          <div className="rounded-[20px] border border-white/55 bg-white/26 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">下一步建议</div>
            <div className="mt-3 text-sm font-semibold text-text-primary">
              {nextStep && nextStep.id !== currentStep.id ? `第 ${nextStep.order} 步 · ${nextStep.title}` : '先完成当前步骤'}
            </div>
            <div className="mt-2 text-sm leading-6 text-text-secondary">
              {nextStep && nextStep.id !== currentStep.id ? nextStep.focus : currentStep.outcome}
            </div>
            <div className="mt-4 space-y-2">
              <div className="metric-tile rounded-[18px] px-3 py-2 text-xs text-text-secondary">
                已完成 {progress.done} 步，已跳过 {progress.skipped} 步，当前进度 {progress.percent}%
              </div>
              {currentStep.outcome ? (
                <div className="metric-tile rounded-[18px] px-3 py-2 text-xs text-text-secondary">
                  完成后你会得到：{currentStep.outcome}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export { dispatchOnboardingSignal };
