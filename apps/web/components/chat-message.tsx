'use client';

import { ChatActionBlock, ChatMsg } from '@/store/chat-store';

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
        {msg.content || (msg.toolCalls?.length ? null : <span className="opacity-50">...</span>)}
        {msg.toolCalls?.map((tc, i) => (
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
