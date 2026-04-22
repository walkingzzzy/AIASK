import { Injectable } from '@nestjs/common';
import { BehaviorEventInput, BehaviorEventRecord, BehaviorStore } from './behavior.store';

export type BehaviorSummary = {
  summary: string;
  count: number;
  lastRoute: string | null;
  recentRoutes: string[];
  recentActions: string[];
};

@Injectable()
export class BehaviorService {
  constructor(private readonly behaviorStore: BehaviorStore) {}

  async append(userId: string, events: BehaviorEventInput[]) {
    return this.behaviorStore.append(userId, events);
  }

  async listByUser(
    userId: string,
    options: { limit?: number; days?: number; source?: string | null; pageKey?: string | null; eventType?: string | null } = {},
  ) {
    return this.behaviorStore.listByUser(userId, options);
  }

  async getRecentSummary(
    userId: string,
    options: { limit?: number; days?: number } = {},
  ): Promise<BehaviorSummary | null> {
    const events = await this.behaviorStore.listByUser(userId, {
      limit: options.limit ?? 20,
      days: options.days ?? 30,
    });
    if (!events.length) {
      return null;
    }

    const recentRoutes = this.unique(events.map((event) => event.route)).slice(0, 4);
    const recentActions = this.unique(events.map((event) => this.describeAction(event)).filter(Boolean)).slice(0, 5);
    const lastRoute = events[0]?.route ?? null;
    const summary = [
      `最近 ${events.length} 条前端语义事件中，最新页面是 ${lastRoute ?? '未知页面'}。`,
      recentRoutes.length ? `最近访问路径：${recentRoutes.join(' → ')}。` : '',
      recentActions.length ? `最近动作：${recentActions.join('；')}。` : '',
    ].filter(Boolean).join(' ');

    return {
      summary,
      count: events.length,
      lastRoute,
      recentRoutes,
      recentActions,
    };
  }

  async getEvidence(
    userId: string,
    options: { limit?: number; days?: number; source?: string | null; pageKey?: string | null; eventType?: string | null } = {},
  ): Promise<Array<Record<string, unknown>>> {
    const events = await this.behaviorStore.listByUser(userId, {
      limit: options.limit ?? 12,
      days: options.days ?? 30,
      source: options.source ?? null,
      pageKey: options.pageKey ?? null,
      eventType: options.eventType ?? null,
    });
    return events.map((event) => ({
      createdAt: event.createdAt,
      route: event.route,
      pageKey: event.pageKey,
      eventType: event.eventType,
      targetType: event.targetType,
      targetLabel: event.targetLabel,
      targetId: event.targetId,
      targetTestId: event.targetTestId,
      source: event.source,
      payload: event.payload,
    }));
  }

  private describeAction(event: BehaviorEventRecord) {
    const label = event.targetLabel ?? event.targetTestId ?? event.targetId ?? '';
    if (label) {
      return `${event.eventType}:${label}`;
    }
    return event.eventType;
  }

  private unique(values: string[]) {
    return values.filter((value, index) => value && values.indexOf(value) === index);
  }
}
