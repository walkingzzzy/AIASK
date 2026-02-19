'use client';

import { ChatMsg } from '@/store/chat-store';

export default function ChatMessage({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] px-3.5 py-2.5 rounded-xl whitespace-pre-wrap break-words leading-relaxed text-sm ${
          isUser ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-900'
        }`}
      >
        {msg.content || (msg.toolCalls?.length ? null : <span className="opacity-50">...</span>)}
        {msg.toolCalls?.map((tc, i) => (
          <div
            key={i}
            className={`mt-1.5 px-2.5 py-1.5 rounded-md text-xs ${
              isUser ? 'bg-white/15' : 'bg-blue-50'
            }`}
          >
            {tc.pending ? '\u23F3' : '\u2705'} 调用工具: {tc.name}
            {tc.result != null && !tc.pending ? (
              <details className="mt-1">
                <summary className="cursor-pointer text-[11px] text-gray-500">查看结果</summary>
                <pre className="text-[11px] max-h-40 overflow-auto mt-1 mb-0 whitespace-pre-wrap">
                  {typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2)}
                </pre>
              </details>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
