'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useChatStore } from '@/store/chat-store';
import { getLlmConfig, streamChat } from '@/lib/chat-api';
import ChatMessage from '@/components/chat-message';
import dynamic from 'next/dynamic';

const ChatConfigModal = dynamic(() => import('@/components/chat-config-modal'), { ssr: false });

export default function ChatPage() {
  const { messages, streaming, configLoaded, hasConfig, showConfig,
    addUserMessage, addAssistantMessage, appendAssistantDelta,
    addToolCall, resolveToolCall, setStreaming, setConfigLoaded, setShowConfig, clearMessages,
  } = useChatStore();

  const [input, setInput] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);
  const quickPrompts = [
    '帮我看 600519 今天的风险点',
    '对比 000858 和 600519 的基本面',
    '总结一下当前市场情绪',
  ];
  const setupPrompt = '请告诉我还没配置模型前，这个页面能帮我完成什么。';
  const inputDisabled = streaming;
  const placeholder = hasConfig ? '输入你的问题...' : '可以先输入问题；点击发送时会先引导你完成模型配置';
  const introCards = useMemo(() => ([
    { title: '盘中问答', desc: '快速追问风险点、板块异动、资金情绪与新闻影响。' },
    { title: '个股对比', desc: '直接比较两只股票的基本面、估值、趋势和潜在催化。' },
    { title: '策略解释', desc: '让 AI 把复杂分析结果整理成可执行的下一步动作。' },
  ]), []);

  useEffect(() => {
    void useChatStore.getState().initSync();
    if (!configLoaded) {
      getLlmConfig().then((c) => {
        setConfigLoaded(true, !!c);
      }).catch(() => setConfigLoaded(true, false));
    }
  }, [configLoaded, setConfigLoaded]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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

    const history = [...useChatStore.getState().messages.slice(0, -1)].map((m) => ({
      role: m.role, content: m.content,
    }));
    const abort = new AbortController();
    abortRef.current = abort;

    try {
      await streamChat(history, (event) => {
        switch (event.type) {
          case 'delta': appendAssistantDelta(assistantId, event.content); break;
          case 'tool_call': addToolCall(assistantId, event.name, event.args); break;
          case 'tool_result': resolveToolCall(assistantId, event.name, event.result); break;
          case 'error': appendAssistantDelta(assistantId, `\n\u26A0\uFE0F ${event.message}`); break;
          case 'done': break;
        }
      }, abort.signal);
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        appendAssistantDelta(assistantId, `\n\u26A0\uFE0F ${(err as Error).message ?? '请求失败'}`);
      }
    }
    setStreaming(false);
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void send();
  }

  function closeConfigModal() {
    setShowConfig(false);
    window.requestAnimationFrame(() => settingsButtonRef.current?.focus());
  }

  return (
    <main className="flex flex-col h-full font-sans" aria-labelledby="chat-page-title">
      <div className="px-5 py-3 border-b border-glass-border flex items-center justify-between">
        <div>
          <h1 id="chat-page-title" className="m-0 text-lg">AI 对话</h1>
          {!hasConfig ? <p className="m-0 mt-1 text-xs text-text-secondary">当前还没有配置 LLM，但你仍可以先查看示例问题和能力说明，再主动决定是否去配置。</p> : null}
        </div>
        <div className="flex gap-2">
          {messages.length > 0 ? <button type="button" onClick={clearMessages} className="cursor-pointer px-3 py-1">清空</button> : null}
          <button
            ref={settingsButtonRef}
            type="button"
            onClick={() => setShowConfig(true)}
            className="cursor-pointer px-3 py-1"
            aria-haspopup="dialog"
            aria-expanded={showConfig}
          >
            {'\u2699'} 设置
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto px-5 py-4">
        {!hasConfig ? (
          <div className="mx-auto mb-4 max-w-4xl rounded-2xl border border-primary/20 bg-primary/5 px-4 py-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-sm font-medium text-text-primary">还没配置模型，也不必先被弹窗打断</div>
                <p className="mb-0 mt-1 text-xs leading-5 text-text-secondary">你可以先看示例提问、理解页面价值，再在准备好时点击“设置”完成模型接入。配置完成后当前会话区会直接可用。</p>
              </div>
              <div className="flex gap-2 flex-wrap">
                <button type="button" onClick={() => setInput(setupPrompt)} className="rounded-full border border-border px-3 py-1.5 text-xs cursor-pointer hover:bg-surface">查看引导示例</button>
                <button type="button" onClick={() => setShowConfig(true)} className="rounded-full bg-primary px-3 py-1.5 text-xs text-white cursor-pointer">去配置模型</button>
              </div>
            </div>
          </div>
        ) : null}
        {!messages.length ? (
          <div className="max-w-2xl mx-auto mt-14 rounded-2xl border border-glass-border bg-surface-alt/60 px-6 py-8 text-center text-text-muted">
            <p className="text-base m-0">你好，我是 AI 股票分析助手</p>
            <p className="text-[13px] mt-2 mb-0">可以问我股票行情、基本面、技术面和策略相关的问题。</p>
            <div className="mt-5 grid gap-3 sm:grid-cols-3 text-left">
              {introCards.map((item) => (
                <div key={item.title} className="rounded-xl border border-border bg-surface px-4 py-3">
                  <div className="text-sm font-medium text-text-primary">{item.title}</div>
                  <p className="mb-0 mt-2 text-xs leading-5 text-text-secondary">{item.desc}</p>
                </div>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setInput(prompt)}
                  className="px-3 py-1.5 rounded-full border border-border text-sm cursor-pointer hover:bg-surface"
                >
                  {prompt}
                </button>
              ))}
            </div>
            {!hasConfig ? <p className="text-xs text-text-secondary mt-3 mb-0">示例问题会先填入输入框；真正发送前只需完成一次模型配置即可。</p> : null}
          </div>
        ) : null}
        {messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
        <div ref={bottomRef} />
      </div>
        <form onSubmit={handleSubmit} className="px-5 py-3 border-t border-glass-border flex gap-2">
        <label htmlFor="chat-composer-input" className="sr-only">聊天输入框</label>
        <input
          id="chat-composer-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(); } }}
          placeholder={placeholder}
          disabled={inputDisabled}
          aria-label="聊天输入框"
          className="flex-1 px-3 py-2 rounded-md border border-glass-border text-sm"
        />
        {streaming ? (
          <button type="button" onClick={stop} className="px-4 py-2 cursor-pointer bg-danger text-white border-none rounded-md">停止</button>
        ) : (
            <button type="submit" disabled={!input.trim()} className="px-4 py-2 cursor-pointer bg-primary text-white border-none rounded-md disabled:opacity-50">{hasConfig ? '发送' : '继续并配置'}</button>
        )}
      </form>
      {showConfig ? <ChatConfigModal onClose={closeConfigModal} /> : null}
    </main>
  );
}
