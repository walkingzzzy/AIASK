'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import CollapsibleSectionCard from '@/components/collapsible-section-card';
import LightOverviewHero from '@/components/light-overview-hero';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { PageContainer, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { apiKeys } from '@/lib/query-keys';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

type NotificationType = 'alert' | 'signal' | 'trade' | 'system' | 'news';

type NotificationItem = {
  id: string;
  type: NotificationType;
  level: 'info' | 'warn' | 'error';
  title: string;
  body: string;
  read: boolean;
  createdAt: string;
};

const TYPE_ICONS: Record<string, string> = {
  alert: '警',
  signal: '策',
  trade: '交',
  system: '系',
  news: '讯',
  all: '总',
};

const TYPE_LABELS: Record<string, string> = {
  alert: '告警',
  signal: '信号',
  trade: '交易',
  system: '系统',
  news: '资讯',
  all: '全部',
};

const TEMPLATE_CARDS = [
  {
    key: 'alert',
    title: '价格/指标提醒',
    description: '当价格突破、均线拐头或指标触发时，优先把通知回流到通知中心。',
    href: '/alerts',
    cta: '去配置告警',
  },
  {
    key: 'signal',
    title: '策略信号通知',
    description: '把策略超市中关注的策略运行结果沉淀成固定消息入口，便于后续批量处理。',
    href: '/strategy-market',
    cta: '去策略超市',
  },
  {
    key: 'trade',
    title: '成交/回执提醒',
    description: '模拟交易的下单、成交和撤单结果适合作为交易类通知模板。',
    href: '/paper-trading',
    cta: '去模拟交易',
  },
  {
    key: 'system',
    title: '系统维护消息',
    description: '把维护、同步和异常告警集中到系统类通知，减少用户漏看。',
    href: '/settings',
    cta: '检查设置',
  },
] as const;

const SOURCE_LINKS: Record<NotificationType, string> = {
  alert: '/alerts',
  signal: '/strategy-market',
  trade: '/paper-trading',
  system: '/settings',
  news: '/research',
};

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)] disabled:cursor-not-allowed disabled:opacity-50';
const CHIP_BUTTON_CLS =
  'action-chip cursor-pointer text-xs text-text-primary disabled:cursor-not-allowed disabled:opacity-50';
const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const NOTIFICATION_INITIAL_VISIBLE = 8;

function readRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export default function NotificationsPage() {
  const [activeType, setActiveType] = useState<string>('all');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const listQ = useApiQuery<unknown>(`/notifications/list?limit=100`, {
    refetchInterval: 30000,
  });
  const markAllReadApi = useApiMutation<{ markedCount?: number }>({
    invalidates: [[...apiKeys.notifications()]],
    successToast: '通知已全部标记为已读',
  });
  const markReadApi = useApiMutation<{ markedCount?: number }>({
    invalidates: [[...apiKeys.notifications()]],
    successToast: false,
  });
  const deleteApi = useApiMutation<{ deletedCount?: number }>({
    invalidates: [[...apiKeys.notifications()]],
    successToast: '通知已删除',
  });

  const rawItems: NotificationItem[] = useMemo(() => {
    const data = readRecord(listQ.data);
    const nested = readRecord(data.data);
    const items = data.items ?? nested.items ?? [];
    return Array.isArray(items) ? (items as NotificationItem[]) : [];
  }, [listQ.data]);

  const items = useMemo(() => {
    return activeType === 'all' ? rawItems : rawItems.filter((i) => i.type === activeType);
  }, [rawItems, activeType]);

  const unreadCount = rawItems.filter((i) => !i.read).length;
  const actionError = markAllReadApi.error || markReadApi.error || deleteApi.error;
  const selectableIds = items.map((item) => item.id);
  const selectedCount = selectedIds.filter((id) => selectableIds.includes(id)).length;
  const allVisibleSelected = selectableIds.length > 0 && selectableIds.every((id) => selectedIds.includes(id));
  const currentTypeLabel = TYPE_LABELS[activeType] || activeType;
  const visibleUnreadCount = items.filter((item) => !item.read).length;
  const canMarkAllRead = unreadCount > 0;
  const latestNotification = rawItems[0]?.createdAt
    ? new Date(rawItems[0].createdAt).toLocaleString('zh-CN')
    : '暂无记录';
  const visibleItems = items.slice(0, NOTIFICATION_INITIAL_VISIBLE);
  const hiddenItems = items.slice(NOTIFICATION_INITIAL_VISIBLE);
  const heroNotes = [
    '先用分类筛掉噪音，再做批量已读或删除，通知中心应该先帮助你降噪，而不是继续堆积信息。',
    '交易类和告警类消息更适合优先处理，系统类与资讯类则更适合作为回看资料。',
    '模板区负责决定通知从哪里进入，列表区负责决定下一步去哪一个工作台继续处理。',
  ];

  const handleMarkAllRead = async () => {
    try {
      await markAllReadApi.triggerAsync('/notifications/mark-all-read', { method: 'POST' });
      listQ.refetch();
    } catch {
      /* ignore */
    }
  };

  const handleMarkRead = async (ids: string[]) => {
    try {
      await markReadApi.triggerAsync('/notifications/mark-read', { method: 'POST' }, { ids });
      listQ.refetch();
    } catch {
      /* ignore */
    }
  };

  const handleDelete = async (ids: string[]) => {
    try {
      await deleteApi.triggerAsync('/notifications/delete', { method: 'DELETE' }, { ids });
      listQ.refetch();
    } catch {
      /* ignore */
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((itemId) => itemId !== id) : [...prev, id]));
  };

  const toggleSelectAllVisible = () => {
    setSelectedIds((prev) => {
      if (allVisibleSelected) return prev.filter((id) => !selectableIds.includes(id));
      return Array.from(new Set([...prev, ...selectableIds]));
    });
  };

  const handleBatchMarkRead = async () => {
    const targetIds = selectedIds.filter((id) => selectableIds.includes(id));
    if (targetIds.length === 0) return;
    await handleMarkRead(targetIds);
    setSelectedIds((prev) => prev.filter((id) => !targetIds.includes(id)));
  };

  const handleBatchDelete = async () => {
    const targetIds = selectedIds.filter((id) => selectableIds.includes(id));
    if (targetIds.length === 0) return;
    await handleDelete(targetIds);
    setSelectedIds((prev) => prev.filter((id) => !targetIds.includes(id)));
  };
  const notificationsActions = [
    {
      id: 'notifications.mark-all-read',
      label: '全部标记已读',
      description: '把所有未读通知统一收口到已读队列',
      keywords: ['通知', '已读'],
      scope: 'page' as const,
      pageKey: 'notifications',
      run: async () => {
        await handleMarkAllRead();
        return { message: '已处理全部未读通知' };
      },
    },
    {
      id: 'notifications.refresh',
      label: '刷新通知',
      description: '重新拉取最新通知流',
      keywords: ['通知', '刷新'],
      scope: 'page' as const,
      pageKey: 'notifications',
      run: async () => {
        await listQ.refetch();
        return { message: '已刷新通知列表' };
      },
    },
    {
      id: 'notifications.filter-alerts',
      label: '只看告警',
      description: '优先聚焦告警类消息',
      keywords: ['告警', '筛选'],
      scope: 'page' as const,
      pageKey: 'notifications',
      run: () => {
        setActiveType('alert');
        return { message: '已切到告警通知' };
      },
    },
  ];
  usePageActions(notificationsActions);
  const notificationsSummary = `当前筛选 ${currentTypeLabel}，总通知 ${rawItems.length} 条，未读 ${unreadCount} 条，可见未读 ${visibleUnreadCount} 条，已选 ${selectedCount} 条。`;
  const notificationsResult = buildLocalResultContract({
    summary: notificationsSummary,
    availableViews: rawItems.length > 1 ? ['compare'] : [],
    pageActions: notificationsActions,
    preferredActionIds: ['notifications.mark-all-read', 'notifications.refresh', 'notifications.filter-alerts'],
    recommendedLinks: [
      { id: 'notifications-link-alerts', label: '告警中心', href: '/alerts' },
      { id: 'notifications-link-strategy', label: '策略超市', href: '/strategy-market' },
      { id: 'notifications-link-paper', label: '模拟交易', href: '/paper-trading' },
      { id: 'notifications-link-research', label: '研究页', href: '/research' },
    ],
    evidence: [
      { label: '总通知', value: String(rawItems.length) },
      { label: '当前筛选', value: currentTypeLabel },
      { label: '未读', value: String(unreadCount), tone: unreadCount > 0 ? 'warning' : 'neutral' },
      { label: '可见未读', value: String(visibleUnreadCount) },
      { label: '已选', value: String(selectedCount) },
    ],
    riskNotes: [
      ...(actionError ? [actionError] : []),
      ...(unreadCount === 0 ? ['当前没有未读通知。'] : []),
      ...(selectedCount === 0 ? ['当前还没有选中批量处理项。'] : []),
    ],
    freshness: rawItems[0]?.createdAt ? { updatedAt: rawItems[0].createdAt, label: '最近通知' } : null,
    platformMeta: {
      sourceTool: 'notifications',
      sourceChain: ['notifications-center'],
      degraded: Boolean(actionError || listQ.error),
      fallbackReason: [actionError, listQ.error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('notifications', `复查通知中心 · ${currentTypeLabel}`, '/notifications', 'notification-review', {
      activeType,
      unreadCount,
      selectedCount,
    }),
  });
  usePageContext({
    pageKey: 'notifications',
    title: '通知中心工作台',
    summary: notificationsSummary,
    objectType: 'notification-stream',
    objectId: activeType,
    resultType: 'notification-center',
    tags: [currentTypeLabel, `${unreadCount} 条未读`, `${selectedCount} 条已选`],
    suggestions: [
      '总结当前通知中心最该先处理哪一类消息',
      '如果要降噪，先看哪种分类最有效',
      '解释为什么通知处理不应该停在“已看到”',
    ],
    recommendedActions: notificationsResult.recommendedActions ?? [],
    recommendedLinks: notificationsResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(notificationsResult.evidence),
    riskNotes: notificationsResult.riskNotes ?? [],
    freshness: notificationsResult.freshness ?? null,
    raw: {
      activeType,
      total: rawItems.length,
      unreadCount,
      visibleUnreadCount,
      selectedCount,
    },
  });

  const renderNotificationCard = (item: NotificationItem) => {
    const selected = selectedIds.includes(item.id);
    const sourceHref = SOURCE_LINKS[item.type];
    return (
      <article
        key={item.id}
        className={`rounded-[28px] border p-4 shadow-[0_24px_50px_-34px_rgba(15,23,42,0.35)] backdrop-blur-2xl transition hover:-translate-y-0.5 hover:border-primary/28 ${
          selected
            ? 'border-primary/28 bg-[linear-gradient(160deg,rgba(47,140,255,0.16),rgba(255,255,255,0.26))] ring-1 ring-primary/30'
            : !item.read
              ? 'border-primary/20 bg-[linear-gradient(160deg,rgba(255,255,255,0.44),rgba(238,247,255,0.34))]'
              : 'border-white/50 bg-[linear-gradient(160deg,rgba(255,255,255,0.38),rgba(255,255,255,0.16))]'
        }`}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 gap-3">
            <label className="mt-1 flex items-center">
              <input
                type="checkbox"
                checked={selected}
                onChange={() => toggleSelect(item.id)}
                aria-label={`选择通知 ${item.title}`}
              />
            </label>
            <div className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-[18px] border border-white/55 bg-white/42 text-sm font-semibold text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
              {TYPE_ICONS[item.type] || '总'}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="info">{TYPE_LABELS[item.type]}</Badge>
                <Badge variant={item.level === 'error' ? 'danger' : item.level === 'warn' ? 'warning' : 'neutral'}>
                  {item.level}
                </Badge>
                {!item.read ? <Badge variant="warning">未读</Badge> : <Badge variant="success">已处理</Badge>}
              </div>
              <h3 className={`mb-0 mt-3 text-base font-semibold ${item.read ? 'text-text-primary/80' : 'text-text-primary'}`}>
                {item.title}
              </h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{item.body}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-text-secondary">
                <span className="rounded-full border border-white/55 bg-white/34 px-3 py-1">
                  {new Date(item.createdAt).toLocaleString('zh-CN')}
                </span>
                <span className="rounded-full border border-white/55 bg-white/28 px-3 py-1">
                  {item.read ? '已进入回看队列' : '等待你决定下一步动作'}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 lg:w-[240px] lg:justify-end">
            <Link href={sourceHref} className={LINK_CHIP_CLS}>
              查看来源页
            </Link>
            {!item.read ? (
              <button
                type="button"
                onClick={() => handleMarkRead([item.id])}
                disabled={markReadApi.isPending}
                className={CHIP_BUTTON_CLS}
              >
                标记已读
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => handleDelete([item.id])}
              disabled={deleteApi.isPending}
              className={CHIP_BUTTON_CLS}
            >
              删除
            </button>
          </div>
        </div>
      </article>
    );
  };

  return (
    <PageContainer className="app-theme-market space-y-4">
      <LightOverviewHero
        eyebrow="Notification Workspace"
        title="通知中心工作台"
        summary="先筛选降噪，再做批量处理，最后跳回告警、策略、交易或研究页面继续动作。默认只展示摘要、筛选和部分消息流。"
        badges={(
          <>
            <Badge variant="info">{currentTypeLabel}</Badge>
            <Badge variant={unreadCount > 0 ? 'warning' : 'success'}>
              {unreadCount > 0 ? `${unreadCount} 条未读` : '全部已处理'}
            </Badge>
          </>
        )}
        actions={(
          <>
            <button
              type="button"
              onClick={handleMarkAllRead}
              disabled={!canMarkAllRead || markAllReadApi.isPending}
              data-testid="page-primary-action"
              data-action-testid="notifications-mark-all-read-action"
              className={HERO_PRIMARY_BUTTON_CLS}
            >
              {markAllReadApi.isPending ? '处理中...' : '全部标记已读'}
            </button>
            <button
              type="button"
              onClick={() => listQ.refetch()}
              disabled={listQ.isFetching}
              className={HERO_SECONDARY_BUTTON_CLS}
            >
              {listQ.isFetching ? '刷新中...' : '刷新通知'}
            </button>
            <Link href="/alerts" className={LINK_CHIP_CLS}>
              去告警中心
            </Link>
          </>
        )}
        status={(
          <div
            data-testid="page-primary-status"
            className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前筛选 {currentTypeLabel} ｜ 未读 {visibleUnreadCount} 条 ｜ 已选 {selectedCount} 条
            </div>
            <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
              {canMarkAllRead
                ? '主动作会把所有未读消息统一收口到已读队列。'
                : '当前没有未读消息，主动作保持禁用但位置固定。'}
            </p>
          </div>
        )}
        metrics={[
          { key: 'notifications-total', label: '通知总数', value: String(rawItems.length) },
          { key: 'notifications-filter', label: '当前筛选', value: currentTypeLabel, hint: `${items.length} 条可见通知` },
          { key: 'notifications-unread', label: '待处理', value: String(visibleUnreadCount) },
          { key: 'notifications-latest', label: '最近更新', value: latestNotification },
        ]}
        compact
        detailsTitle="展开处理建议与上游入口"
        detailsContent={(
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              {heroNotes.map((note) => (
                <div key={note} className={NOTE_CARD_CLS}>
                  {note}
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/paper-trading" className={LINK_CHIP_CLS}>
                模拟交易
              </Link>
              <Link href="/research" className={LINK_CHIP_CLS}>
                研究页
              </Link>
              <Link href="/settings" className={LINK_CHIP_CLS}>
                系统设置
              </Link>
              <Link href="/notifications" className={LINK_CHIP_CLS}>
                当前消息流
              </Link>
            </div>
          </div>
        )}
      />

      <ProgressiveWorkbenchSection pageKey="notifications" title="通知结果工作台" result={notificationsResult} summaryMode="strip" />

      {actionError ? (
        <div className="rounded-[22px] border border-danger/20 bg-[linear-gradient(180deg,rgba(217,45,32,0.12),rgba(255,255,255,0.52))] p-4 text-sm text-danger shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-xl">
          {actionError}
        </div>
      ) : null}

      <CollapsibleSectionCard
        title="筛选区"
        summary="通知筛选现在被抬升为主控制区。先收窄类别，再决定是否批量已读、删除。"
        defaultOpen
        badge={<Badge variant="neutral">{selectedCount > 0 ? `已选 ${selectedCount} 条` : '未选中消息'}</Badge>}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">Filter Deck</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">先筛选，再处理通知</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              通知筛选现在被抬升为主控制区。你可以先收窄到某个类别，再决定是否批量已读、删除，或者进入对应来源页面继续跟进。
            </p>
          </div>
          <Badge variant="neutral">{selectedCount > 0 ? `已选 ${selectedCount} 条` : '未选中消息'}</Badge>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {['all', 'alert', 'signal', 'trade', 'system', 'news'].map((t) => {
            const count = t === 'all' ? rawItems.length : rawItems.filter((i) => i.type === t).length;
            const active = activeType === t;
            return (
              <button
                key={t}
                type="button"
                onClick={() => {
                  setActiveType(t);
                  setSelectedIds([]);
                }}
                className={`action-chip cursor-pointer text-sm transition ${
                  active ? 'border-primary/30 bg-primary/10 text-primary' : 'text-text-secondary'
                }`}
              >
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-white/55 bg-white/35 text-[11px] font-semibold">
                  {TYPE_ICONS[t] || '总'}
                </span>
                <span>{TYPE_LABELS[t] || t}</span>
                <span className="text-xs">({count})</span>
              </button>
            );
          })}
        </div>
      </CollapsibleSectionCard>

      <CollapsibleSectionCard
        title="通知模板与批量处理"
        summary="模板区负责决定消息从哪里来，批量按钮负责清理当前视野。默认按需展开。"
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="eyebrow">Action Deck</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">通知模板与批量处理</h2>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                上半区负责决定消息从哪里来，下半区负责决定现在怎么处理它们。模板卡片帮助你补齐来源，批量按钮帮助你快速清理视野。
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <button
                type="button"
                onClick={toggleSelectAllVisible}
                disabled={selectableIds.length === 0}
                className={CHIP_BUTTON_CLS}
              >
                {allVisibleSelected ? '取消全选当前筛选' : '选中当前筛选'}
              </button>
              <button
                type="button"
                disabled={selectedCount === 0 || markReadApi.isPending}
                onClick={handleBatchMarkRead}
                className={CHIP_BUTTON_CLS}
              >
                批量已读 ({selectedCount})
              </button>
              <button
                type="button"
                disabled={selectedCount === 0 || deleteApi.isPending}
                onClick={handleBatchDelete}
                className={CHIP_BUTTON_CLS}
              >
                批量删除 ({selectedCount})
              </button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {TEMPLATE_CARDS.map((card, index) => (
              <div
                key={card.key}
                className="rounded-[24px] border border-white/50 bg-[linear-gradient(160deg,rgba(255,255,255,0.42),rgba(255,255,255,0.18))] p-4 shadow-[0_22px_44px_-34px_rgba(15,23,42,0.35)] backdrop-blur-xl"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-text-primary">{card.title}</div>
                  <span className="rounded-full border border-white/55 bg-white/35 px-2 py-1 text-[11px] font-semibold text-text-muted">
                    0{index + 1}
                  </span>
                </div>
                <p className="mb-0 mt-3 min-h-[72px] text-xs leading-6 text-text-secondary">{card.description}</p>
                <Link href={card.href} className={`${LINK_CHIP_CLS} mt-4 inline-flex`}>
                  {card.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </CollapsibleSectionCard>

      <CollapsibleSectionCard
        title="通知流与逐条处理区"
        summary={`默认先展示前 ${visibleItems.length} 条消息，其余消息折叠到附加区。`}
        defaultOpen
        badge={<Badge variant={visibleUnreadCount > 0 ? 'warning' : 'success'}>{visibleUnreadCount > 0 ? `${visibleUnreadCount} 条待处理` : '当前筛选已清空'}</Badge>}
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">Message Stream</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">通知流与逐条处理区</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              这里保留了逐条处理能力，但阅读顺序重新组织成卡片流。每条消息都同时告诉你来源类别、风险等级、时间和下一步动作，不再只是裸文本堆叠。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={visibleUnreadCount > 0 ? 'warning' : 'success'}>
              {visibleUnreadCount > 0 ? `${visibleUnreadCount} 条待处理` : '当前筛选已清空'}
            </Badge>
            <Badge variant="neutral">{currentTypeLabel}</Badge>
          </div>
        </div>

        {items.length === 0 ? (
          <div className="mt-5 rounded-[28px] border border-dashed border-glass-border bg-white/28 p-6 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]">
            <p className="m-0 text-sm font-medium text-text-primary">
              暂无{activeType === 'all' ? '' : TYPE_LABELS[activeType]}通知
            </p>
            <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
              可以先去告警中心、策略超市或模拟交易页面创建上游触发源，让通知页真正承担“统一接单”的角色。
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              <Link href="/alerts" className={LINK_CHIP_CLS}>
                去告警中心
              </Link>
              <Link href="/strategy-market" className={LINK_CHIP_CLS}>
                去策略超市
              </Link>
              <Link href="/paper-trading" className={LINK_CHIP_CLS}>
                去模拟交易
              </Link>
            </div>
            <div className="mt-4 text-[11px] text-text-secondary/70">
              常见触发源：价格/技术指标告警、策略运行结果、模拟交易成交、系统维护通知
            </div>
          </div>
        ) : (
          <div className="mt-5 space-y-3">
            {visibleItems.map((item) => renderNotificationCard(item))}
            {hiddenItems.length > 0 ? (
              <details className="rounded-[24px] border border-white/45 bg-white/20 p-4">
                <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
                  展开剩余 {hiddenItems.length} 条通知
                </summary>
                <div className="mt-4 space-y-3">
                  {hiddenItems.map((item) => renderNotificationCard(item))}
                </div>
              </details>
            ) : null}
          </div>
        )}
      </CollapsibleSectionCard>
    </PageContainer>
  );
}
