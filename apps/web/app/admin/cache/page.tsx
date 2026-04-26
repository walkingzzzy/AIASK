'use client';

import Link from 'next/link';
import { useCallback, useState, useMemo } from 'react';
import ResultWorkbench from '@/components/result-workbench';
import { PageContainer, SectionCard, KpiGrid, KpiCard } from '@/components/ui';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { EmptyState, ErrorState } from '@/components/status-state';
import { isPermissionDeniedErrorMessage } from '@/lib/api';
import { apiKeys } from '@/lib/query-keys';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

/**
 * T-050: Cache Management Panel
 */
export default function CachePage() {
  const [clearing, setClearing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<{ prefix?: string; label: string } | null>(null);
  const [dangerAck, setDangerAck] = useState(false);
  const [lastStatsRefreshAt, setLastStatsRefreshAt] = useState<string | null>(null);
  const [clearReceipt, setClearReceipt] = useState<{
    label: string;
    clearedAt: string;
    fullClear: boolean;
    statsRefreshed: boolean;
  } | null>(null);

  const cacheQ = useApiQuery<unknown>('/admin/cache-stats', {
    refetchInterval: 10000,
    parse: (raw) => raw,
  });
  const clearApi = useApiMutation<unknown>({
    invalidates: [[...apiKeys.admin()]],
    successToast: '缓存已清理',
  });

  const stats = useMemo(() => {
    const raw = (cacheQ.data ?? {}) as Record<string, unknown>;
    const prefixes = Array.isArray(raw.prefixes) ? raw.prefixes : [];
    return {
      hitRate: Number(raw.hitRate ?? 0),
      totalKeys: Number(raw.totalKeys ?? 0),
      memoryUsed: String(raw.memoryUsed ?? '0 MB'),
      hits: Number(raw.hits ?? 0),
      misses: Number(raw.misses ?? 0),
      prefixes: prefixes.map((p: Record<string, unknown>) => ({
        prefix: String(p.prefix ?? ''),
        count: Number(p.count ?? 0),
        hitRate: Number(p.hitRate ?? 0),
      })),
    };
  }, [cacheQ.data]);

  const prefixStats = useMemo(
    () =>
      [...stats.prefixes].sort((a, b) => {
        const hitRateDiff = a.hitRate - b.hitRate;
        if (hitRateDiff !== 0) return hitRateDiff;
        return b.count - a.count;
      }),
    [stats.prefixes],
  );
  const statsUpdatedAt = cacheQ.dataUpdatedAt ? new Date(cacheQ.dataUpdatedAt).toLocaleString('zh-CN') : null;
  const statsStatus = cacheQ.isFetching ? '刷新中' : cacheQ.data ? '统计可用' : '等待统计';
  const refreshStats = useCallback(async () => {
    setActionError(null);
    await cacheQ.refetch();
    setLastStatsRefreshAt(new Date().toLocaleString('zh-CN'));
  }, [cacheQ]);

  const cachePageActions = useMemo(
    () => [
      {
        id: 'admin-cache.refresh',
        label: '刷新缓存统计',
        description: '重新拉取缓存命中率、键数和前缀分布',
        keywords: ['缓存', '刷新', '统计'],
        scope: 'page' as const,
        pageKey: 'admin-cache',
        run: async () => {
          await refreshStats();
          return { message: '已刷新缓存统计' };
        },
      },
      {
        id: 'admin-cache.confirm-clear-all',
        label: '准备清除全部缓存',
        description: '打开全量清理确认框，谨慎执行高风险动作',
        keywords: ['清缓存', '全量', '危险操作'],
        scope: 'page' as const,
        pageKey: 'admin-cache',
        run: () => {
          setConfirmTarget({ label: '全部缓存' });
          return { message: '已打开全量清理确认' };
        },
      },
    ],
    [refreshStats],
  );
  usePageActions(cachePageActions);
  const cacheSummary = `缓存统计当前为 ${statsStatus}，总键数 ${stats.totalKeys.toLocaleString()}，命中率 ${(stats.hitRate * 100).toFixed(1)}%，内存占用 ${stats.memoryUsed}。`;
  const cacheResult = buildLocalResultContract({
    summary: cacheSummary,
    availableViews: prefixStats.length > 1 ? ['compare'] : [],
    pageActions: cachePageActions,
    preferredActionIds: ['admin-cache.refresh', 'admin-cache.confirm-clear-all'],
    recommendedLinks: [
      { id: 'admin-cache-link-tools', label: '检查工具健康', href: '/admin/tools' },
      { id: 'admin-cache-link-dead-letters', label: '查看死信队列', href: '/admin/dead-letters' },
      { id: 'admin-cache-link-audit', label: '审计日志', href: '/settings/audit-log' },
    ],
    evidence: [
      { label: '统计状态', value: statsStatus },
      { label: '总键数', value: stats.totalKeys.toLocaleString() },
      { label: '命中率', value: `${(stats.hitRate * 100).toFixed(1)}%` },
      { label: '内存占用', value: stats.memoryUsed },
      { label: '前缀数量', value: String(prefixStats.length) },
    ],
    riskNotes: [
      ...(actionError ? [actionError] : []),
      ...(clearReceipt?.fullClear ? ['最近一次执行的是全量清理，需要关注回源压力。'] : []),
      ...(prefixStats.length === 0 ? ['当前还没有可用的前缀级缓存统计。'] : []),
    ],
    freshness: statsUpdatedAt ? { updatedAt: statsUpdatedAt, label: '缓存快照' } : null,
    platformMeta: {
      sourceTool: 'admin/cache-stats',
      sourceChain: ['admin', 'cache'],
      degraded: Boolean(actionError || cacheQ.error),
      fallbackReason: [actionError, cacheQ.error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('admin-cache', '复查缓存状态', '/admin/cache', 'cache-review', {
      totalKeys: stats.totalKeys,
      hitRate: stats.hitRate,
      prefixCount: prefixStats.length,
    }),
  });
  usePageContext({
    pageKey: 'admin-cache',
    title: '缓存管理',
    summary: cacheSummary,
    objectType: 'cache-cluster',
    objectId: 'admin-cache',
    resultType: 'cache-admin-panel',
    tags: [statsStatus, `${stats.totalKeys} 键`, `${prefixStats.length} 个前缀`],
    suggestions: [
      '总结当前缓存健康状态和是否需要局部清理',
      '如果命中率偏低，给出先检查的前缀或链路',
      '解释为什么全量清理应该谨慎使用',
    ],
    recommendedActions: cacheResult.recommendedActions ?? [],
    recommendedLinks: cacheResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(cacheResult.evidence),
    riskNotes: cacheResult.riskNotes ?? [],
    freshness: cacheResult.freshness ?? null,
    raw: {
      totalKeys: stats.totalKeys,
      hitRate: stats.hitRate,
      prefixCount: prefixStats.length,
      statsStatus,
    },
  });

  const handleClear = async (target: { prefix?: string; label: string }) => {
    setClearing(true);
    setActionError(null);
    try {
      await clearApi.triggerAsync('/admin/cache/clear', { method: 'POST' }, { prefix: target.prefix });
      await cacheQ.refetch();
      const refreshedAt = new Date().toLocaleString('zh-CN');
      setLastStatsRefreshAt(refreshedAt);
      setClearReceipt({
        label: target.label,
        clearedAt: refreshedAt,
        fullClear: target.prefix == null,
        statsRefreshed: true,
      });
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setClearing(false);
    }
  };

  const confirmClear = async () => {
    if (!confirmTarget) return;
    const target = confirmTarget;
    setConfirmTarget(null);
    setDangerAck(false);
    await handleClear(target);
  };

  if (cacheQ.error) {
    const permissionDenied = isPermissionDeniedErrorMessage(cacheQ.error);
    return (
      <PageContainer>
        <h1 className="text-lg font-semibold mb-4">💾 缓存管理</h1>
        {permissionDenied ? (
          <SectionCard className="p-4">
            <EmptyState
              variant="full"
              text="当前账号无权查看缓存管理"
              hint="如果这是预期权限策略，请保留该拒绝态；如果当前账号本应具备管理员权限，请先回到管理后台核对登录身份与角色。"
              action={
                <>
                  <Link
                    href="/admin"
                    className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline"
                  >
                    返回管理后台
                  </Link>
                  <Link
                    href="/admin/tools"
                    className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline"
                  >
                    检查工具健康
                  </Link>
                </>
              }
            />
          </SectionCard>
        ) : (
          <ErrorState
            text={cacheQ.error}
            hint="当前页面需要管理员权限；请求失败时不再显示 0 命中率。"
            onRetry={() => cacheQ.refetch()}
          />
        )}
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <h1 className="text-lg font-semibold mb-4">💾 缓存管理</h1>
      {actionError ? <ErrorState text={actionError} /> : null}

      <ResultWorkbench pageKey="admin-cache" title="缓存管理结果工作台" result={cacheResult} />

      <SectionCard className="mb-4 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="mt-0 mb-1 text-base font-semibold">操作建议</h2>
            <p className="m-0 text-sm text-text-secondary">
              优先清理单个前缀缓存，只有在大面积缓存异常或结构升级后，才建议执行“清除全部缓存”。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="rounded-xl border border-warning/20 bg-warning/5 px-3 py-2 text-xs leading-5 text-text-secondary">
              全量清理会放大瞬时回源压力，并可能让用户短时间内看到更多加载态。
            </div>
            <button
              type="button"
              onClick={() => void refreshStats()}
              disabled={cacheQ.isFetching}
              data-testid="page-primary-action"
              className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {cacheQ.isFetching ? '刷新中...' : '刷新缓存统计'}
            </button>
          </div>
        </div>
        <div
          data-testid="page-primary-status"
          className="mt-4 rounded-xl border border-border bg-surface-alt/35 px-3 py-3 text-sm"
        >
          <div className="font-medium text-text-primary">缓存统计状态：{statsStatus}</div>
          <p className="mt-1 mb-0 text-xs text-text-secondary">
            当前总键数 {stats.totalKeys.toLocaleString()}，命中率 {(stats.hitRate * 100).toFixed(1)}%，内存占用{' '}
            {stats.memoryUsed}。
          </p>
          <p className="mt-2 mb-0 text-xs text-text-secondary">
            最近统计：{statsUpdatedAt ?? '未加载'}
            {lastStatsRefreshAt ? ` ｜ 手动刷新：${lastStatsRefreshAt}` : ''}
          </p>
        </div>
      </SectionCard>

      <KpiGrid cols={4}>
        <KpiCard title="命中率" value={`${(stats.hitRate * 100).toFixed(1)}%`} />
        <KpiCard title="总键数" value={stats.totalKeys.toLocaleString()} />
        <KpiCard title="内存占用" value={stats.memoryUsed} />
        <KpiCard title="命中/未命中" value={`${stats.hits}/${stats.misses}`} />
      </KpiGrid>

      <div className="flex gap-2 mt-4 mb-4">
        <button
          onClick={() => setConfirmTarget({ label: '全部缓存' })}
          disabled={clearing}
          data-testid="cache-clear-all-action"
          className="text-xs px-3 py-1.5 bg-danger/20 text-danger rounded-lg cursor-pointer border border-danger/30 hover:bg-danger/30"
        >
          {clearing ? '清除中...' : '🗑 清除全部缓存'}
        </button>
      </div>

      {clearReceipt ? (
        <SectionCard className="mb-4 p-4">
          <div
            data-testid="cache-clear-receipt"
            className="rounded-xl border border-success/20 bg-success/5 px-3 py-3 text-sm"
          >
            <div className="font-medium text-text-primary">最近一次清理回执</div>
            <p className="mt-1 mb-0 text-xs text-text-secondary">
              清理目标：{clearReceipt.label} ｜ 类型：{clearReceipt.fullClear ? '全量清理' : '前缀清理'}
            </p>
            <p className="mt-2 mb-0 text-xs text-text-secondary">
              触发时间：{clearReceipt.clearedAt} ｜ 统计已刷新：{clearReceipt.statsRefreshed ? '是' : '否'}
            </p>
          </div>
        </SectionCard>
      ) : null}

      {prefixStats.length > 0 && (
        <SectionCard className="p-3">
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <div>
              <h3 className="mt-0 mb-1 text-sm font-semibold">按前缀统计</h3>
              <p className="m-0 text-xs text-text-secondary">
                低命中率前缀会优先显示，便于先做局部清理，而不是直接全量清空。
              </p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-glass-border text-text-secondary text-xs">
                  <th className="text-left py-2 px-2">前缀</th>
                  <th className="text-right py-2 px-2">键数</th>
                  <th className="text-right py-2 px-2">命中率</th>
                  <th className="text-center py-2 px-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {prefixStats.map((p) => (
                  <tr key={p.prefix} className="border-b border-glass-border/50 hover:bg-white/5">
                    <td className="py-2 px-2 font-mono text-xs">{p.prefix}</td>
                    <td className="py-2 px-2 text-right">{p.count}</td>
                    <td className="py-2 px-2 text-right">{(p.hitRate * 100).toFixed(1)}%</td>
                    <td className="py-2 px-2 text-center">
                      <button
                        onClick={() => setConfirmTarget({ prefix: p.prefix, label: p.prefix })}
                        disabled={clearing}
                        className="text-[11px] text-danger cursor-pointer hover:underline"
                      >
                        清除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      <ConfirmDialog
        open={confirmTarget != null}
        title="确认清理缓存"
        danger
        confirmDisabled={confirmTarget?.prefix == null && !dangerAck}
        confirmText={clearing ? '清理中...' : '确认清理'}
        cancelText="取消"
        onConfirm={() => void confirmClear()}
        onCancel={() => {
          setConfirmTarget(null);
          setDangerAck(false);
        }}
      >
        {confirmTarget ? (
          <div className="space-y-2 text-sm">
            <p className="m-0">
              即将清理：<span className="font-medium">{confirmTarget.label}</span>
            </p>
            <p className="m-0 text-text-secondary">该操作会立即删除对应缓存键，后续请求需要重新回源加载数据。</p>
            {confirmTarget.prefix == null ? (
              <>
                <p className="m-0 text-warning text-xs">
                  这是全量危险操作。建议确认当前确实存在大面积缓存污染、版本切换或命中率异常，再继续。
                </p>
                <label className="flex items-start gap-2 rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-text-secondary">
                  <input
                    type="checkbox"
                    checked={dangerAck}
                    onChange={(e) => setDangerAck(e.target.checked)}
                    className="mt-0.5 rounded border-border accent-primary"
                  />
                  <span>我已知晓全量清理会让所有缓存回源重建，并可能导致短时加载变慢。</span>
                </label>
              </>
            ) : null}
          </div>
        ) : null}
      </ConfirmDialog>
    </PageContainer>
  );
}
