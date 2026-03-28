import { Injectable } from '@nestjs/common';
import { AuthService } from '../auth/auth.service';
import { PaperTradingService } from '../paper-trading/paper-trading.service';
import { WatchlistService } from '../watchlist/watchlist.service';
import { ResearchService } from '../research/research.service';
import { NotificationService } from '../notification/notification.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class ExportService {
  private static readonly EXPORT_SECTION_TIMEOUT_MS = 8_000;

  constructor(
    private readonly authService: AuthService,
    private readonly paperTradingService: PaperTradingService,
    private readonly watchlistService: WatchlistService,
    private readonly researchService: ResearchService,
    private readonly notificationService: NotificationService,
    private readonly mcpGatewayService: McpGatewayService,
  ) {}

  async exportUserData(userId: string) {
    const [profile, summary, positions, orders, performance, watchlist, notifications, news, portfolios, alerts] = await Promise.all([
      this.resolveSection('auth.profile', () => this.authService.getProfile(userId), {
        id: '',
        username: '',
        role: 'user',
        riskLevel: '稳健',
        nickname: null,
        avatarUrl: null,
        preferences: {},
      } as Awaited<ReturnType<AuthService['getProfile']>>),
      this.resolveSection('paper_trading.summary', () => this.paperTradingService.summary(userId), {}),
      this.resolveSection('paper_trading.positions', () => this.paperTradingService.positions(userId), []),
      this.resolveSection('paper_trading.orders', () => this.paperTradingService.orders(userId), []),
      this.resolveSection('paper_trading.performance', () => this.paperTradingService.performance(userId, undefined, 30), {
        dailyReturns: [],
        metrics: {
          totalReturn: 0,
          sharpe: 0,
          maxDrawdown: 0,
          winRate: 0,
          avgHoldDays: 0,
        },
        warnings: [],
      } as Awaited<ReturnType<PaperTradingService['performance']>>),
      this.resolveSection('watchlist.list_groups', () => this.watchlistService.listGroups(userId), []),
      this.resolveSection('notifications.list', () => this.notificationService.list(userId, { limit: 100 }), {
        items: [],
        total: 0,
        unread: 0,
      } as Awaited<ReturnType<NotificationService['list']>>),
      this.resolveSection('research.market_news', () => this.researchService.getMarketNews(10), { items: [], count: 0 }),
      this.resolveSection(
        'portfolio_manager.list',
        () => this.callTool('portfolio_manager', { action: 'list', kwargs: JSON.stringify({ user_id: userId }) }),
        { success: false, tool: 'portfolio_manager', error: 'portfolio export unavailable' },
      ),
      this.resolveSection(
        'alerts_manager.list',
        () => this.callTool('alerts_manager', { action: 'list', kwargs: JSON.stringify({ user_id: userId, status: 'active' }) }),
        { success: false, tool: 'alerts_manager', error: 'alerts export unavailable' },
      ),
    ]);

    return {
      exportedAt: new Date().toISOString(),
      profile: profile.data,
      paperTrading: {
        summary: summary.data,
        positions: positions.data,
        orders: orders.data,
        performance: performance.data,
      },
      watchlist: watchlist.data,
      notifications: notifications.data,
      marketNews: news.data,
      portfolios: portfolios.data,
      alerts: alerts.data,
      warnings: [
        profile.warning,
        summary.warning,
        positions.warning,
        orders.warning,
        performance.warning,
        watchlist.warning,
        notifications.warning,
        news.warning,
        portfolios.warning,
        alerts.warning,
      ].filter((item): item is string => Boolean(item)),
    };
  }

  async generateReport(userId: string, period = 'monthly') {
    const payload = await this.exportUserData(userId);
    const profile = payload.profile as Record<string, unknown>;
    const summary = payload.paperTrading.summary as Record<string, unknown>;
    const perf = payload.paperTrading.performance as Record<string, unknown>;
    const metrics = (perf.metrics ?? {}) as Record<string, unknown>;
    const watchlist = Array.isArray(payload.watchlist) ? payload.watchlist : [];
    const notifications = ((payload.notifications as Record<string, unknown>)?.items ?? []) as Record<string, unknown>[];
    const report = [
      `# ${String(profile.nickname ?? profile.username ?? '用户')} 的投资报告`,
      `- 周期：${period}`,
      `- 生成时间：${payload.exportedAt}`,
      `- 风险偏好：${String(profile.riskLevel ?? '稳健')}`,
      `- 总资产：${String(summary.total_value ?? summary.totalValue ?? '-')}`,
      `- 总收益率：${String(metrics.totalReturn ?? 0)}`,
      `- 夏普比率：${String(metrics.sharpe ?? 0)}`,
      `- 最大回撤：${String(metrics.maxDrawdown ?? 0)}`,
      `- 自选分组数：${watchlist.length}`,
      `- 通知数：${notifications.length}`,
      ...(Array.isArray(payload.warnings) && payload.warnings.length > 0
        ? ['', '## 数据降级说明', ...payload.warnings.map((warning) => `- ${warning}`)]
        : []),
    ].join('\n');

    return {
      period,
      generatedAt: payload.exportedAt,
      report,
      sections: payload,
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      return { success: false, tool: name, error: error instanceof Error ? error.message : String(error) };
    }
  }

  private async resolveSection<T>(name: string, task: () => Promise<T>, fallback: T) {
    try {
      const data = await this.withTimeout(task(), ExportService.EXPORT_SECTION_TIMEOUT_MS, name);
      return { data, warning: null as string | null };
    } catch (error) {
      return {
        data: fallback,
        warning: `${name}: ${this.formatError(error)}`,
      };
    }
  }

  private async withTimeout<T>(promise: Promise<T>, timeoutMs: number, name: string): Promise<T> {
    return await new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`${name} timed out after ${timeoutMs}ms`)), timeoutMs);
      promise.then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        },
      );
    });
  }

  private formatError(error: unknown) {
    if (error instanceof Error) {
      return error.message;
    }
    return String(error);
  }
}
