'use client';

import dynamic from 'next/dynamic';
import { FormEvent, startTransition, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { pageActionBus } from '@/lib/page-action-bus';
import { getLlmConfig, streamChat } from '@/lib/chat-api';
import type { CopilotActionMeta } from '@/lib/copilot-types';
import ChatMessage from '@/components/chat-message';
import { useChatStore, type ChatActionBlock } from '@/store/chat-store';
import { useCopilotStore } from '@/store/copilot-store';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

const ChatConfigModal = dynamic(() => import('@/components/chat-config-modal'), { ssr: false });

const DEFAULT_PROMPTS = [
  '总结当前页面最值得关注的信号',
  '给我一个下一步操作建议',
  '把当前页面数据整理成行动清单',
];

function summarizeActionResult(result: unknown): string {
  if (typeof result === 'string' && result.trim()) {
    return result.slice(0, 120);
  }
  if (result && typeof result === 'object') {
    const record = result as Record<string, unknown>;
    if (typeof record.message === 'string' && record.message.trim()) {
      return record.message.slice(0, 120);
    }
    if (typeof record.status === 'string' && record.status.trim()) {
      return `动作返回状态: ${record.status}`;
    }
  }
  return '动作已执行';
}

function ActionChip({
  action,
  onClick,
}: {
  action: CopilotActionMeta;
  onClick: (action: CopilotActionMeta) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(action)}
      className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary transition hover:bg-surface-alt"
      title={action.description ?? action.label}
    >
      {action.label}
    </button>
  );
}

export default function CopilotDock({
  className = '',
  variant = 'dock',
  style,
}: {
  className?: string;
  variant?: 'dock' | 'page';
  style?: CSSProperties;
}) {
  const {
    messages,
    conversations,
    currentConversationId,
    streaming,
    configLoaded,
    hasConfig,
    showConfig,
    syncReady,
    addUserMessage,
    addAssistantMessage,
    appendAssistantDelta,
    addToolCall,
    resolveToolCall,
    addActionBlock,
    updateActionBlock,
    setStreaming,
    setConfigLoaded,
    setShowConfig,
    clearMessages,
    switchConversation,
    createConversation,
    assignConversationWorkspace,
    ensureWorkspaceConversation,
  } = useChatStore();
  const pageContext = useCopilotStore((state) => state.pageContext);
  const globalActions = useCopilotStore((state) => state.globalActions);
  const pageActions = useCopilotStore((state) => state.pageActions);
  const pendingInject = useCopilotStore((state) => state.pendingInject);
  const setPendingInject = useCopilotStore((state) => state.setPendingInject);
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);

  const [input, setInput] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);
  const availableActions = useMemo(() => [...pageActions, ...globalActions], [globalActions, pageActions]);
  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const currentConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === currentConversationId) ?? null,
    [conversations, currentConversationId],
  );
  const workspaceConversationId = activeWorkspace.context.copilotConversationId ?? '';
  const quickPrompts = useMemo(
    () => (pageContext?.suggestions?.length ? pageContext.suggestions : DEFAULT_PROMPTS),
    [pageContext?.suggestions],
  );

  useEffect(() => {
    void useChatStore.getState().initSync();
    if (!configLoaded) {
      getLlmConfig().then((config) => {
        setConfigLoaded(true, !!config);
      }).catch(() => setConfigLoaded(true, false));
    }
  }, [configLoaded, setConfigLoaded]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 消费 AskAiButton 注入的 pendingInject：预填输入框
  useEffect(() => {
    if (!pendingInject) return;
    const prompt = pendingInject.prompt;
    queueMicrotask(() => {
      startTransition(() => {
        setInput(prompt);
        setPendingInject(null);
      });
    });
  }, [pendingInject, setPendingInject]);

  useEffect(() => {
    if (!syncReady || !workbenchHydrated) return;
    const title = `${activeWorkspace.name} Copilot`;
    const resolvedConversationId = ensureWorkspaceConversation(
      activeWorkspace.id,
      title,
      workspaceConversationId || null,
    );

    if (resolvedConversationId && resolvedConversationId !== workspaceConversationId) {
      updateWorkbenchContext({ copilotConversationId: resolvedConversationId });
    }
  }, [
    activeWorkspace.id,
    activeWorkspace.name,
    ensureWorkspaceConversation,
    syncReady,
    updateWorkbenchContext,
    workbenchHydrated,
    workspaceConversationId,
  ]);

  async function executeAction(messageId: string, action: ChatActionBlock) {
    updateActionBlock(messageId, action.id, { status: 'running', resultMessage: '正在执行页面动作...' });
    try {
      const result = await pageActionBus.execute(action.actionId, action.payload);
      updateActionBlock(messageId, action.id, {
        status: 'done',
        resultMessage: summarizeActionResult(result),
      });
    } catch (error) {
      updateActionBlock(messageId, action.id, {
        status: 'error',
        resultMessage: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async function triggerActionChip(action: CopilotActionMeta) {
    const assistantId = addAssistantMessage();
    const actionId = addActionBlock(assistantId, {
      actionId: action.id,
      label: action.label,
      description: action.description,
      status: 'pending',
    });

    await executeAction(assistantId, {
      id: actionId,
      kind: 'action',
      actionId: action.id,
      label: action.label,
      description: action.description,
      status: 'pending',
    });
  }

  function handleConversationChange(nextConversationId: string) {
    if (!nextConversationId) return;
    switchConversation(nextConversationId);
    const selected = conversations.find((conversation) => conversation.id === nextConversationId);
    if (selected && !selected.workspaceId) {
      assignConversationWorkspace(nextConversationId, activeWorkspace.id, `${activeWorkspace.name} Copilot`);
    }
    if (workspaceConversationId !== nextConversationId) {
      updateWorkbenchContext({ copilotConversationId: nextConversationId });
    }
  }

  function handleCreateConversation() {
    const nextConversationId = createConversation({
      title: `${activeWorkspace.name} Copilot`,
      workspaceId: activeWorkspace.id,
    });
    updateWorkbenchContext({ copilotConversationId: nextConversationId });
  }

  async function send() {
    const text = input.trim();
    if (!text || streaming || !hasConfig) {
      if (!hasConfig) setShowConfig(true);
      return;
    }

    setInput('');
    addUserMessage(text);
    const assistantId = addAssistantMessage();
    setStreaming(true);

    const history = useChatStore.getState().messages.slice(0, -1).map((message) => ({
      role: message.role,
      content: message.content,
    }));

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      await streamChat(
        history,
        (event) => {
          switch (event.type) {
            case 'delta':
              appendAssistantDelta(assistantId, event.content);
              break;
            case 'tool_call':
              addToolCall(assistantId, event.name, event.args);
              break;
            case 'tool_result':
              resolveToolCall(assistantId, event.name, event.result);
              break;
            case 'action': {
              const actionBlockId = addActionBlock(assistantId, {
                actionId: event.actionId,
                label: event.label,
                description: event.description,
                reason: event.reason,
                payload: event.payload,
                status: event.autoExecute === false ? 'pending' : 'running',
                autoExecute: event.autoExecute,
                resultMessage: event.autoExecute === false ? '等待手动执行' : '正在执行页面动作...',
              });

              if (event.autoExecute !== false) {
                void executeAction(assistantId, {
                  id: actionBlockId,
                  kind: 'action',
                  actionId: event.actionId,
                  label: event.label,
                  description: event.description,
                  reason: event.reason,
                  payload: event.payload,
                  status: 'running',
                  autoExecute: event.autoExecute,
                });
              }
              break;
            }
            case 'error':
              appendAssistantDelta(assistantId, `\n⚠ ${event.message}`);
              break;
            case 'done':
              break;
          }
        },
        abort.signal,
        {
          mode: variant === 'page' ? 'chat' : 'copilot',
          pageContext,
          availableActions,
        },
      );
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        appendAssistantDelta(assistantId, `\n⚠ ${(error as Error).message ?? '请求失败'}`);
      }
    }

    setStreaming(false);
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send();
  }

  function closeConfigModal() {
    setShowConfig(false);
    window.requestAnimationFrame(() => settingsButtonRef.current?.focus());
  }

  const shellClassName = variant === 'page'
    ? 'flex h-full min-h-0 flex-col rounded-[28px] border border-border bg-surface shadow-[0_24px_80px_rgba(15,23,42,0.08)]'
    : 'flex h-full min-h-0 flex-col border-l border-border bg-surface';

  return (
    <aside className={`${shellClassName} ${className}`} style={style}>
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-text-primary">AI 工作台</div>
          <div className="mt-1 text-xs text-text-secondary">
            {pageContext ? `正在联动 ${pageContext.title}` : '可直接对话，也可联动当前页面动作'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleCreateConversation}
            className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs"
          >
            新会话
          </button>
          {messages.length > 0 ? (
            <button type="button" onClick={clearMessages} className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs">
              清空
            </button>
          ) : null}
          <button
            ref={settingsButtonRef}
            type="button"
            onClick={() => setShowConfig(true)}
            className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs"
          >
            设置
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <section className="mb-4 rounded-2xl border border-border bg-surface-alt/60 p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">工作区会话</div>
              <div className="mt-2 truncate text-sm font-medium text-text-primary">
                {activeWorkspace.name}
                {currentConversation?.title ? <span className="ml-2 text-xs font-normal text-text-secondary">· {currentConversation.title}</span> : null}
              </div>
            </div>
            <span className="rounded-full bg-surface px-2.5 py-1 text-[11px] text-text-secondary">
              {syncReady ? `${conversations.length} 个会话` : '同步中'}
            </span>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <select
              value={currentConversationId}
              onChange={(event) => handleConversationChange(event.target.value)}
              className="min-w-0 flex-1 rounded-xl border border-border bg-surface px-3 py-2 text-sm"
            >
              {conversations.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title}
                  {conversation.workspaceId === activeWorkspace.id ? ' · 当前工作区' : ''}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleCreateConversation}
              className="rounded-xl border border-border bg-surface px-3 py-2 text-xs"
            >
              新建
            </button>
          </div>
        </section>

        {pageContext ? (
          <section className="mb-4 rounded-2xl border border-border bg-surface-alt/60 p-3">
            <div className="text-xs font-medium uppercase tracking-[0.16em] text-text-muted">页面上下文</div>
            <div className="mt-2 text-sm font-medium text-text-primary">
              {pageContext.title}
              {pageContext.stockCode ? <span className="ml-2 font-mono text-xs text-primary">{pageContext.stockCode}</span> : null}
            </div>
            <div className="mt-2 text-xs leading-5 text-text-secondary">{pageContext.summary}</div>
            {pageContext.tags?.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {pageContext.tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-surface px-2.5 py-1 text-[11px] text-text-secondary">
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}

        {availableActions.length ? (
          <section className="mb-4">
            <div className="mb-2 text-xs font-medium uppercase tracking-[0.16em] text-text-muted">可执行联动</div>
            <div className="flex flex-wrap gap-2">
              {availableActions.slice(0, 10).map((action) => (
                <ActionChip key={action.id} action={action} onClick={(item) => void triggerActionChip(item)} />
              ))}
            </div>
          </section>
        ) : null}

        {!hasConfig ? (
          <div className="mb-4 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-4">
            <div className="text-sm font-medium text-text-primary">尚未配置模型</div>
            <p className="mb-0 mt-2 text-xs leading-5 text-text-secondary">
              配置完成后，右侧 Copilot 会自动带着当前页面上下文和可执行动作参与对话。
            </p>
            <button type="button" onClick={() => setShowConfig(true)} className="mt-3 rounded-full bg-primary px-3 py-1.5 text-xs text-white">
              去配置模型
            </button>
          </div>
        ) : null}

        {!messages.length ? (
          <div className="rounded-2xl border border-border bg-surface-alt/60 px-4 py-5 text-sm text-text-secondary">
            <div className="text-text-primary">这个面板会读取当前页面上下文，并可以联动导航与页面动作。</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setInput(prompt)}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs transition hover:bg-surface-alt"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            msg={message}
            onActionClick={(action, messageId) => {
              void executeAction(messageId, action);
            }}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="border-t border-border px-4 py-3">
        <label htmlFor={`copilot-input-${variant}`} className="sr-only">AI 输入框</label>
        <textarea
          id={`copilot-input-${variant}`}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder={hasConfig ? '输入问题，Copilot 会结合当前页面进行回答...' : '输入问题后，发送时会提示先完成模型配置'}
          disabled={streaming}
          rows={variant === 'page' ? 4 : 3}
          className="min-h-[96px] w-full resize-none rounded-2xl border border-border bg-surface px-3 py-3 text-sm"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="text-[11px] leading-5 text-text-muted">
            {pageContext ? `${pageContext.title} · ${availableActions.length} 个可联动动作` : '当前未挂载页面上下文'}
          </div>
          {streaming ? (
            <button type="button" onClick={stop} className="rounded-full bg-danger px-4 py-2 text-xs text-white">
              停止
            </button>
          ) : (
            <button type="submit" disabled={!input.trim()} className="rounded-full bg-primary px-4 py-2 text-xs text-white disabled:opacity-50">
              {hasConfig ? '发送' : '继续并配置'}
            </button>
          )}
        </div>
      </form>

      {showConfig ? <ChatConfigModal onClose={closeConfigModal} /> : null}
    </aside>
  );
}
