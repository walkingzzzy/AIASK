'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, DataTable, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { ErrorState } from '@/components/status-state';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';

function readRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

/**
 * T-052: User Management Panel
 */
export default function UsersPage() {
  const [searchText, setSearchText] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [lastManualRefreshAt, setLastManualRefreshAt] = useState<string | null>(null);
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const usersQ = useApiQuery<unknown>('/admin/users', {
    refetchInterval: 30000,
    parse: (raw) => raw,
  });

  const users = useMemo(() => {
    const raw = readRecord(usersQ.data);
    const data = readRecord(raw.data);
    const items = raw.items ?? data.items ?? raw.users ?? [];
    return Array.isArray(items)
      ? items.map((u: Record<string, unknown>) => ({
          id: String(u.id ?? ''),
          username: String(u.username ?? u.name ?? ''),
          email: String(u.email ?? ''),
          role: String(u.role ?? 'viewer'),
          status: String(u.status ?? 'active'),
          createdAt: String(u.createdAt ?? u.created_at ?? ''),
          lastActive: String(u.lastActive ?? u.last_active ?? u.lastLogin ?? ''),
        }))
      : [];
  }, [usersQ.data]);

  const stats = useMemo(
    () => ({
      total: users.length,
      active: users.filter((u) => u.status === 'active').length,
      admins: users.filter((u) => u.role === 'admin').length,
      today: users.filter((u) => {
        if (!u.lastActive) return false;
        const d = new Date(u.lastActive);
        const now = new Date();
        return d.toDateString() === now.toDateString();
      }).length,
    }),
    [users],
  );
  const availableRoles = useMemo(
    () =>
      Array.from(new Set(users.map((u) => u.role)))
        .filter(Boolean)
        .sort(),
    [users],
  );
  const filteredUsers = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    return users.filter((user) => {
      const roleMatch = roleFilter === 'all' || user.role === roleFilter;
      const searchMatch =
        !keyword || user.username.toLowerCase().includes(keyword) || user.email.toLowerCase().includes(keyword);
      return roleMatch && searchMatch;
    });
  }, [roleFilter, searchText, users]);
  const latestUsersRefreshText = usersQ.dataUpdatedAt
    ? new Date(usersQ.dataUpdatedAt).toLocaleString('zh-CN')
    : '等待首个用户快照';

  async function refreshUsers() {
    await usersQ.refetch();
    setLastManualRefreshAt(new Date().toLocaleString('zh-CN'));
  }

  const ROLE_COLORS: Record<string, 'danger' | 'warning' | 'info' | 'success'> = {
    admin: 'danger',
    trader: 'warning',
    analyst: 'info',
    viewer: 'success',
  };

  if (usersQ.error) {
    return (
      <PageContainer>
        <h1 className="text-lg font-semibold mb-4">👥 用户管理</h1>
        <ErrorState
          text={usersQ.error}
          hint="当前页面需要管理员权限；请求失败时不再渲染成 0 用户。"
          onRetry={() => usersQ.refetch()}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <h1 className="text-lg font-semibold mb-4">👥 用户管理</h1>

      <SectionCard className="mb-4 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="mt-0 mb-1 text-base font-semibold">先确认用户盘点</h2>
            <p className="m-0 text-sm text-text-secondary">
              首屏只保留用户盘点和一个稳定的刷新动作，搜索与角色筛选都下沉到表头工具条。
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refreshUsers()}
            disabled={usersQ.isFetching}
            data-testid="page-primary-action"
            data-action-testid="admin-users-refresh-action"
            className="inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {usersQ.isFetching ? '刷新中...' : '刷新用户列表'}
          </button>
        </div>
        <div
          data-testid="page-primary-status"
          className="mt-4 rounded-xl border border-border bg-surface-alt/35 px-3 py-3 text-sm"
        >
          <div className="font-medium text-text-primary">
            当前展示 {filteredUsers.length} / {users.length} 位用户 ｜ 活跃 {stats.active} ｜ 管理员 {stats.admins}
          </div>
          <p className="mt-1 mb-0 text-xs text-text-secondary">
            当前筛选：{roleFilter === 'all' ? '全部角色' : roleFilter} ｜ 搜索词：{searchText.trim() || '无'}
          </p>
          <p className="mt-2 mb-0 text-xs text-text-secondary">
            最近快照：{latestUsersRefreshText}
            {lastManualRefreshAt ? ` ｜ 手动刷新：${lastManualRefreshAt}` : ''}
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-border bg-surface px-3 py-3">
              <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">总用户</div>
              <div className="mt-2 text-xl font-semibold text-text-primary">{stats.total}</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-3 py-3">
              <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">活跃用户</div>
              <div className="mt-2 text-xl font-semibold text-text-primary">{stats.active}</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-3 py-3">
              <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">管理员</div>
              <div className="mt-2 text-xl font-semibold text-text-primary">{stats.admins}</div>
            </div>
            <div className="rounded-2xl border border-border bg-surface px-3 py-3">
              <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">今日活跃</div>
              <div className="mt-2 text-xl font-semibold text-text-primary">{stats.today}</div>
            </div>
          </div>
        </div>
      </SectionCard>

      {users.length === 0 ? (
        <SectionCard className="mt-4">
          <p className="text-text-secondary text-sm text-center py-12">
            {usersQ.isFetching ? '加载中...' : '暂无用户数据'}
          </p>
        </SectionCard>
      ) : filteredUsers.length === 0 ? (
        <SectionCard className="mt-4">
          <p className="text-text-secondary text-sm text-center py-12">
            当前筛选条件下没有匹配用户，请调整搜索词或角色筛选。
          </p>
        </SectionCard>
      ) : (
        <SectionCard className="mt-4 p-3">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-text-primary">用户列表</div>
              <div className="mt-1 text-sm text-text-secondary">
                当前展示 {filteredUsers.length} / {users.length} 位用户
              </div>
            </div>
            <div className="text-xs text-text-secondary">
              {roleFilter === 'all' ? '全部角色' : roleFilter} ｜ 搜索词：{searchText.trim() || '无'}
            </div>
          </div>
          <details className="mb-4 rounded-2xl border border-border bg-surface/50 px-3 py-3" open={!compactLayout}>
            <summary className="cursor-pointer text-sm font-medium text-text-primary">筛选与搜索</summary>
            <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <label htmlFor="admin-users-search" className="grid gap-1 text-xs text-text-secondary md:min-w-[260px]">
                <span>搜索用户</span>
                <input
                  id="admin-users-search"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="按用户名或邮箱搜索"
                  className="px-3 py-2 rounded border border-border bg-surface text-sm"
                />
              </label>
              <label htmlFor="admin-users-role" className="grid gap-1 text-xs text-text-secondary md:min-w-[180px]">
                <span>角色筛选</span>
                <select
                  id="admin-users-role"
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                  className="px-3 py-2 rounded border border-border bg-surface text-sm"
                >
                  <option value="all">全部角色</option>
                  {availableRoles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </details>
          <div className="text-xs text-text-secondary">
            默认扫读只保留用户名、角色、状态和最近活跃；邮箱与注册时间下沉到详情态。
          </div>
          <DataTable
            rows={filteredUsers}
            pageSize={10}
            maxHeight={520}
            rowKey="id"
            columns={[
              { key: 'username', label: '用户名' },
              {
                key: 'role',
                label: '角色',
                align: 'center',
                render: (value) => <Badge variant={ROLE_COLORS[String(value)] ?? 'info'}>{String(value || '-')}</Badge>,
              },
              {
                key: 'status',
                label: '状态',
                align: 'center',
                render: (value) => (
                  <span className={`text-xs ${value === 'active' ? 'text-success' : 'text-text-secondary'}`}>
                    {value === 'active' ? '🟢' : '⚪'} {String(value || '-')}
                  </span>
                ),
              },
              {
                key: 'lastActive',
                label: '最近活跃',
                render: (value) => (value ? new Date(String(value)).toLocaleString('zh-CN') : '-'),
              },
              {
                key: 'detail',
                label: '详情',
                sortable: false,
                render: (_value, row) => (
                  <details className="rounded-lg border border-glass-border bg-white/40 px-3 py-2">
                    <summary className="cursor-pointer text-xs text-text-secondary">查看邮箱与注册信息</summary>
                    <div className="mt-2 space-y-1 text-xs text-text-secondary">
                      <div>邮箱：{String(row.email || '-')}</div>
                      <div>
                        注册时间：
                        {row.createdAt ? new Date(String(row.createdAt)).toLocaleDateString('zh-CN') : '-'}
                      </div>
                    </div>
                  </details>
                ),
              },
            ]}
            mobileCardRender={(row) => (
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-text-primary">{String(row.username || '-')}</div>
                    <div className="mt-1 text-xs text-text-secondary">
                      最近活跃：{row.lastActive ? new Date(String(row.lastActive)).toLocaleString('zh-CN') : '-'}
                    </div>
                  </div>
                  <Badge variant={ROLE_COLORS[String(row.role)] ?? 'info'}>{String(row.role || '-')}</Badge>
                </div>
                <div className="text-xs text-text-secondary">
                  状态：{row.status === 'active' ? '🟢' : '⚪'} {String(row.status || '-')}
                </div>
                <details className="rounded-lg border border-glass-border bg-white/35 px-3 py-2">
                  <summary className="cursor-pointer text-xs text-text-secondary">更多信息</summary>
                  <div className="mt-2 space-y-1 text-xs text-text-secondary">
                    <div>邮箱：{String(row.email || '-')}</div>
                    <div>
                      注册时间：
                      {row.createdAt ? new Date(String(row.createdAt)).toLocaleDateString('zh-CN') : '-'}
                    </div>
                  </div>
                </details>
              </div>
            )}
          />
        </SectionCard>
      )}
    </PageContainer>
  );
}
