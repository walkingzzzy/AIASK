import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class PaperTradingService {
  constructor(private readonly mcp: McpGatewayService) { }

  private async call(action: string, params: Record<string, unknown> = {}) {
    try {
      const result = await this.mcp.callTool('paper_trading_manager', {
        action,
        kwargs: JSON.stringify(params),
      });
      if (result && typeof result === 'object') {
        const obj = result as Record<string, unknown>;
        if (obj.success === false) {
          throw new Error(String(obj.error || obj.message || `${action} 操作失败`));
        }
        if ('data' in obj) return obj.data;
      }
      return result;
    } catch (error) {
      if (error instanceof BadGatewayException) throw error;
      throw new BadGatewayException({
        success: false,
        message: `调用 paper_trading_manager.${action} 失败`,
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  async listAccounts(userId: string) {
    return this.call('list_accounts', { user_id: userId });
  }

  async summary(userId: string, accountId?: string) {
    return this.call('summary', { user_id: userId, account_id: accountId });
  }

  async positions(userId: string, accountId?: string) {
    return this.call('positions', { user_id: userId, account_id: accountId });
  }

  async orders(userId: string, accountId?: string) {
    return this.call('orders', { user_id: userId, account_id: accountId });
  }

  async orderEvents(userId: string, params: {
    order_id?: string; account_id?: string; limit?: number;
  } = {}) {
    return this.call('order_events', { user_id: userId, ...params });
  }

  async pendingOrders(userId: string, accountId?: string) {
    return this.call('pending_orders', { user_id: userId, account_id: accountId });
  }

  async placeOrder(userId: string, params: {
    code: string; direction: string; quantity: number;
    price?: number; order_type?: string; stop_price?: number;
    account_id?: string;
  }) {
    return this.call('place_order', { user_id: userId, ...params, shares: params.quantity });
  }

  async cancelOrder(userId: string, orderId: string) {
    return this.call('cancel_order', { user_id: userId, order_id: orderId });
  }

  async updatePrices(userId: string, accountId?: string) {
    return this.call('update_prices', { user_id: userId, account_id: accountId });
  }

  async navHistory(userId: string, accountId?: string, limit?: number) {
    return this.call('nav_history', { user_id: userId, account_id: accountId, limit: limit ?? 90 });
  }

  async performance(userId: string, accountId?: string, days = 30) {
    const [navPayload, orderPayload] = await Promise.all([
      this.navHistory(userId, accountId, days > 0 ? Math.max(days, 30) : 365),
      this.orders(userId, accountId),
    ]);

    const nav = Array.isArray((navPayload as Record<string, unknown>)?.nav)
      ? ((navPayload as Record<string, unknown>).nav as Record<string, unknown>[])
      : Array.isArray(navPayload) ? (navPayload as Record<string, unknown>[]) : [];
    const series = (days > 0 ? nav.slice(-days) : nav).map((item) => ({
      date: String(item.nav_date ?? item.date ?? ''),
      totalValue: Number(item.total_value ?? item.value ?? 0),
      dailyReturn: Number(item.daily_return ?? 0),
    }));

    const equityCurve = series.map((item) => item.totalValue);
    const dailyReturns = series.map((item) => item.dailyReturn);
    const totalReturn = equityCurve.length >= 2 && equityCurve[0] > 0
      ? (equityCurve[equityCurve.length - 1] - equityCurve[0]) / equityCurve[0]
      : 0;
    const mean = dailyReturns.length ? dailyReturns.reduce((sum, item) => sum + item, 0) / dailyReturns.length : 0;
    const variance = dailyReturns.length > 1
      ? dailyReturns.reduce((sum, item) => sum + (item - mean) ** 2, 0) / (dailyReturns.length - 1)
      : 0;
    const std = Math.sqrt(Math.max(variance, 0));
    const sharpe = std > 0 ? mean / std * Math.sqrt(252) : 0;

    let peak = equityCurve[0] ?? 0;
    let maxDrawdown = 0;
    equityCurve.forEach((value) => {
      peak = Math.max(peak, value);
      if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (value - peak) / peak);
    });

    const positiveDays = dailyReturns.filter((item) => item > 0).length;
    const winRate = dailyReturns.length ? positiveDays / dailyReturns.length : 0;

    const orders = Array.isArray((orderPayload as Record<string, unknown>)?.orders)
      ? ((orderPayload as Record<string, unknown>).orders as Record<string, unknown>[])
      : Array.isArray(orderPayload) ? (orderPayload as Record<string, unknown>[]) : [];
    const avgHoldDays = this.estimateAverageHoldDays(orders);

    return {
      dailyReturns: series,
      metrics: { totalReturn, sharpe, maxDrawdown, winRate, avgHoldDays },
    };
  }

  async matchingStatus() {
    return this.call('matching_status');
  }

  async navStatus() {
    return this.call('nav_status');
  }

  async realtimeSnapshot(userId: string, accountId?: string) {
    const [summary, positions, pendingOrders] = await Promise.all([
      this.summary(userId, accountId),
      this.positions(userId, accountId),
      this.pendingOrders(userId, accountId),
    ]);

    return {
      ts: new Date().toISOString(),
      account_id: accountId || (summary as Record<string, unknown>)?.account_id,
      summary,
      positions,
      pending_orders: pendingOrders,
    };
  }

  async setRiskRules(userId: string, params: {
    account_id?: string; max_position_pct?: number;
    max_drawdown_pct?: number; stop_loss_pct?: number;
  }) {
    return this.call('set_risk_rules', { user_id: userId, ...params });
  }

  // MCP Compliance Manager Integration
  async checkCompliance(userId: string, params: {
    code: string; direction: string; quantity: number;
    price?: number; account_id?: string;
  }) {
    try {
      const result = await this.mcp.callTool('compliance_manager', {
        action: 'check_order',
        kwargs: JSON.stringify({ user_id: userId, ...params }),
      });
      return { data: result };
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP compliance_manager (check_order) 失败',
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  // MCP Execution Manager Integration
  async routeExecution(userId: string, params: {
    code: string; direction: string; quantity: number;
    price?: number; urgency?: string;
  }) {
    try {
      const result = await this.mcp.callTool('execution_manager', {
        action: 'route_order',
        kwargs: JSON.stringify({ user_id: userId, ...params }),
      });
      return { data: result };
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP execution_manager (route_order) 失败',
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  async executionStatus(userId: string, executionId: string) {
    try {
      const result = await this.mcp.callTool('execution_manager', {
        action: 'execution_status',
        kwargs: JSON.stringify({ user_id: userId, execution_id: executionId }),
      });
      return { data: result };
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '调用 MCP execution_manager (execution_status) 失败',
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  private estimateAverageHoldDays(orders: Record<string, unknown>[]) {
    const buyQueues = new Map<string, number[]>();
    const holdDays: number[] = [];

    orders.forEach((item) => {
      const code = String(item.stock_code ?? item.code ?? '');
      const tradeType = String(item.trade_type ?? item.direction ?? '').toLowerCase();
      const tradeTime = new Date(String(item.trade_time ?? item.created_at ?? '')).getTime();
      if (!code || !Number.isFinite(tradeTime)) return;
      if (tradeType.includes('buy') || tradeType.includes('买')) {
        const queue = buyQueues.get(code) ?? [];
        queue.push(tradeTime);
        buyQueues.set(code, queue);
        return;
      }
      if (tradeType.includes('sell') || tradeType.includes('卖')) {
        const queue = buyQueues.get(code) ?? [];
        const openedAt = queue.shift();
        if (openedAt) holdDays.push(Math.max(1, (tradeTime - openedAt) / 86400000));
        buyQueues.set(code, queue);
      }
    });

    if (!holdDays.length) return 0;
    return holdDays.reduce((sum, item) => sum + item, 0) / holdDays.length;
  }
}
