import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class PaperTradingService {
  constructor(private readonly mcp: McpGatewayService) {}

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

  async navHistory(userId: string, accountId?: string, limit?: number) {
    return this.call('nav_history', { user_id: userId, account_id: accountId, limit: limit ?? 90 });
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
}
