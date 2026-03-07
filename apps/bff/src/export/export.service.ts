import { Injectable } from '@nestjs/common';
import { AuthService } from '../auth/auth.service';
import { PaperTradingService } from '../paper-trading/paper-trading.service';
import { WatchlistService } from '../watchlist/watchlist.service';
import { ResearchService } from '../research/research.service';
import { NotificationService } from '../notification/notification.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class ExportService {
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
      this.authService.getProfile(userId),
      this.paperTradingService.summary(userId),
      this.paperTradingService.positions(userId),
      this.paperTradingService.orders(userId),
      this.paperTradingService.performance(userId, undefined, 30),
      this.watchlistService.listGroups(userId),
      this.notificationService.list(userId, { limit: 100 }),
      this.researchService.getMarketNews(10),
      this.callTool('portfolio_manager', { action: 'list', kwargs: JSON.stringify({ user_id: userId }) }),
      this.callTool('alerts_manager', { action: 'list', kwargs: JSON.stringify({ user_id: userId, status: 'active' }) }),
    ]);

    return {
      exportedAt: new Date().toISOString(),
      profile,
      paperTrading: { summary, positions, orders, performance },
      watchlist,
      notifications,
      marketNews: news,
      portfolios,
      alerts,
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
}

