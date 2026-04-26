'use client';

import { ChatActionBlock, ChatMsg } from '@/store/chat-store';
import type { ChatToolTrace, ChatToolTraceItem } from '@/lib/tool-trace-types';

function formatTraceTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function traceKindLabel(kind: ChatToolTraceItem['kind']) {
  if (kind === 'mcp') return 'MCP';
  if (kind === 'local_context') return '本地上下文';
  return '页面动作';
}

function traceStatusLabel(item: ChatToolTraceItem) {
  if (item.status === 'pending') return '调用中';
  if (item.status === 'success') return '成功';
  return '失败';
}

function evidenceModeLabel(trace: ChatToolTrace) {
  if (trace.evidenceMode === 'mcp_supported') return 'MCP 证据支持';
  if (trace.evidenceMode === 'tool_supported') return '工具证据支持';
  if (trace.evidenceMode === 'page_context_supported') return '页面上下文支持';
  return '纯建议态';
}

function statusTone(status: ChatToolTraceItem['status']) {
  if (status === 'success') return 'border-success/40 bg-success/10 text-success';
  if (status === 'error') return 'border-danger/40 bg-danger/10 text-danger';
  return 'border-warning/40 bg-warning/10 text-warning';
}

function ToolTracePanel({ trace, isUser }: { trace: ChatToolTrace; isUser: boolean }) {
  const mcpCount = trace.items.filter((item) => item.kind === 'mcp').length;
  const successCount = trace.items.filter((item) => item.status === 'success').length;
  const errorCount = trace.items.filter((item) => item.status === 'error').length;
  const referenced = trace.answerReferences;

  return (
    <details
      className={`mt-2 rounded-xl border px-3 py-2 text-xs ${isUser ? 'border-white/20 bg-white/10' : 'border-border bg-surface-alt/60'}`}
    >
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium text-text-primary">工具轨迹</span>
          <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-text-secondary">
            {evidenceModeLabel(trace)}
          </span>
        </div>
        <div className="mt-1 text-[11px] text-text-muted">
          {trace.items.length > 0
            ? `${trace.items.length} 次工具记录，其中 MCP ${mcpCount} 次，成功 ${successCount} 次${errorCount ? `，失败 ${errorCount} 次` : ''}`
            : '本次没有实际 MCP 工具调用'}
        </div>
      </summary>

      <div className="mt-3 space-y-2">
        {trace.advisoryReason ? (
          <div className="rounded-lg border border-border bg-surface px-2.5 py-2 text-[11px] text-text-secondary">
            {trace.advisoryReason}
          </div>
        ) : null}

        {trace.items.map((item) => (
          <div key={item.id} className="rounded-lg border border-border bg-surface px-2.5 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <span className="font-semibold text-text-primary">[{item.referenceLabel}]</span>
                <span className="ml-1 break-all font-medium text-text-primary">{item.toolName}</span>
                <span className="ml-2 text-[11px] text-text-muted">{traceKindLabel(item.kind)}</span>
              </div>
              <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(item.status)}`}>
                {traceStatusLabel(item)}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-text-muted">
              {formatTraceTime(item.startedAt)}
              {item.finishedAt ? ` - ${formatTraceTime(item.finishedAt)}` : ''}
              {typeof item.durationMs === 'number' ? ` · ${item.durationMs}ms` : ''}
            </div>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[11px] font-medium text-text-secondary">关键输入</div>
                <ul className="m-0 space-y-1 p-0">
                  {item.inputSummary.map((line, index) => (
                    <li key={`${item.id}-input-${index}`} className="list-none break-all text-[11px] text-text-secondary">
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="mb-1 text-[11px] font-medium text-text-secondary">返回摘要</div>
                <ul className="m-0 space-y-1 p-0">
                  {(item.outputSummary.length ? item.outputSummary : ['等待返回']).map((line, index) => (
                    <li key={`${item.id}-output-${index}`} className="list-none break-all text-[11px] text-text-secondary">
                      {line}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ))}

        <div className="rounded-lg border border-border bg-surface px-2.5 py-2">
          <div className="text-[11px] font-medium text-text-secondary">最终答案引用</div>
          {referenced.length ? (
            <ul className="m-0 mt-1 space-y-1 p-0">
              {referenced.map((ref) => (
                <li key={`${ref.itemId}-${ref.referenceLabel}`} className="list-none break-all text-[11px] text-text-secondary">
                  [{ref.referenceLabel}] {ref.toolName}: {ref.evidenceSummary}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-1 text-[11px] text-text-muted">最终答案未显式标注工具结果引用。</div>
          )}
        </div>
      </div>
    </details>
  );
}

export default function ChatMessage({
  msg,
  onActionClick,
}: {
  msg: ChatMsg;
  onActionClick?: (action: ChatActionBlock, messageId: string) => void;
}) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] sm:max-w-[75%] px-3 py-2.5 sm:px-3.5 rounded-xl whitespace-pre-wrap wrap-break-word leading-relaxed text-sm ${
          isUser ? 'bg-primary text-white' : 'surface-card text-text'
        }`}
      >
        {msg.content || (msg.toolCalls?.length || msg.toolTrace ? null : <span className="opacity-50">...</span>)}
        {msg.toolTrace ? <ToolTracePanel trace={msg.toolTrace} isUser={isUser} /> : null}
        {!msg.toolTrace && msg.toolCalls?.map((tc, i) => (
          <div
            key={i}
            className={`mt-1.5 px-2.5 py-1.5 rounded-md text-xs ${
              isUser ? 'bg-white/15' : 'bg-surface-alt/50'
            }`}
          >
            {tc.pending ? '\u23F3' : '\u2705'} 调用工具: {tc.name}
            {tc.result != null && !tc.pending ? (
              <details className="mt-1">
                <summary className="cursor-pointer text-[11px] text-text-muted">查看结果</summary>
                <pre className="text-[11px] max-h-40 overflow-auto mt-1 mb-0 whitespace-pre-wrap">
                  {typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2)}
                </pre>
              </details>
            ) : null}
          </div>
        ))}
        {msg.actions?.map((action) => (
          <div
            key={action.id}
            className={`mt-2 rounded-xl border px-3 py-2 text-xs ${
              isUser ? 'border-white/20 bg-white/10' : 'border-glass-border bg-surface-alt/50'
            }`}
          >
            <div className="font-medium text-text-primary">{action.label}</div>
            {action.description ? <div className="mt-1 text-text-secondary">{action.description}</div> : null}
            {action.reason ? <div className="mt-1 text-text-muted">原因: {action.reason}</div> : null}
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-[11px] text-text-muted">
                {action.status === 'running'
                  ? '执行中'
                  : action.status === 'done'
                    ? '已完成'
                    : action.status === 'error'
                      ? '执行失败'
                      : '待执行'}
              </span>
              {action.status !== 'running' && action.status !== 'done' ? (
                <button
                  type="button"
                  onClick={() => onActionClick?.(action, msg.id)}
                  className="rounded-full border border-primary/40 px-3 py-1 text-[11px] text-primary"
                >
                  执行动作
                </button>
              ) : null}
            </div>
            {action.resultMessage ? <div className="mt-2 text-[11px] text-text-secondary">{action.resultMessage}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
