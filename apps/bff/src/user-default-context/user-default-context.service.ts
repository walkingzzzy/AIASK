import { Injectable } from '@nestjs/common';
import type { WorkspaceSharedContext, WorkspaceStateSnapshot } from '@aiask/shared-types';
import { PreferencesService } from '../auth/preferences.service';
import { WatchlistService, type WatchlistGroup } from '../watchlist/watchlist.service';
import { PaperTradingService } from '../paper-trading/paper-trading.service';

type UserPreferencesRecord = Record<string, unknown> & {
  userDefaultContext?: Record<string, unknown>;
  workspaceState?: unknown;
  defaultStockCode?: unknown;
};

export type UserDefaultContextPatch = {
  stockCode?: string | null;
  accountId?: string | null;
  strategyId?: string | null;
  strategyName?: string | null;
  workspaceId?: string | null;
};

type DefaultContextSource = 'workspace' | 'recent_confirmed' | 'watchlist' | 'paper_position' | 'profile' | 'none';

type StockCandidate = {
  code: string | null;
  source: DefaultContextSource;
  confirmedAt?: string | null;
  requiresConfirmation?: boolean;
};

@Injectable()
export class UserDefaultContextService {
  private static readonly SYSTEM_STOCK_FALLBACKS = new Set(['000001', '600519']);

  constructor(
    private readonly preferencesService: PreferencesService,
    private readonly watchlistService: WatchlistService,
    private readonly paperTradingService: PaperTradingService,
  ) {}

  async getDefaultContext(userId: string) {
    const prefs = await this.preferencesService.getUserPreferences(userId) as UserPreferencesRecord;
    const workspaceState = this.asWorkspaceState(prefs.workspaceState);
    const activeWorkspace = workspaceState?.workspaces.find((workspace) => workspace.id === workspaceState.activeWorkspaceId)
      ?? workspaceState?.workspaces[0]
      ?? null;
    const workspaceContext = activeWorkspace?.context ?? {};
    const profileContext = this.asRecord(prefs.userDefaultContext);
    const watchlistLeadCode = await this.resolveWatchlistLeadCode(userId);
    const paperContext = await this.resolvePaperTradingContext(userId);
    const workspaceConfirmedAt = this.isoString(workspaceContext.stockConfirmedAt);
    const profileConfirmedAt = this.isoString(profileContext.stockConfirmedAt);
    const workspaceStockCode = this.trustedStockCode(workspaceContext.stockCode, workspaceConfirmedAt);
    const recentConfirmedStockCode = this.confirmedStockCode(profileContext.stockCode, profileConfirmedAt);
    const profileStockCode = this.profileStockCode(profileContext.stockCode ?? prefs.defaultStockCode);
    const stockCandidate = this.firstStockCandidate([
      { code: workspaceStockCode, source: 'workspace', confirmedAt: workspaceConfirmedAt },
      { code: recentConfirmedStockCode, source: 'recent_confirmed', confirmedAt: profileConfirmedAt },
      { code: watchlistLeadCode, source: 'watchlist' },
      { code: paperContext.stockCode, source: 'paper_position' },
      { code: profileStockCode, source: 'profile' },
    ]);
    const stockCode = stockCandidate.code;
    const accountId = this.nonEmptyString(workspaceContext.accountId)
      ?? paperContext.accountId
      ?? this.nonEmptyString(profileContext.accountId)
      ?? null;
    const strategyId = this.nonEmptyString(workspaceContext.strategyId)
      ?? this.nonEmptyString(profileContext.strategyId)
      ?? null;
    const emptyReason = stockCode
      ? null
      : this.hasLegacySystemFallback(workspaceContext, profileContext, prefs)
        ? 'legacy_system_fallback_ignored'
        : 'no_user_context';

    return {
      stockCode,
      trustedStockCode: stockCode,
      stockSource: stockCandidate.source,
      stockConfirmedAt: stockCandidate.confirmedAt ?? null,
      emptyReason,
      accountId,
      strategyId,
      strategyName: this.nonEmptyString(workspaceContext.strategyName)
        ?? this.nonEmptyString(profileContext.strategyName)
        ?? null,
      workspaceId: activeWorkspace?.id ?? null,
      workspaceName: activeWorkspace?.name ?? null,
      workspaceContext,
      watchlistLeadCode,
      paperPositionLeadCode: paperContext.stockCode,
      profileStockCode,
      sources: {
        workspace: {
          stockCode: workspaceStockCode,
          rawStockCode: this.stockCode(workspaceContext.stockCode),
          stockConfirmedAt: workspaceConfirmedAt,
          accountId: this.nonEmptyString(workspaceContext.accountId) ?? null,
          strategyId: this.nonEmptyString(workspaceContext.strategyId) ?? null,
        },
        watchlist: { stockCode: watchlistLeadCode },
        paperTrading: {
          stockCode: paperContext.stockCode,
          accountId: paperContext.accountId,
        },
        profile: {
          stockCode: profileStockCode,
          rawStockCode: this.stockCode(profileContext.stockCode ?? prefs.defaultStockCode),
          stockConfirmedAt: profileConfirmedAt,
          accountId: this.nonEmptyString(profileContext.accountId) ?? null,
          strategyId: this.nonEmptyString(profileContext.strategyId) ?? null,
        },
      },
      updatedAt: new Date().toISOString(),
    };
  }

  async saveDefaultContext(userId: string, patch: UserDefaultContextPatch) {
    const prefs = await this.preferencesService.getUserPreferences(userId) as UserPreferencesRecord;
    const currentProfileContext = this.asRecord(prefs.userDefaultContext);
    const confirmedAt = patch.stockCode ? new Date().toISOString() : this.isoString(currentProfileContext.stockConfirmedAt);
    const nextProfileContext = {
      ...currentProfileContext,
      ...this.compactPatch(patch, confirmedAt),
      updatedAt: new Date().toISOString(),
    };
    const workspaceState = this.patchWorkspaceState(prefs.workspaceState, patch, confirmedAt);
    await this.preferencesService.setUserPreferences(userId, {
      ...prefs,
      userDefaultContext: nextProfileContext,
      ...(workspaceState ? { workspaceState } : {}),
    });
    return this.getDefaultContext(userId);
  }

  private async resolveWatchlistLeadCode(userId: string): Promise<string | null> {
    try {
      const groups = await this.watchlistService.listGroups(userId);
      return this.firstWatchlistCode(groups);
    } catch {
      return null;
    }
  }

  private async resolvePaperTradingContext(userId: string): Promise<{ stockCode: string | null; accountId: string | null }> {
    try {
      const payload = await this.paperTradingService.positions(userId);
      const record = this.asRecord(payload);
      const positions = Array.isArray(record.positions)
        ? record.positions
        : Array.isArray(payload)
          ? payload
          : [];
      for (const item of positions) {
        const row = this.asRecord(item);
        const quantity = Number(row.quantity ?? row.shares ?? row.volume ?? row.available_quantity ?? 0);
        const code = this.stockCode(row.code ?? row.stock_code ?? row.symbol);
        if (code && (!Number.isFinite(quantity) || quantity > 0)) {
          return {
            stockCode: code,
            accountId: this.nonEmptyString(record.account_id ?? row.account_id),
          };
        }
      }
      return {
        stockCode: null,
        accountId: this.nonEmptyString(record.account_id),
      };
    } catch {
      return { stockCode: null, accountId: null };
    }
  }

  private firstWatchlistCode(groups: WatchlistGroup[]) {
    for (const group of groups) {
      for (const item of group.items ?? []) {
        const code = this.stockCode(item.code);
        if (code) return code;
      }
    }
    return null;
  }

  private firstStockCandidate(candidates: StockCandidate[]): StockCandidate {
    return candidates.find((candidate) => candidate.code) ?? { code: null, source: 'none' };
  }

  private trustedStockCode(value: unknown, confirmedAt?: string | null): string | null {
    const code = this.stockCode(value);
    if (!code) return null;
    if (confirmedAt) return code;
    return UserDefaultContextService.SYSTEM_STOCK_FALLBACKS.has(code) ? null : code;
  }

  private confirmedStockCode(value: unknown, confirmedAt?: string | null): string | null {
    const code = this.stockCode(value);
    return code && confirmedAt ? code : null;
  }

  private profileStockCode(value: unknown): string | null {
    const code = this.stockCode(value);
    if (!code) return null;
    return UserDefaultContextService.SYSTEM_STOCK_FALLBACKS.has(code) ? null : code;
  }

  private hasLegacySystemFallback(
    workspaceContext: WorkspaceSharedContext,
    profileContext: Record<string, unknown>,
    prefs: UserPreferencesRecord,
  ) {
    const candidates = [
      this.stockCode(workspaceContext.stockCode),
      this.stockCode(profileContext.stockCode),
      this.stockCode(prefs.defaultStockCode),
    ];
    return candidates.some((code) => code && UserDefaultContextService.SYSTEM_STOCK_FALLBACKS.has(code));
  }

  private patchWorkspaceState(
    value: unknown,
    patch: UserDefaultContextPatch,
    confirmedAt?: string | null,
  ): WorkspaceStateSnapshot | null {
    const snapshot = this.asWorkspaceState(value);
    if (!snapshot) return null;
    return {
      ...snapshot,
      workspaces: snapshot.workspaces.map((workspace) => {
        if (workspace.id !== snapshot.activeWorkspaceId) return workspace;
        const context: WorkspaceSharedContext = { ...workspace.context };
        const stockCode = this.stockCode(patch.stockCode);
        const accountId = this.nonEmptyString(patch.accountId);
        const strategyId = this.nonEmptyString(patch.strategyId);
        const strategyName = this.nonEmptyString(patch.strategyName);
        if (stockCode) {
          context.stockCode = stockCode;
          if (confirmedAt) context.stockConfirmedAt = confirmedAt;
        }
        if (accountId) context.accountId = accountId;
        if (strategyId) context.strategyId = strategyId;
        if (strategyName) context.strategyName = strategyName;
        return {
          ...workspace,
          updatedAt: Date.now(),
          context,
        };
      }),
      updatedAt: new Date().toISOString(),
    };
  }

  private compactPatch(patch: UserDefaultContextPatch, confirmedAt?: string | null) {
    const next: Record<string, unknown> = {};
    const stockCode = this.stockCode(patch.stockCode);
    const accountId = this.nonEmptyString(patch.accountId);
    const strategyId = this.nonEmptyString(patch.strategyId);
    const strategyName = this.nonEmptyString(patch.strategyName);
    const workspaceId = this.nonEmptyString(patch.workspaceId);
    if (stockCode) {
      next.stockCode = stockCode;
      if (confirmedAt) next.stockConfirmedAt = confirmedAt;
    }
    if (accountId) next.accountId = accountId;
    if (strategyId) next.strategyId = strategyId;
    if (strategyName) next.strategyName = strategyName;
    if (workspaceId) next.workspaceId = workspaceId;
    return next;
  }

  private asWorkspaceState(value: unknown): WorkspaceStateSnapshot | null {
    const record = this.asRecord(value);
    const activeWorkspaceId = this.nonEmptyString(record.activeWorkspaceId);
    const workspaces = Array.isArray(record.workspaces) ? record.workspaces : [];
    if (!activeWorkspaceId || workspaces.length === 0) return null;
    return value as WorkspaceStateSnapshot;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  }

  private nonEmptyString(value: unknown): string | null {
    const normalized = String(value ?? '').trim();
    return normalized.length > 0 ? normalized : null;
  }

  private isoString(value: unknown): string | null {
    const normalized = this.nonEmptyString(value);
    if (!normalized) return null;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date.toISOString();
  }

  private stockCode(value: unknown): string | null {
    const normalized = this.nonEmptyString(value);
    return normalized && /^\d{6}$/.test(normalized) ? normalized : null;
  }
}
