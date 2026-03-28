import { BadGatewayException, Injectable } from '@nestjs/common';
import type {
  EventImportantItem,
  EventImportantResponse,
  EventSubscriptionMutationResponse,
  EventSubscriptionItem,
  EventSubscriptionsResponse,
  EventTimelineDirection,
  EventTimelineItem,
  EventTimelineResponse,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { NotificationService } from '../notification/notification.service';
import { WatchlistService } from '../watchlist/watchlist.service';

export type EventPreferences = {
  frequency: 'realtime' | 'daily' | 'weekly';
  eventTypes: string[];
  minImportance: number;
  updatedAt: string;
};

const DEFAULT_PREFERENCES: Omit<EventPreferences, 'updatedAt'> = {
  frequency: 'daily',
  eventTypes: ['notice', 'report', 'dividend', 'ipo', 'news'],
  minImportance: 2,
};

@Injectable()
export class EventService {
  private static readonly SUBSCRIPTION_GROUP_ID = 'event_subscriptions';
  private static readonly SUBSCRIPTION_GROUP_NAME = '事件订阅';

  /** 内存级用户偏好存储（生产环境应替换为 DB 持久化） */
  private readonly preferencesStore = new Map<string, EventPreferences>();

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly watchlistService: WatchlistService,
    private readonly notificationService: NotificationService,
  ) {}

  async getPreferences(userId: string): Promise<EventPreferences> {
    return this.preferencesStore.get(userId) ?? {
      ...DEFAULT_PREFERENCES,
      updatedAt: new Date().toISOString(),
    };
  }

  async updatePreferences(
    userId: string,
    patch: Partial<Omit<EventPreferences, 'updatedAt'>>,
  ): Promise<EventPreferences> {
    const current = await this.getPreferences(userId);
    const next: EventPreferences = {
      frequency: patch.frequency ?? current.frequency,
      eventTypes: patch.eventTypes ?? current.eventTypes,
      minImportance: patch.minImportance ?? current.minImportance,
      updatedAt: new Date().toISOString(),
    };
    this.preferencesStore.set(userId, next);
    return next;
  }

  async byCode(code: string, limit = 20): Promise<EventTimelineResponse> {
    const normalizedCode = code.trim();
    const normalizedLimit = Math.min(Math.max(limit, 1), 50);
    const params = { code: normalizedCode, limit: normalizedLimit };
    const payload = await this.callManager('get_by_code', params);
    const record = this.extractDataRecord(payload);
    const events = this.normalizeEvents(this.asRecordArray(record.events), 'stock');

    return {
      scope: 'stock',
      code: normalizedCode,
      count: events.length,
      limit: normalizedLimit,
      highlights: this.buildHighlights(events, 'stock'),
      fallbackUsed: Boolean(record.fallback_used ?? record.fallbackUsed),
      source: this.toStringValue(record.source),
      sourceChain: this.toStringArray(record.source_chain ?? record.sourceChain),
      events,
      sourceTool: 'event_manager',
      argsMatched: { action: 'get_by_code', params },
      result: payload,
    };
  }

  async calendar(days = 7, type = 'all'): Promise<EventTimelineResponse> {
    const normalizedDays = Math.min(Math.max(days, 1), 90);
    const normalizedType = String(type || 'all').trim() || 'all';
    const params = { days: normalizedDays, type: normalizedType };
    const payload = await this.callManager('upcoming_events', params);
    const record = this.extractDataRecord(payload);
    const events = this.normalizeEvents(this.asRecordArray(record.events), 'market');

    return {
      scope: 'market',
      count: events.length,
      days: normalizedDays,
      type: normalizedType,
      highlights: this.buildHighlights(events, 'market'),
      source: this.toStringValue(record.source),
      sourceChain: this.toStringArray(record.source_chain ?? record.sourceChain),
      events,
      sourceTool: 'event_manager',
      argsMatched: { action: 'upcoming_events', params },
      result: payload,
    };
  }

  async subscriptions(userId: string): Promise<EventSubscriptionsResponse> {
    const groups = await this.watchlistService.listGroups(userId);
    const group = groups.find((item) =>
      item.id === EventService.SUBSCRIPTION_GROUP_ID
      || item.name === EventService.SUBSCRIPTION_GROUP_NAME,
    );

    const items = (group?.items ?? []).map<EventSubscriptionItem>((item) => ({
      code: item.code,
      name: item.name || null,
      groupId: group?.id ?? EventService.SUBSCRIPTION_GROUP_ID,
      groupName: group?.name ?? EventService.SUBSCRIPTION_GROUP_NAME,
      addedAt: item.addedAt,
    }));

    return {
      groupId: group?.id ?? EventService.SUBSCRIPTION_GROUP_ID,
      groupName: group?.name ?? EventService.SUBSCRIPTION_GROUP_NAME,
      count: items.length,
      items,
      sourceTool: 'watchlist_manager',
      argsMatched: {
        userId,
        groupId: group?.id ?? EventService.SUBSCRIPTION_GROUP_ID,
      },
      result: group ?? null,
    };
  }

  async subscribe(userId: string, code: string, name?: string | null) {
    const normalizedCode = code.trim();
    const subscriptions = await this.subscriptions(userId);
    const existing = subscriptions.items.find((item) => item.code === normalizedCode);

    if (existing) {
      return {
        subscribed: true,
        alreadySubscribed: true,
        item: existing,
        message: `${normalizedCode} 已在事件订阅列表中`,
      };
    }

    await this.ensureSubscriptionGroup(userId, subscriptions.groupId, subscriptions.groupName, subscriptions.result != null);
    await this.watchlistService.addStocks(
      userId,
      EventService.SUBSCRIPTION_GROUP_ID,
      [normalizedCode],
      EventService.SUBSCRIPTION_GROUP_NAME,
    );

    await this.notificationService.create({
      userId,
      type: 'news',
      level: 'info',
      title: '事件订阅已更新',
      body: `已订阅 ${name?.trim() || normalizedCode} 的重点事件跟踪`,
      source: 'event.subscribe',
      meta: {
        code: normalizedCode,
        groupId: EventService.SUBSCRIPTION_GROUP_ID,
      },
    });

    const nextSubscriptions = await this.subscriptions(userId);
    const item = nextSubscriptions.items.find((entry) => entry.code === normalizedCode) ?? {
      code: normalizedCode,
      name: name?.trim() || null,
      groupId: nextSubscriptions.groupId,
      groupName: nextSubscriptions.groupName,
      addedAt: new Date().toISOString(),
    };

    return {
      subscribed: true,
      alreadySubscribed: false,
      item,
      message: `已订阅 ${name?.trim() || normalizedCode} 的事件`,
    };
  }

  async unsubscribe(userId: string, code: string): Promise<EventSubscriptionMutationResponse> {
    const normalizedCode = code.trim();
    const subscriptions = await this.subscriptions(userId);
    const existing = subscriptions.items.find((item) => item.code === normalizedCode);

    if (!existing) {
      return {
        subscribed: false,
        alreadySubscribed: false,
        removed: false,
        item: null,
        message: `${normalizedCode} 当前不在事件订阅列表中`,
      };
    }

    await this.watchlistService.removeStock(userId, subscriptions.groupId, normalizedCode);

    await this.notificationService.create({
      userId,
      type: 'news',
      level: 'info',
      title: '事件订阅已更新',
      body: `已取消订阅 ${existing.name?.trim() || normalizedCode} 的重点事件跟踪`,
      source: 'event.unsubscribe',
      meta: {
        code: normalizedCode,
        groupId: subscriptions.groupId,
      },
    });

    return {
      subscribed: false,
      alreadySubscribed: false,
      removed: true,
      item: existing,
      message: `已取消订阅 ${existing.name?.trim() || normalizedCode} 的事件`,
    };
  }

  async important(userId: string, days = 7, limit = 12): Promise<EventImportantResponse> {
    const normalizedDays = Math.min(Math.max(days, 1), 30);
    const normalizedLimit = Math.min(Math.max(limit, 1), 30);
    const [calendar, subscriptions] = await Promise.all([
      this.calendar(normalizedDays, 'all'),
      this.subscriptions(userId),
    ]);

    const subscribedCodes = subscriptions.items.map((item) => item.code).filter((item) => item.length > 0);
    const stockResults = await Promise.allSettled(
      subscribedCodes.slice(0, Math.min(normalizedLimit, 12)).map((code) => this.byCode(code, 8)),
    );

    const stockEvents = stockResults.flatMap((result) => {
      if (result.status !== 'fulfilled') return [];
      return result.value.events
        .filter((item) => item.direction !== 'past' || item.importance === 'high')
        .map<EventImportantItem>((item) => ({
          ...item,
          scope: 'stock',
          subscribed: true,
          reasons: this.buildImportantReasons(item, true),
        }));
    });

    const marketEvents = calendar.events.map<EventImportantItem>((item) => ({
      ...item,
      scope: 'market',
      subscribed: false,
      reasons: this.buildImportantReasons(item, false),
    }));

    const deduped = new Map<string, EventImportantItem>();
    [...stockEvents, ...marketEvents].forEach((item) => {
      const key = [
        item.scope,
        item.code ?? '',
        item.eventType,
        item.title,
        item.eventDate ?? '',
      ].join('::');
      const current = deduped.get(key);
      if (!current || this.scoreImportantItem(item) > this.scoreImportantItem(current)) {
        deduped.set(key, item);
      }
    });

    const ranked = Array.from(deduped.values())
      .sort((left, right) => this.scoreImportantItem(right) - this.scoreImportantItem(left))
      .slice(0, normalizedLimit)
      .map((item, index) => ({ ...item, rank: index + 1 }));

    return {
      days: normalizedDays,
      limit: normalizedLimit,
      count: ranked.length,
      subscriptionCount: subscriptions.count,
      highlights: ranked.slice(0, 3).map((item) => `${item.code ? `${item.code} ` : ''}${item.title}`),
      items: ranked,
      sourceTools: {
        calendar: 'event_manager',
        subscriptions: 'watchlist_manager',
        stockEvents: subscribedCodes.length > 0 ? 'event_manager' : undefined,
      },
      argsMatched: {
        userId,
        days: normalizedDays,
        limit: normalizedLimit,
        subscribedCodes: subscribedCodes.slice(0, Math.min(subscribedCodes.length, 12)),
      },
      result: {
        calendar,
        subscriptions,
        stockResults: stockResults.map((result) => result.status === 'fulfilled' ? result.value : { error: String(result.reason) }),
      },
    };
  }

  private async callManager(action: string, params: Record<string, unknown>) {
    try {
      const result = await this.mcpGatewayService.callTool('event_manager', {
        action,
        kwargs: JSON.stringify(params),
      });
      const toolError = this.extractToolError(result);
      if (toolError) {
        throw new Error(toolError);
      }
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP event_manager.${action} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private buildHighlights(events: EventTimelineItem[], scope: 'stock' | 'market') {
    if (events.length === 0) {
      return [scope === 'stock' ? '当前标的暂无可展示事件。' : '当前时间窗口暂无市场事件。'];
    }

    return events.slice(0, 3).map((item) => {
      const prefix = item.eventDate ? `${item.eventDate} ` : '';
      return `${prefix}${item.title}`;
    });
  }

  private buildImportantReasons(item: EventTimelineItem, subscribed: boolean) {
    const reasons: string[] = [];
    if (subscribed) reasons.push('已订阅标的');
    if (item.direction === 'today') reasons.push('今日事件');
    else if (item.direction === 'upcoming') reasons.push('即将发生');
    if (item.importance === 'high') reasons.push('高优先级');
    if (!reasons.length) reasons.push('市场观察');
    return reasons;
  }

  private scoreImportantItem(item: EventImportantItem) {
    const importanceScore = item.importance === 'high' ? 300 : item.importance === 'medium' ? 200 : 100;
    const directionScore = item.direction === 'today' ? 90 : item.direction === 'upcoming' ? 60 : 20;
    const subscriptionScore = item.subscribed ? 40 : 0;
    const typeScore = String(item.eventType || '').toLowerCase().includes('notice') ? 20 : 0;
    return importanceScore + directionScore + subscriptionScore + typeScore + this.toTime(item.eventDate);
  }

  private async ensureSubscriptionGroup(
    userId: string,
    groupId: string,
    groupName: string,
    exists: boolean,
  ) {
    if (exists) return;
    await this.watchlistService.createGroup(
      userId,
      groupId || EventService.SUBSCRIPTION_GROUP_ID,
      groupName || EventService.SUBSCRIPTION_GROUP_NAME,
      '#ea580c',
    );
  }

  private normalizeEvents(rows: Record<string, unknown>[], scope: 'stock' | 'market'): EventTimelineItem[] {
    const sorted = [...rows].sort((left, right) => {
      const leftTime = this.toTime(left.event_date ?? left.eventDate ?? left.date);
      const rightTime = this.toTime(right.event_date ?? right.eventDate ?? right.date);
      return scope === 'market' ? leftTime - rightTime : rightTime - leftTime;
    });

    return sorted.map((row, index) => {
      const eventType = this.toStringValue(row.event_type ?? row.eventType) ?? 'event';
      const eventDate = this.toStringValue(row.event_date ?? row.eventDate ?? row.date);
      const source = this.toStringValue(row.source ?? row.institution ?? row.org_name);
      const summary = this.toStringValue(row.summary ?? row.content ?? row.description ?? row.remark);
      const direction = this.resolveDirection(eventDate);
      const importance = this.resolveImportance(eventType, direction);
      const code = this.toStringValue(row.code);

      return {
        id: this.toStringValue(row.id) ?? `${code ?? scope}-${eventType}-${eventDate ?? index}`,
        code,
        eventType,
        title: this.toStringValue(row.title ?? row.name ?? row.notice_title ?? row.report_title) ?? `事件 ${index + 1}`,
        eventDate,
        source,
        url: this.toStringValue(row.url ?? row.link),
        summary,
        direction,
        importance,
        tags: [eventType, direction, source].filter((item): item is string => Boolean(item)),
        raw: row,
      };
    });
  }

  private resolveDirection(eventDate: string | null): EventTimelineDirection {
    if (!eventDate) return 'past';
    const eventDay = eventDate.slice(0, 10);
    const today = new Date().toISOString().slice(0, 10);
    if (eventDay === today) return 'today';
    return eventDay > today ? 'upcoming' : 'past';
  }

  private resolveImportance(
    eventType: string,
    direction: EventTimelineDirection,
  ): 'high' | 'medium' | 'low' {
    const normalizedType = eventType.toLowerCase();
    if (
      direction === 'today'
      || normalizedType.includes('earning')
      || normalizedType.includes('notice')
      || normalizedType.includes('dividend')
      || normalizedType.includes('重组')
    ) {
      return 'high';
    }
    if (direction === 'upcoming' || normalizedType.includes('research') || normalizedType.includes('news')) {
      return 'medium';
    }
    return 'low';
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      return /error executing tool|validation error/i.test(payload) ? payload : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.success === false) {
      return String(record.error ?? record.message ?? 'event manager error');
    }
    if (typeof record.data === 'string' && /error executing tool|validation error/i.test(record.data)) {
      return record.data;
    }
    return null;
  }

  private extractDataRecord(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return {};
    }
    const record = payload as Record<string, unknown>;
    const data = record.data;
    return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : record;
  }

  private asRecordArray(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) return [];
    return value
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  }

  private toStringValue(value: unknown): string | null {
    if (value == null) return null;
    const text = String(value).trim();
    return text ? text : null;
  }

  private toStringArray(value: unknown) {
    return Array.isArray(value)
      ? value.map((item) => String(item).trim()).filter((item) => item.length > 0)
      : [];
  }

  private toTime(value: unknown) {
    const text = this.toStringValue(value);
    if (!text) return 0;
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : 0;
  }
}
