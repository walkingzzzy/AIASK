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

type DefaultContextSource = 'workspace' | 'watchlist' | 'paper_position' | 'profile' | 'none';

@Injectable()
export class UserDefaultContextService {
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
    const profileStockCode = this.stockCode(profileContext.stockCode) ?? this.stockCode(prefs.defaultStockCode);
    const workspaceStockCode = this.stockCode(workspaceContext.stockCode);
    const stockSource: DefaultContextSource = workspaceStockCode
      ? 'workspace'
      : watchlistLeadCode
        ? 'watchlist'
        : paperContext.stockCode
          ? 'paper_position'
          : profileStockCode
            ? 'profile'
            : 'none';
    const stockCode = workspaceStockCode ?? watchlistLeadCode ?? paperContext.stockCode ?? profileStockCode ?? null;
    const accountId = this.nonEmptyString(workspaceContext.accountId)
      ?? paperContext.accountId
      ?? this.nonEmptyString(profileContext.accountId)
      ?? null;
    const strategyId = this.nonEmptyString(workspaceContext.strategyId)
      ?? this.nonEmptyString(profileContext.strategyId)
      ?? null;

    return {
      stockCode,
      stockSource,
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
    const nextProfileContext = {
      ...currentProfileContext,
      ...this.compactPatch(patch),
      updatedAt: new Date().toISOString(),
    };
    const workspaceState = this.patchWorkspaceState(prefs.workspaceState, patch);
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

  private patchWorkspaceState(value: unknown, patch: UserDefaultContextPatch): WorkspaceStateSnapshot | null {
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
        if (stockCode) context.stockCode = stockCode;
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

  private compactPatch(patch: UserDefaultContextPatch) {
    const next: Record<string, unknown> = {};
    const stockCode = this.stockCode(patch.stockCode);
    const accountId = this.nonEmptyString(patch.accountId);
    const strategyId = this.nonEmptyString(patch.strategyId);
    const strategyName = this.nonEmptyString(patch.strategyName);
    const workspaceId = this.nonEmptyString(patch.workspaceId);
    if (stockCode) next.stockCode = stockCode;
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

  private stockCode(value: unknown): string | null {
    const normalized = this.nonEmptyString(value);
    return normalized && /^\d{6}$/.test(normalized) ? normalized : null;
  }
}
