'use client';

import { useMemo } from 'react';
import { PageContainer, SectionCard, KpiGrid, KpiCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';

/**
 * T-052: User Management Panel
 */
export default function UsersPage() {
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

    const ROLE_COLORS: Record<string, 'danger' | 'warning' | 'info' | 'success'> = {
        admin: 'danger', trader: 'warning', analyst: 'info', viewer: 'success',
    };

    return (
        <PageContainer>
            <h2 className="text-lg font-semibold mb-4">👥 用户管理</h2>

            <KpiGrid cols={4}>
                <KpiCard title="总用户" value={stats.total.toString()} />
                <KpiCard title="活跃用户" value={stats.active.toString()} />
                <KpiCard title="管理员" value={stats.admins.toString()} />
                <KpiCard title="今日活跃" value={stats.today.toString()} />
            </KpiGrid>

            {users.length === 0 ? (
                <SectionCard className="mt-4">
                    <p className="text-text-secondary text-sm text-center py-12">
                        {usersQ.isFetching ? '加载中...' : '暂无用户数据'}
                    </p>
                </SectionCard>
            ) : (
                <SectionCard className="mt-4 p-3">
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
                                {users.map((u) => (
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
