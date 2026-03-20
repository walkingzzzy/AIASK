'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { setLoggedIn } from '@/lib/auth';
import { useHydrated } from '@/hooks/use-hydrated';

const LOGIN_ACTION = '/api/auth/login';

export default function LoginPage() {
  const hydrated = useHydrated();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hydrated || loading) return;
    setLoading(true);
    setError(null);
    const redirectTo = new URLSearchParams(window.location.search).get('redirect') || '/market';

    try {
      const response = await fetch(LOGIN_ACTION, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username, password }),
        credentials: 'include',
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.message || `登录失败：HTTP ${response.status}`);
      }

      setLoggedIn();
      window.location.assign(redirectTo);
    } catch (e) {
      setError(e instanceof Error ? e.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto mt-10 max-w-[960px] px-4 py-8 font-sans sm:mt-16">
      <div className="grid gap-6 rounded-3xl border border-glass-border bg-white/75 p-5 shadow-lg backdrop-blur md:grid-cols-[minmax(0,1.1fr)_420px] md:p-8">
        <section className="flex min-h-[420px] flex-col justify-between rounded-2xl bg-gradient-to-br from-primary/10 via-white/40 to-purple-500/10 p-6">
          <div>
            <p className="mb-2 text-sm font-medium text-primary">AIASK 智能股票分析</p>
            <h1 className="mb-3 text-3xl font-semibold">登录后继续查看行情、回测与交易任务流</h1>
            <p className="m-0 max-w-[42ch] text-sm leading-6 text-text-secondary">
              登录页首屏已改为稳定双栏布局：左侧承接产品价值与使用提示，右侧专注账号登录，避免在不同设备上出现内容抖动或大片留白。
            </p>
          </div>
          <div className="grid gap-3 text-sm text-text-secondary sm:grid-cols-2">
            <div className="rounded-2xl border border-white/60 bg-white/70 p-4">
              <div className="font-medium text-text">盘中看板</div>
              <div className="mt-1">登录后可直接恢复上次行情视图与自选任务入口。</div>
            </div>
            <div className="rounded-2xl border border-white/60 bg-white/70 p-4">
              <div className="font-medium text-text">回测与告警</div>
              <div className="mt-1">统一查看策略回测、模拟盘、风险巡检和告警状态。</div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-white p-5 shadow-sm">
          <h2 className="mt-0 mb-1 text-2xl">账号登录</h2>
          <p className="mt-0 text-sm text-text-secondary">在 hydration 完成前按钮会保持禁用，避免浏览器回退为原生 GET 提交。</p>

          <form onSubmit={onSubmit} method="post" action={LOGIN_ACTION} className="mt-5 grid gap-4" noValidate>
            <div className="grid gap-1.5">
              <label htmlFor="login-username" className="text-sm font-medium text-text">用户名</label>
              <input
                id="login-username"
                type="text"
                name="username"
                placeholder="请输入用户名"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-xl border border-border px-3 py-2.5 text-sm"
              />
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="login-password" className="text-sm font-medium text-text">密码</label>
              <input
                id="login-password"
                type="password"
                name="password"
                placeholder="请输入密码"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-border px-3 py-2.5 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={!hydrated || loading}
              className="min-h-11 rounded-xl bg-primary px-4 py-2.5 text-white cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
            >
              {!hydrated ? '页面初始化中...' : loading ? '登录中...' : '登录'}
            </button>
          </form>

          {error ? <p className="mt-3 text-sm text-error" role="alert">{error}</p> : null}

          <p className="mt-4 text-sm text-muted-foreground">
            还没有账号？<Link href="/register" className="text-primary underline">去注册</Link>
          </p>
        </section>
      </div>
    </main>
  );
}
