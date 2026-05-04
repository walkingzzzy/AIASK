'use client';

import Link from 'next/link';
import { useState } from 'react';
import {
  PageContainer,
  SectionCard,
  KpiGrid,
  KpiCard,
  Badge,
  Skeleton,
  QuickAction,
  QuickActionGrid,
} from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { ErrorState } from '@/components/status-state';
import {
  formatHealthStatusLabel,
  healthStatusVariant,
  normalizeSystemHealthSnapshot,
} from '@/lib/system-health';

type AdminIssue = {
  title: string;
  detail: string;
  href: string;
  tone: 'danger' | 'warning';
};

const QUICK_LINKS = [
  { href: '/admin/tools', label: 'MCP 工具仪表盘', desc: '查看工具连通性与调用概况' },
  { href: '/admin/cache', label: '缓存管理', desc: '检查命中率并清理异常缓存' },
  { href: '/admin/dead-letters', label: '死信队列', desc: '优先处理同步失败和重试任务' },
  { href: '/admin/users', label: '用户管理', desc: '核对角色、状态和注册情况' },
  { href: '/settings/audit-log', label: '审计日志', desc: '查看管理员操作留痕' },
];

export default function AdminPage() {
  const [lastManualRefreshAt, setLastManualRefreshAt] = useState<string | null>(null);
  const healthQ = useApiQuery<unknown>('/health', {
    staleTime: 15000,
    placeholderData: 'keepPrevious',
    parse: (raw) => raw,
  });

  const snapshot = normalizeSystemHealthSnapshot(healthQ.data);
  const db = snapshot.dependencies.db.raw;
  const cache = snapshot.dependencies.cache.raw;
  const mcp = snapshot.dependencies.mcp.raw;
  const vector = snapshot.dependencies.vector.raw;
  const hasHealthSnapshot = healthQ.data != null;
  const loadingSnapshot = !hasHealthSnapshot && !healthQ.error;
  const lastUpdated = snapshot.timestamp ? new Date(snapshot.timestamp).toLocaleString('zh-CN') : '-';

  const issues: AdminIssue[] = [];
  if (hasHealthSnapshot && snapshot.status === 'untrusted') {
    issues.push({
      title: '服务状态异常',
      detail: `当前 health 状态为 ${formatHealthStatusLabel(snapshot.status)}，建议先检查 BFF 日志与部署状态。`,
      href: '/settings/audit-log',
      tone: 'danger',
    });
  }
  if (hasHealthSnapshot && snapshot.status === 'degraded') {
    issues.push({
      title: '系统存在降级链路',
      detail: snapshot.reasons.length > 0 ? snapshot.reasons.join(' / ') : '至少有一个依赖正在降级运行。',
      href: '/admin/tools',
      tone: 'warning',
    });
  }
  if (hasHealthSnapshot && snapshot.dependencies.db.status === 'untrusted') {
    issues.push({
      title: '数据库健康检查失败',
      detail: snapshot.dependencies.db.reasons.length > 0
        ? snapshot.dependencies.db.reasons.join(' / ')
        : `数据库状态 ${formatHealthStatusLabel(snapshot.dependencies.db.status)}，优先确认连接、迁移和资源占用。`,
      href: '/settings/audit-log',
      tone: 'danger',
    });
  }
  if (hasHealthSnapshot && snapshot.dependencies.mcp.status === 'untrusted') {
    issues.push({
      title: 'MCP 网关不可达',
      detail: 'AI/数据工具可能无法调用，建议先检查 MCP 进程与连接来源。',
      href: '/admin/tools',
      tone: 'danger',
    });
  }
  if (hasHealthSnapshot && snapshot.dependencies.mcp.status === 'degraded') {
    issues.push({
      title: 'MCP 处于降级模式',
      detail: `当前可用 ${String(mcp.toolCount ?? 0)} / 期望 ${String(mcp.expectedTools ?? 0)}，存在能力缺口或传输回退。`,
      href: '/admin/tools',
      tone: 'warning',
    });
  }
  if (hasHealthSnapshot && snapshot.dependencies.vector.status !== 'normal') {
    issues.push({
      title: '向量链路不可完全信任',
      detail: snapshot.dependencies.vector.reasons.length > 0
        ? snapshot.dependencies.vector.reasons.join(' / ')
        : `向量状态为 ${formatHealthStatusLabel(snapshot.dependencies.vector.status)}。`,
      href: '/strategy-market?from=admin',
      tone: snapshot.dependencies.vector.status === 'untrusted' ? 'danger' : 'warning',
    });
  }
  if (hasHealthSnapshot && snapshot.dependencies.cache.status !== 'normal') {
    issues.push({
      title: '缓存未处于 Redis 正常态',
      detail: snapshot.dependencies.cache.reasons.length > 0
        ? snapshot.dependencies.cache.reasons.join(' / ')
        : '当前缓存处于内存回退路径。',
      href: '/admin/cache',
      tone: 'warning',
    });
  }
  const snapshotState = healthQ.isFetching
    ? '刷新中'
    : !hasHealthSnapshot
      ? '等待快照'
      : snapshot.status === 'untrusted'
        ? '发现不可信状态'
        : snapshot.status === 'degraded'
          ? '存在降级'
          : '运行正常';
  const snapshotHint = hasHealthSnapshot
    ? `服务 ${formatHealthStatusLabel(snapshot.status)} / DB ${formatHealthStatusLabel(snapshot.dependencies.db.status)} / Cache ${formatHealthStatusLabel(snapshot.dependencies.cache.status)} / MCP ${formatHealthStatusLabel(snapshot.dependencies.mcp.status)} / Vector ${formatHealthStatusLabel(snapshot.dependencies.vector.status)}`
    : '首屏保持静态摘要；需要最新运行态时请手动刷新快照。';

  async function refreshSnapshot() {
    await healthQ.refetch();
    setLastManualRefreshAt(new Date().toLocaleString('zh-CN'));
  }

  return (
    <PageContainer>
      <h1 className="text-lg font-semibold mb-2">管理后台概览</h1>
      <p className="mt-0 mb-4 text-sm text-text-secondary">
        第一屏先呈现需要处理的管理动作和健康概览，详细运行快照可在后续区域继续查看。
      </p>

      {healthQ.error ? (
        <ErrorState
          text={healthQ.error}
          hint="请先确认管理员权限和 BFF 健康接口是否可达。"
          onRetry={() => healthQ.refetch()}
        />
      ) : null}

      <SectionCard className="p-4 mb-4 min-h-[176px]">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="mt-0 mb-0 text-base font-semibold">优先处理</h2>
            <Badge variant={issues.length > 0 ? 'danger' : 'success'}>
              {issues.length > 0 ? `${issues.length} 个待处理项` : '当前无阻塞项'}
            </Badge>
          </div>
          <button
            type="button"
            onClick={() => void refreshSnapshot()}
            disabled={healthQ.isFetching}
            data-testid="admin-refresh-snapshot-action"
            data-action-testid="admin-refresh-snapshot-action"
            className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {healthQ.isFetching ? '刷新中...' : '刷新运行快照'}
          </button>
        </div>
        {!hasHealthSnapshot ? (
          <div className="space-y-3">
            <Skeleton height={52} />
            <Skeleton height={52} />
          </div>
        ) : issues.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2">
            {issues.map((issue) => (
              <Link
                key={issue.title}
                href={issue.href}
                className={`no-underline rounded-xl border p-3 text-inherit ${issue.tone === 'danger' ? 'border-danger/30 bg-danger/5' : 'border-warning/30 bg-warning/5'}`}
              >
                <div className="text-sm font-medium">{issue.title}</div>
                <p className="mt-1 mb-0 text-xs text-text-secondary">{issue.detail}</p>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-success/20 bg-success/5 p-3">
            <div className="text-sm font-medium text-success">当前系统未发现首屏阻塞项</div>
            <p className="mt-1 mb-0 text-xs text-text-secondary">
              如果后续出现缓存异常、工具断连或同步失败，可从下方入口继续排查。
            </p>
          </div>
        )}
        <div
          data-testid="page-primary-status"
          className="mt-4 rounded-xl border border-border bg-surface-alt/35 p-3 text-sm"
        >
          <div className="font-medium text-text-primary">快照状态：{snapshotState}</div>
          <p className="mt-1 mb-0 text-xs text-text-secondary">{snapshotHint}</p>
          <p className="mt-2 mb-0 text-xs text-text-secondary">
            最近快照：{lastUpdated}
            {lastManualRefreshAt ? ` ｜ 手动刷新：${lastManualRefreshAt}` : ''}
          </p>
        </div>
      </SectionCard>

      <SectionCard className="p-4 mb-4">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
          <div>
            <h2 className="mt-0 mb-1 text-base font-semibold">第一步通常去这里</h2>
            <p className="m-0 text-sm text-text-secondary">
              先排查工具、缓存和死信，再回来看详细快照，通常比一开始盯着所有状态字段更有效。
            </p>
          </div>
          <Badge variant={issues.length > 0 ? 'warning' : 'info'}>
            {issues.length > 0 ? '优先看异常路径' : '可做例行巡检'}
          </Badge>
        </div>
        <QuickActionGrid cols={5}>
          <QuickAction href="/admin/tools" icon="🧰" title="工具健康" description="先看 MCP 工具是否断连或降级" />
          <QuickAction href="/admin/cache" icon="💾" title="缓存管理" description="命中率异常时优先做局部清理" />
          <QuickAction href="/admin/dead-letters" icon="📭" title="死信队列" description="处理反复失败和未消费任务" />
          <QuickAction href="/settings/audit-log" icon="🧾" title="审计日志" description="回看管理员操作与错误留痕" />
          <QuickAction href="/admin/users" icon="👥" title="用户管理" description="核对角色、状态和注册情况" />
        </QuickActionGrid>
      </SectionCard>

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="服务状态" value={hasHealthSnapshot ? formatHealthStatusLabel(snapshot.status) : '加载中'} />
        <KpiCard
          title="数据库"
          value={hasHealthSnapshot ? formatHealthStatusLabel(snapshot.dependencies.db.status) : '加载中'}
        />
        <KpiCard title="缓存" value={hasHealthSnapshot ? formatHealthStatusLabel(snapshot.dependencies.cache.status) : '加载中'} />
        <KpiCard title="MCP 连接" value={hasHealthSnapshot ? formatHealthStatusLabel(snapshot.dependencies.mcp.status) : '加载中'} />
        <KpiCard
          title="向量状态"
          value={hasHealthSnapshot ? formatHealthStatusLabel(snapshot.dependencies.vector.status) : '加载中'}
        />
      </KpiGrid>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SectionCard className="p-4">
          <h3 className="mt-0 text-sm font-semibold mb-3">常用入口</h3>
          <div className="space-y-2">
            {QUICK_LINKS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block rounded-lg border border-border px-3 py-3 no-underline text-inherit hover:bg-surface-alt/40"
              >
                <div className="text-sm font-medium">{item.label}</div>
                <div className="mt-1 text-xs text-text-secondary">{item.desc}</div>
              </Link>
            ))}
          </div>
        </SectionCard>

        <SectionCard className="p-4">
          <h3 className="mt-0 text-sm font-semibold mb-3">运行快照</h3>
          {loadingSnapshot ? (
            <div className="space-y-3">
              <Skeleton height={20} />
              <Skeleton height={20} />
              <Skeleton height={20} />
              <Skeleton height={72} />
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">服务名</span>
                <span className="font-medium">
                  {hasHealthSnapshot ? snapshot.service : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">MCP 来源</span>
                <span className="font-medium">{hasHealthSnapshot ? String(mcp.source ?? '-') : '加载中'}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">MCP 状态</span>
                <Badge variant={hasHealthSnapshot ? healthStatusVariant(snapshot.dependencies.mcp.status) : 'warning'}>
                  {hasHealthSnapshot ? formatHealthStatusLabel(snapshot.dependencies.mcp.status) : 'loading'}
                </Badge>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">数据库模式</span>
                <span className="font-medium">
                  {hasHealthSnapshot ? (db.enabled ? '持久化' : '内存模式') : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">DB 原因</span>
                <span className="font-medium">
                  {hasHealthSnapshot ? String((snapshot.dependencies.db.reasons[0] ?? db.lastFailureStage ?? '-')) : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">缓存后端</span>
                <span className="font-medium">
                  {hasHealthSnapshot ? String(cache.activeBackend ?? '-') : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">Cache 原因</span>
                <span className="font-medium">
                  {hasHealthSnapshot ? String((snapshot.dependencies.cache.reasons[0] ?? cache.lastFailureStage ?? '-')) : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">活跃连接 / 连接池</span>
                <span className="font-medium">
                  {hasHealthSnapshot
                    ? `${String(mcp.activeConnections ?? '-')} / ${String(mcp.poolSize ?? '-')}`
                    : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">向量 backend / mode</span>
                <span className="font-medium">
                  {hasHealthSnapshot ? `${String(vector.backend ?? '-')} / ${String(vector.health_mode ?? vector.healthMode ?? '-')}` : '加载中'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">最近更新</span>
                <span className="font-medium">{hasHealthSnapshot ? lastUpdated : '加载中'}</span>
              </div>
              {snapshot.reasons.length > 0 ? (
                <div className="rounded-xl border border-border bg-surface-alt/30 p-3">
                  <div className="text-xs font-medium text-text-primary">主要原因</div>
                  <p className="mt-1 mb-0 text-xs text-text-secondary break-all">
                    {snapshot.reasons.join(' / ')}
                  </p>
                </div>
              ) : null}
            </div>
          )}
          {!loadingSnapshot ? (
            <div className="rounded-xl border border-border bg-surface-alt/30 p-3">
              <div className="text-xs font-medium text-text-primary">排查建议</div>
              <p className="mt-1 mb-0 text-xs text-text-secondary">
                如果首页提示阻塞项，优先检查 MCP 工具页和死信队列；如果没有阻塞项，再回到缓存管理和审计日志做细项排查。
              </p>
            </div>
          ) : null}
        </SectionCard>
      </div>
    </PageContainer>
  );
}
