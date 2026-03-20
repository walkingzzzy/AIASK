'use client';

import { useState, useMemo } from 'react';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { ErrorState } from '@/components/status-state';

type AuditEntry = {
    id: string;
    action: string;
    user: string;
    ip?: string;
    timestamp: string;
    detail?: string;
    resource?: string;
};

type RawAuditEntry = {
    id?: string;
    trace_id?: string;
    action?: string;
    user?: string | { id?: string; username?: string; role?: string } | null;
    ip?: string;
    timestamp?: string;
    ts?: string;
    detail?: string;
    resource?: string;
    method?: string;
    path?: string;
    status?: number;
    duration_ms?: number;
};

function readRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return {};
    }
    return value as Record<string, unknown>;
}

function parseAuditError(raw: string) {
    const normalized = String(raw || '').trim();
    const traceId = normalized.match(/trace(?:[_\s-]?id)?[:=]\s*([A-Za-z0-9-]+)/i)?.[1] ?? null;
    const path = normalized.match(/(\/[A-Za-z0-9/_-]+)/)?.[1] ?? null;
    const status = normalized.match(/\b(401|403|404|500)\b/)?.[1] ?? null;
    const permissionDenied = /403|forbidden|权限|permission/i.test(normalized);

    return {
        message: permissionDenied ? '当前账号没有查看审计日志的权限。' : '审计日志暂时不可用，请稍后重试。',
        hint: permissionDenied
            ? '如果你需要排查线上问题，请联系管理员为当前账号开通审计日志读取权限。'
            : '你仍可以继续使用其他设置页功能；如果问题持续，再查看下面的技术详情。',
        details: [
            status ? `状态码：${status}` : null,
            path ? `接口：${path}` : null,
            traceId ? `Trace ID：${traceId}` : null,
            normalized ? `原始错误：${normalized}` : null,
        ].filter(Boolean) as string[],
    };
}

function normalizeAuditEntry(entry: RawAuditEntry, index: number): AuditEntry {
    const user = typeof entry.user === 'string'
        ? entry.user
        : entry.user && typeof entry.user === 'object'
            ? String(entry.user.username ?? entry.user.id ?? '系统')
            : '系统';
    const timestamp = String(entry.timestamp ?? entry.ts ?? '');
    const action = entry.action
        ? String(entry.action)
        : [entry.method, entry.path, entry.status].filter((item) => item !== undefined && item !== null && item !== '').join(' ');
    const detail = entry.detail
        ? String(entry.detail)
        : entry.duration_ms != null
            ? `${entry.duration_ms}ms`
            : undefined;
    const resource = entry.resource ? String(entry.resource) : entry.path ? String(entry.path) : undefined;

    return {
        id: String(entry.id ?? entry.trace_id ?? `${entry.method ?? 'audit'}-${entry.path ?? 'log'}-${timestamp || index}`),
        action,
        user,
        ip: entry.ip ? String(entry.ip) : undefined,
        timestamp,
        detail,
        resource,
    };
}

/**
 * T-038: Audit Log Page
 * Displays operation logs with time/user/action/IP/detail.
 */
export default function AuditLogPage() {
    const [filter, setFilter] = useState<string>('all');

    const logsQ = useApiQuery<unknown>('/audit/logs?limit=100', {
        refetchInterval: 30000,
        parse: (raw) => raw,
    });

    const rawLogs: AuditEntry[] = useMemo(() => {
        const data = readRecord(logsQ.data);
        const nested = readRecord(data.data);
        const items = data.items ?? nested.items ?? data.logs ?? [];
        return Array.isArray(items) ? items.map((item, index) => normalizeAuditEntry(item as RawAuditEntry, index)) : [];
    }, [logsQ.data]);

    const logs = useMemo(() => {
        return filter === 'all' ? rawLogs : rawLogs.filter((l) => l.action?.includes(filter));
    }, [rawLogs, filter]);
    const friendlyError = useMemo(() => logsQ.error ? parseAuditError(logsQ.error) : null, [logsQ.error]);

    const actionTypes = useMemo(() => {
        const set = new Set<string>();
        rawLogs.forEach((l) => { if (l.action) set.add(l.action); });
        return Array.from(set);
    }, [rawLogs]);

    const formatTimestamp = (value: string) => {
        if (!value) return '-';
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return value;
        return parsed.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    return (
        <PageContainer>
            <div className="mb-4">
                <h1 className="text-lg font-semibold m-0">📋 操作审计日志</h1>
                <p className="mt-1 mb-0 text-sm text-text-secondary">展示最近 100 条操作记录。若当前账户没有权限，会直接显示错误原因而不是空白页。</p>
            </div>

            <div className="flex gap-2 mb-4 flex-wrap">
                <button
                    onClick={() => setFilter('all')}
                    className={`text-xs px-3 py-1 rounded-full cursor-pointer ${filter === 'all' ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface border border-glass-border text-text-secondary'
                        }`}
                >
                    全部 ({rawLogs.length})
                </button>
                {actionTypes.slice(0, 8).map((t) => (
                    <button
                        key={t}
                        onClick={() => setFilter(t)}
                        className={`text-xs px-3 py-1 rounded-full cursor-pointer ${filter === t ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface border border-glass-border text-text-secondary'
                            }`}
                    >
                        {t}
                    </button>
                ))}
            </div>

            {friendlyError ? (
                <>
                    <ErrorState
                        text={friendlyError.message}
                        hint={friendlyError.hint}
                        onRetry={() => logsQ.refetch()}
                    />
                    <SectionCard className="mt-3 p-4">
                        <h3 className="mt-0 text-sm font-medium">技术详情</h3>
                        <p className="mt-1 mb-2 text-xs text-text-secondary">下面的信息主要用于排查权限或接口问题，普通使用时可以忽略。</p>
                        <details>
                            <summary className="cursor-pointer text-sm text-text-secondary">展开查看原始错误</summary>
                            <ul className="mt-2 mb-0 list-disc pl-5 text-xs text-text-secondary space-y-1">
                                {friendlyError.details.map((detail) => (
                                    <li key={detail}>{detail}</li>
                                ))}
                            </ul>
                        </details>
                    </SectionCard>
                </>
            ) : null}

            {!friendlyError && logs.length === 0 ? (
                <SectionCard>
                    <div className="text-center py-12 text-text-secondary text-sm">
                        {logsQ.isFetching ? '加载中...' : '暂无审计日志'}
                    </div>
                </SectionCard>
            ) : (
                <SectionCard>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-2 px-2">时间</th>
                                    <th className="text-left py-2 px-2">用户</th>
                                    <th className="text-left py-2 px-2">操作</th>
                                    <th className="text-left py-2 px-2">资源</th>
                                    <th className="text-left py-2 px-2">IP</th>
                                    <th className="text-left py-2 px-2">详情</th>
                                </tr>
                            </thead>
                            <tbody>
                                {logs.map((log) => (
                                    <tr key={log.id} className="border-b border-glass-border/50 hover:bg-white/5">
                                        <td className="py-2 px-2 whitespace-nowrap text-xs">
                                            {formatTimestamp(log.timestamp)}
                                        </td>
                                        <td className="py-2 px-2 whitespace-nowrap">{log.user}</td>
                                        <td className="py-2 px-2">
                                            <Badge variant={log.action?.includes('delete') ? 'danger' : log.action?.includes('create') ? 'success' : 'info'}>
                                                {log.action}
                                            </Badge>
                                        </td>
                                        <td className="py-2 px-2 text-text-secondary max-w-[150px] truncate">{log.resource || '-'}</td>
                                        <td className="py-2 px-2 text-text-secondary text-xs">{log.ip || '-'}</td>
                                        <td className="py-2 px-2 text-text-secondary text-xs max-w-[200px] truncate">{log.detail || '-'}</td>
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
