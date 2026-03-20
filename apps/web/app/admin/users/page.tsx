'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiGrid, KpiCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { ErrorState } from '@/components/status-state';

/**
 * T-052: User Management Panel
 */
export default function UsersPage() {
    const [searchText, setSearchText] = useState('');
    const [roleFilter, setRoleFilter] = useState('all');
    const usersQ = useApiQuery<unknown>('/admin/users', {
        refetchInterval: 30000,
        parse: (raw) => raw,
    });

    const users = useMemo(() => {
        const raw = usersQ.data as any;
        const items = raw?.items ?? raw?.data?.items ?? raw?.users ?? [];
        return Array.isArray(items) ? items.map((u: Record<string, unknown>) => ({
            id: String(u.id ?? ''),
            username: String(u.username ?? u.name ?? ''),
            email: String(u.email ?? ''),
            role: String(u.role ?? 'viewer'),
            status: String(u.status ?? 'active'),
            createdAt: String(u.createdAt ?? u.created_at ?? ''),
            lastActive: String(u.lastActive ?? u.last_active ?? u.lastLogin ?? ''),
        })) : [];
    }, [usersQ.data]);

    const stats = useMemo(() => ({
        total: users.length,
        active: users.filter((u) => u.status === 'active').length,
        admins: users.filter((u) => u.role === 'admin').length,
        today: users.filter((u) => {
            if (!u.lastActive) return false;
            const d = new Date(u.lastActive);
            const now = new Date();
            return d.toDateString() === now.toDateString();
        }).length,
    }), [users]);
    const availableRoles = useMemo(() => Array.from(new Set(users.map((u) => u.role))).filter(Boolean).sort(), [users]);
    const filteredUsers = useMemo(() => {
        const keyword = searchText.trim().toLowerCase();
        return users.filter((user) => {
            const roleMatch = roleFilter === 'all' || user.role === roleFilter;
            const searchMatch = !keyword
                || user.username.toLowerCase().includes(keyword)
                || user.email.toLowerCase().includes(keyword);
            return roleMatch && searchMatch;
        });
    }, [roleFilter, searchText, users]);

    const ROLE_COLORS: Record<string, 'danger' | 'warning' | 'info' | 'success'> = {
        admin: 'danger', trader: 'warning', analyst: 'info', viewer: 'success',
    };

    if (usersQ.error) {
        return (
            <PageContainer>
                <h1 className="text-lg font-semibold mb-4">👥 用户管理</h1>
                <ErrorState text={usersQ.error} hint="当前页面需要管理员权限；请求失败时不再渲染成 0 用户。" onRetry={() => usersQ.refetch()} />
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <h1 className="text-lg font-semibold mb-4">👥 用户管理</h1>

            <KpiGrid cols={4}>
                <KpiCard title="总用户" value={stats.total.toString()} />
                <KpiCard title="活跃用户" value={stats.active.toString()} />
                <KpiCard title="管理员" value={stats.admins.toString()} />
                <KpiCard title="今日活跃" value={stats.today.toString()} />
            </KpiGrid>

            <SectionCard className="mt-4 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
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
                                <option key={role} value={role}>{role}</option>
                            ))}
                        </select>
                    </label>
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
                    <div className="mb-3 text-sm text-text-secondary">当前展示 {filteredUsers.length} / {users.length} 位用户</div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-2 px-2">用户名</th>
                                    <th className="text-left py-2 px-2">邮箱</th>
                                    <th className="text-center py-2 px-2">角色</th>
                                    <th className="text-center py-2 px-2">状态</th>
                                    <th className="text-left py-2 px-2">注册时间</th>
                                    <th className="text-left py-2 px-2">最后活跃</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredUsers.map((u) => (
                                    <tr key={u.id} className="border-b border-glass-border/50 hover:bg-white/5">
                                        <td className="py-2 px-2 font-medium">{u.username}</td>
                                        <td className="py-2 px-2 text-text-secondary text-xs">{u.email || '-'}</td>
                                        <td className="py-2 px-2 text-center">
                                            <Badge variant={ROLE_COLORS[u.role] ?? 'info'}>{u.role}</Badge>
                                        </td>
                                        <td className="py-2 px-2 text-center">
                                            <span className={`text-xs ${u.status === 'active' ? 'text-success' : 'text-text-secondary'}`}>
                                                {u.status === 'active' ? '🟢' : '⚪'} {u.status}
                                            </span>
                                        </td>
                                        <td className="py-2 px-2 text-xs text-text-secondary">
                                            {u.createdAt ? new Date(u.createdAt).toLocaleDateString('zh-CN') : '-'}
                                        </td>
                                        <td className="py-2 px-2 text-xs text-text-secondary">
                                            {u.lastActive ? new Date(u.lastActive).toLocaleString('zh-CN') : '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </SectionCard>
            )}
        </PageContainer>
    );
}
