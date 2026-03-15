'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
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

  useEffect(() => {
    void useChatStore.getState().initSync();
    if (!configLoaded) {
      getLlmConfig().then((c) => {
        setConfigLoaded(true, !!c);
        if (!c) setShowConfig(true);
      }).catch(() => setConfigLoaded(true, false));
    }
  }, [configLoaded, setConfigLoaded, setShowConfig]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || streaming) return;
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
          {!hasConfig ? <p className="m-0 mt-1 text-xs text-text-secondary">当前还没有配置 LLM，先完成设置后才能开始发消息。</p> : null}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={clearMessages} className="cursor-pointer px-3 py-1">清空</button>
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
        {!messages.length ? (
          <div className="text-center text-text-muted mt-20">
            <p className="text-base">你好，我是 AI 股票分析助手</p>
            <p className="text-[13px]">可以问我任何关于股票行情、基本面、技术面的问题</p>
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
          placeholder={hasConfig ? '输入你的问题...' : '请先点击右上角设置配置 LLM'}
          disabled={!hasConfig}
          aria-label="聊天输入框"
          className="flex-1 px-3 py-2 rounded-md border border-glass-border text-sm"
        />
        {streaming ? (
          <button type="button" onClick={stop} className="px-4 py-2 cursor-pointer bg-danger text-white border-none rounded-md">停止</button>
        ) : (
          <button type="submit" disabled={!hasConfig || !input.trim()} className="px-4 py-2 cursor-pointer bg-primary text-white border-none rounded-md">发送</button>
        )}
      </form>
      {showConfig ? <ChatConfigModal onClose={closeConfigModal} /> : null}
    </main>
  );
}
