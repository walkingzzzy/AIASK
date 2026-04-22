'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import ResultWorkbench from '@/components/result-workbench';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { ErrorState } from '@/components/status-state';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';

type AuditEntry = {
  id: string;
  action: string;
  user: string;
  ip?: string;
  timestamp: string;
  detail?: string;
  resource?: string;
  source: 'audit';
};

type BehaviorEntry = {
  id: string;
  action: string;
  timestamp: string;
  detail?: string;
  resource?: string;
  source: 'behavior';
  pageKey?: string;
  route?: string;
};

type CombinedEntry = AuditEntry | BehaviorEntry;

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

type RawBehaviorEntry = {
  id?: string;
  eventType?: string;
  event_type?: string;
  targetLabel?: string;
  target_label?: string;
  targetTestId?: string;
  target_testid?: string;
  route?: string;
  pageKey?: string;
  page_key?: string;
  payload?: Record<string, unknown>;
  source?: string;
  createdAt?: string;
  created_at?: string;
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
    source: 'audit',
  };
}

function normalizeBehaviorEntry(entry: RawBehaviorEntry, index: number): BehaviorEntry {
  const eventType = String(entry.event_type ?? entry.eventType ?? 'behavior');
  const targetLabel = String(entry.target_label ?? entry.targetLabel ?? entry.target_testid ?? entry.targetTestId ?? '').trim();
  const route = String(entry.route ?? '').trim();
  const pageKey = String(entry.page_key ?? entry.pageKey ?? '').trim();
  const payload = entry.payload && typeof entry.payload === 'object' ? entry.payload : {};
  const duration = payload.durationMs != null ? `${String(payload.durationMs)}ms` : undefined;

  return {
    id: String(entry.id ?? `${eventType}-${route || index}`),
    action: targetLabel ? `${eventType} · ${targetLabel}` : eventType,
    timestamp: String(entry.created_at ?? entry.createdAt ?? ''),
    detail: duration,
    resource: route || pageKey || undefined,
    source: 'behavior',
    pageKey: pageKey || undefined,
    route: route || undefined,
  };
}

export default function AuditLogPage() {
  const router = useRouter();
  const [sourceFilter, setSourceFilter] = useState<'all' | 'audit' | 'behavior'>('all');
  const [actionFilter, setActionFilter] = useState<string>('all');

  const logsQ = useApiQuery<unknown>('/audit/my-logs?limit=100', {
    refetchInterval: 30000,
    parse: (raw) => raw,
  });
  const behaviorQ = useApiQuery<unknown>('/behavior/events?limit=100&days=30', {
    refetchInterval: 30000,
    parse: (raw) => raw,
  });

  const auditLogs = useMemo(() => {
    const data = readRecord(logsQ.data);
    const nested = readRecord(data.data);
    const items = data.items ?? nested.items ?? data.logs ?? [];
    return Array.isArray(items) ? items.map((item, index) => normalizeAuditEntry(item as RawAuditEntry, index)) : [];
  }, [logsQ.data]);

  const behaviorLogs = useMemo(() => {
    const data = readRecord(behaviorQ.data);
    const nested = readRecord(data.data);
    const items = data.items ?? nested.items ?? [];
    return Array.isArray(items) ? items.map((item, index) => normalizeBehaviorEntry(item as RawBehaviorEntry, index)) : [];
  }, [behaviorQ.data]);

  const combinedLogs = useMemo(() => {
    const items = [...auditLogs, ...behaviorLogs];
    items.sort((left, right) => {
      const leftTime = new Date(left.timestamp).getTime();
      const rightTime = new Date(right.timestamp).getTime();
      return rightTime - leftTime;
    });
    return items;
  }, [auditLogs, behaviorLogs]);

  const filteredLogs = useMemo(() => {
    return combinedLogs.filter((log) => {
      if (sourceFilter !== 'all' && log.source !== sourceFilter) return false;
      if (actionFilter !== 'all' && !log.action.includes(actionFilter)) return false;
      return true;
    });
  }, [actionFilter, combinedLogs, sourceFilter]);

  const actionTypes = useMemo(() => {
    const set = new Set<string>();
    combinedLogs.forEach((log) => {
      if (log.action) set.add(log.action);
    });
    return Array.from(set).slice(0, 10);
  }, [combinedLogs]);

  const combinedError = useMemo(
    () => (logsQ.error ? parseAuditError(logsQ.error) : behaviorQ.error ? parseAuditError(behaviorQ.error) : null),
    [behaviorQ.error, logsQ.error],
  );

  const pageActions = useMemo(
    () => [
      {
        id: 'audit-log.refresh',
        label: '刷新日志',
        description: '重新拉取后端审计与前端行为轨迹',
        keywords: ['刷新', '日志'],
        scope: 'page' as const,
        pageKey: 'settings-audit-log',
        run: async () => {
          await Promise.allSettled([logsQ.refetch(), behaviorQ.refetch()]);
          return { message: '已刷新审计日志与前端行为轨迹' };
        },
      },
      {
        id: 'audit-log.clear-filters',
        label: '清空筛选',
        description: '恢复显示全部来源与全部动作类型',
        keywords: ['清空', '筛选'],
        scope: 'page' as const,
        pageKey: 'settings-audit-log',
        run: () => {
          setSourceFilter('all');
          setActionFilter('all');
          return { message: '已清空审计页筛选条件' };
        },
      },
      {
        id: 'audit-log.return-settings',
        label: '返回设置页',
        description: '回到设置中心的安全日志标签页',
        keywords: ['设置', '返回'],
        scope: 'page' as const,
        pageKey: 'settings-audit-log',
        run: () => {
          router.push('/settings?tab=security');
          return { message: '已返回设置页' };
        },
      },
    ],
    [behaviorQ, logsQ, router],
  );

  usePageActions(pageActions);
  const auditSummary = `当前过滤来源 ${sourceFilter === 'all' ? '全部' : sourceFilter === 'audit' ? '后端审计' : '前端行为'}，可见 ${filteredLogs.length} 条记录，其中后端审计 ${auditLogs.length} 条、前端行为 ${behaviorLogs.length} 条。`;
  const auditResult = buildLocalResultContract({
    summary: auditSummary,
    availableViews: filteredLogs.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['audit-log.refresh', 'audit-log.clear-filters', 'audit-log.return-settings'],
    recommendedLinks: [
      { id: 'audit-open-assistant-link', label: '继续问 Copilot', href: '/assistant' },
      { id: 'audit-open-admin-tools-link', label: 'MCP 工具页', href: '/admin/tools' },
      { id: 'audit-open-settings-link', label: '返回设置页', href: '/settings?tab=security' },
    ],
    evidence: [
      { label: '可见记录', value: String(filteredLogs.length) },
      { label: '后端审计', value: String(auditLogs.length) },
      { label: '前端行为', value: String(behaviorLogs.length) },
      { label: '来源筛选', value: sourceFilter },
      { label: '动作筛选', value: actionFilter },
    ],
    riskNotes: combinedError ? combinedError.details : [],
    freshness: combinedLogs[0]?.timestamp ? { updatedAt: combinedLogs[0].timestamp, label: '最近日志' } : null,
    platformMeta: {
      sourceTool: 'audit-log',
      sourceChain: ['audit', sourceFilter, actionFilter],
      degraded: Boolean(combinedError),
      fallbackReason: combinedError ? combinedError.details : undefined,
    },
    workbenchTask: defaultWorkbenchTask('settings-audit-log', '复查审计日志', '/settings/audit-log', 'audit-review', {
      sourceFilter,
      actionFilter,
    }),
  });

  usePageContext({
    pageKey: 'settings-audit-log',
    title: '审计日志',
    summary: auditSummary,
    objectType: 'audit-stream',
    objectId: `${sourceFilter}:${actionFilter}`,
    resultType: 'audit-log',
    tags: [
      `${filteredLogs.length} 条可见记录`,
      `${auditLogs.length} 条后端审计`,
      `${behaviorLogs.length} 条前端行为`,
      combinedError ? '存在读取异常' : '读取正常',
    ],
    suggestions: [
      '先总结当前审计页最重要的异常与轨迹',
      '如果需要页面联动，请优先刷新日志或清空筛选',
      '说明哪些是后端审计，哪些是前端行为证据',
    ],
    recommendedActions: auditResult.recommendedActions ?? [],
    recommendedLinks: auditResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(auditResult.evidence),
    riskNotes: auditResult.riskNotes ?? [],
    freshness: auditResult.freshness ?? null,
    raw: {
      sourceFilter,
      actionFilter,
      visibleCount: filteredLogs.length,
      auditCount: auditLogs.length,
      behaviorCount: behaviorLogs.length,
      hasError: Boolean(combinedError),
    },
  });

  const formatTimestamp = (value: string) => {
    if (!value) return '-';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  return (
    <PageContainer>
      <ResultWorkbench pageKey="settings-audit-log" title="审计结果工作台" result={auditResult} />

      <div className="mb-4">
        <h1 className="text-lg font-semibold m-0">📋 操作审计日志</h1>
        <p className="mt-1 mb-0 text-sm text-text-secondary">
          同时展示后端请求审计和前端行为轨迹，方便核对 UI 证据与 AI 可见证据是否一致。
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {[
          { key: 'all', label: `全部 (${combinedLogs.length})` },
          { key: 'audit', label: `后端审计 (${auditLogs.length})` },
          { key: 'behavior', label: `前端行为 (${behaviorLogs.length})` },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setSourceFilter(item.key as 'all' | 'audit' | 'behavior')}
            className={`text-xs px-3 py-1 rounded-full cursor-pointer ${sourceFilter === item.key ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface border border-glass-border text-text-secondary'}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="mb-4 flex gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setActionFilter('all')}
          className={`text-xs px-3 py-1 rounded-full cursor-pointer ${actionFilter === 'all' ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface border border-glass-border text-text-secondary'}`}
        >
          全部动作
        </button>
        {actionTypes.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setActionFilter(t)}
            className={`text-xs px-3 py-1 rounded-full cursor-pointer ${actionFilter === t ? 'bg-primary/20 text-primary border border-primary/40' : 'bg-surface border border-glass-border text-text-secondary'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {combinedError ? (
        <>
          <ErrorState
            text={combinedError.message}
            hint={combinedError.hint}
            onRetry={() => {
              void Promise.allSettled([logsQ.refetch(), behaviorQ.refetch()]);
            }}
          />
          <SectionCard className="mt-3 p-4">
            <h3 className="mt-0 text-sm font-medium">技术详情</h3>
            <p className="mt-1 mb-2 text-xs text-text-secondary">下面的信息主要用于排查权限或接口问题，普通使用时可以忽略。</p>
            <details>
              <summary className="cursor-pointer text-sm text-text-secondary">展开查看原始错误</summary>
              <ul className="mt-2 mb-0 list-disc pl-5 text-xs text-text-secondary space-y-1">
                {combinedError.details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            </details>
          </SectionCard>
        </>
      ) : null}

      {!combinedError && filteredLogs.length === 0 ? (
        <SectionCard>
          <div className="text-center py-12 text-text-secondary text-sm">
            {logsQ.isFetching || behaviorQ.isFetching ? '加载中...' : '暂无日志记录'}
          </div>
        </SectionCard>
      ) : (
        <SectionCard>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-glass-border text-text-secondary text-xs">
                  <th className="text-left py-2 px-2">时间</th>
                  <th className="text-left py-2 px-2">来源</th>
                  <th className="text-left py-2 px-2">操作</th>
                  <th className="text-left py-2 px-2">资源 / 路由</th>
                  <th className="text-left py-2 px-2">用户 / 说明</th>
                  <th className="text-left py-2 px-2">详情</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((log) => (
                  <tr key={`${log.source}-${log.id}`} className="border-b border-glass-border/50 hover:bg-white/5">
                    <td className="py-2 px-2 whitespace-nowrap text-xs">{formatTimestamp(log.timestamp)}</td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      <Badge variant={log.source === 'audit' ? 'info' : 'warning'}>
                        {log.source === 'audit' ? '后端审计' : '前端行为'}
                      </Badge>
                    </td>
                    <td className="py-2 px-2">{log.action}</td>
                    <td className="py-2 px-2 text-text-secondary max-w-[220px] truncate">{log.resource || '-'}</td>
                    <td className="py-2 px-2 text-text-secondary text-xs">
                      {'user' in log ? log.user : `${log.pageKey ?? '-'}${log.route ? ` · ${log.route}` : ''}`}
                    </td>
                    <td className="py-2 px-2 text-text-secondary text-xs max-w-[220px] truncate">{log.detail || '-'}</td>
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
