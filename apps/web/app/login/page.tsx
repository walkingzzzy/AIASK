'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { setLoggedIn } from '@/lib/auth';
import { useHydrated } from '@/hooks/use-hydrated';

const LOGIN_ACTION = '/api/auth/login';

const LOGIN_HIGHLIGHTS = [
  {
    title: '恢复工作流',
    description: '登录后继续查看上次的行情视图、研究上下文和策略筛选结果。',
  },
  {
    title: '集中式看板',
    description: '同一工作台里统一完成行情、回测、模拟盘和风险巡检。',
  },
  {
    title: '稳定提交链路',
    description: '认证入口保持同源 POST 提交，不改现有登录接口与跳转逻辑。',
  },
] as const;

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
    <main className="mx-auto min-h-screen w-full max-w-[1180px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.14fr)_420px]">
        <section className="rounded-[28px] border border-border bg-surface p-6 shadow-sm sm:p-8">
          <div className="eyebrow">Login Workspace</div>
          <h1 className="mt-3">继续你的行情、研究与交易工作流。</h1>
          <p className="page-lead mt-3 mb-0">
            登录页改成更克制的金融工作台入口。左侧只说明登录后的核心收益，右侧专注账号输入，不再用大面积渐变和装饰性玻璃效果制造噪音。
          </p>

          <div className="mt-6 grid gap-3 md:grid-cols-3">
            {LOGIN_HIGHLIGHTS.map((item) => (
              <div key={item.title} className="rounded-[20px] border border-border bg-surface-alt/72 px-4 py-4">
                <div className="metric-label">{item.title}</div>
                <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">{item.description}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-[24px] border border-border bg-surface-alt/72 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">登录后可用</div>
                <h2 className="mt-2">一个入口，继续完整投研链路</h2>
              </div>
              <Link href="/" className="rounded-full border border-border bg-surface px-4 py-2 text-sm no-underline text-text-secondary">
                返回首页
              </Link>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-[18px] border border-border bg-surface px-4 py-3">
                <div className="metric-label">高频模块</div>
                <div className="mt-2 text-sm font-semibold text-text-primary">行情、策略、模拟交易、AI 工作台</div>
              </div>
              <div className="rounded-[18px] border border-border bg-surface px-4 py-3">
                <div className="metric-label">状态恢复</div>
                <div className="mt-2 text-sm font-semibold text-text-primary">继续上次视图、上下文跳转和自选动作</div>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[28px] border border-border bg-surface p-6 shadow-sm sm:p-8">
          <div className="eyebrow">账户登录</div>
          <h2 className="mt-2">登录账号</h2>
          <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
            表单只保留必要字段。Hydration 完成前按钮保持禁用，避免浏览器回退为错误的原生提交体验。
          </p>

          <form onSubmit={onSubmit} method="post" action={LOGIN_ACTION} className="mt-6 grid gap-4" noValidate>
            <label htmlFor="login-username" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">用户名</span>
              <input
                id="login-username"
                type="text"
                name="username"
                placeholder="请输入用户名"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="px-3 py-2.5 text-sm"
              />
            </label>

            <label htmlFor="login-password" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">密码</span>
              <input
                id="login-password"
                type="password"
                name="password"
                placeholder="请输入密码"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="px-3 py-2.5 text-sm"
              />
            </label>

            {error ? (
              <p className="m-0 rounded-[18px] border border-danger/18 bg-danger/8 px-3 py-2 text-sm text-error" role="alert">
                {error}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={!hydrated || loading}
              className="min-h-11 rounded-xl bg-primary px-4 py-2.5 text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {!hydrated ? '页面初始化中...' : loading ? '登录中...' : '登录'}
            </button>
          </form>

          <div className="mt-4 rounded-[18px] border border-border bg-surface-alt/72 px-4 py-3 text-xs leading-5 text-text-secondary">
            登录成功后会维持现有跳转逻辑：优先回到 `redirect` 指定页面，否则进入 `/market`。
          </div>

          <p className="mb-0 mt-4 text-sm text-text-secondary">
            还没有账号？
            <Link href="/register" className="ml-1 text-primary underline underline-offset-4">
              去注册
            </Link>
          </p>
        </section>
      </div>
    </main>
  );
}
