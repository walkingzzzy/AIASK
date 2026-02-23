'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';
import Link from 'next/link';

type ErrorLevel = { title: string; description: string; actions: Array<{ label: string; href?: string; onClick?: () => void }> };

function classify(error: Error): ErrorLevel {
  const msg = error.message || '';
  if (/fetch|network|ERR_/i.test(msg)) {
    return { title: '网络连接失败', description: '请检查网络连接后重试', actions: [] };
  }
  if (/401|未登录|登录已过期/i.test(msg)) {
    return { title: '登录已过期', description: '请重新登录', actions: [{ label: '去登录', href: '/login' }] };
  }
  if (/403|权限|forbidden/i.test(msg)) {
    return { title: '没有访问权限', description: '当前账号无权访问此页面', actions: [{ label: '返回首页', href: '/' }] };
  }
  if (/5\d{2}|服务/i.test(msg)) {
    return { title: '服务暂时不可用', description: '服务端出现问题，请稍后重试', actions: [] };
  }
  return { title: '出错了', description: msg || '发生了未知错误', actions: [] };
}

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => { Sentry.captureException(error); }, [error]);

  const level = classify(error);

  return (
    <div className="max-w-[600px] mx-auto mt-20 text-center font-sans">
      <h2 className="text-xl font-bold text-error">{level.title}</h2>
      <p className="mt-2 text-text-secondary">{level.description}</p>
      <div className="mt-4 flex gap-3 justify-center">
        <button onClick={reset} className="px-4 py-2 bg-primary text-white rounded cursor-pointer">
          重试
        </button>
        {level.actions.map((a) =>
          a.href ? (
            <Link key={a.label} href={a.href} className="px-4 py-2 border border-border rounded no-underline text-text-secondary">
              {a.label}
            </Link>
          ) : (
            <button key={a.label} onClick={a.onClick} className="px-4 py-2 border border-border rounded cursor-pointer">
              {a.label}
            </button>
          ),
        )}
        <Link href="/" className="px-4 py-2 border border-border rounded no-underline text-text-secondary">
          返回首页
        </Link>
      </div>
    </div>
  );
}
