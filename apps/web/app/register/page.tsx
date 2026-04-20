'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui';
import { setLoggedIn } from '@/lib/auth';
import { useHydrated } from '@/hooks/use-hydrated';

const REGISTER_ACTION = '/api/auth/register';

const REGISTER_STEPS = [
  {
    title: '创建账户',
    description: '输入用户名和密码即可完成注册。',
  },
  {
    title: '直接进入平台',
    description: '注册成功后自动进入 `/market`。',
  },
] as const;

export default function RegisterPage() {
  const hydrated = useHydrated();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitRegistration() {
    if (!hydrated || loading) return;
    setError(null);

    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
      return;
    }
    if (password.length < 6) {
      setError('密码至少6个字符');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(REGISTER_ACTION, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username, password }),
        credentials: 'include',
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const nextError =
          (body && typeof body === 'object' && 'error' in body && body.error && typeof body.error === 'object'
            ? (body.error as { message?: string }).message
            : null) ||
          (body && typeof body === 'object' && 'message' in body ? String(body.message) : null);
        throw new Error(nextError || `注册失败：HTTP ${response.status}`);
      }

      setLoggedIn();
      window.location.assign('/market');
    } catch (e) {
      setError(e instanceof Error ? e.message : '注册失败');
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitRegistration();
  }

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1180px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_460px]">
        <section className="page-hero p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Register Workspace</Badge>
            <Badge variant="neutral">New Account</Badge>
          </div>
          <h1 className="mt-3">创建你的 AI 股票研究工作台。</h1>
          <p className="page-lead mt-3 mb-0">注册后直接进入平台首页，再继续完善自选、组合和策略配置。</p>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {REGISTER_STEPS.map((item, index) => (
              <div key={item.title} className="metric-tile rounded-[22px] px-4 py-4">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/12 text-xs font-semibold text-primary">
                    {index + 1}
                  </span>
                  <div className="metric-label">{item.title}</div>
                </div>
                <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">{item.description}</p>
              </div>
            ))}
          </div>

          <div className="panel-soft mt-6 rounded-[28px] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">注册后重点</div>
                <h2 className="mt-2">先进入行情页，再决定下一步</h2>
              </div>
              <Link
                href="/login"
                className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-secondary no-underline shadow-sm"
              >
                已有账号，去登录
              </Link>
            </div>
            <div className="mt-4 text-sm leading-6 text-text-secondary">
              表单保持最少字段，提交前只做密码长度和确认密码校验。
            </div>
          </div>
        </section>

        <section className="panel-solid rounded-[30px] p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warning">账户注册</Badge>
            <Badge variant="neutral">Create Access</Badge>
          </div>
          <h2 className="mt-2">创建账号</h2>
          <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">提交后会直接创建账号并进入 `/market`。</p>

          <form onSubmit={onSubmit} noValidate className="mt-6 grid gap-4">
            <label htmlFor="reg-username" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">用户名</span>
              <input
                id="reg-username"
                type="text"
                name="username"
                placeholder="请输入用户名"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="px-3 py-2.5 text-sm"
              />
            </label>

            <label htmlFor="reg-password" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">密码</span>
              <input
                id="reg-password"
                type="password"
                name="password"
                placeholder="至少 6 位"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="px-3 py-2.5 text-sm"
              />
            </label>

            <label htmlFor="reg-confirm" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">确认密码</span>
              <input
                id="reg-confirm"
                type="password"
                name="confirmPassword"
                placeholder="再次输入密码"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="px-3 py-2.5 text-sm"
              />
            </label>

            {error ? (
              <p
                className="m-0 rounded-[18px] border border-danger/18 bg-danger/8 px-3 py-2 text-sm text-error"
                role="alert"
              >
                {error}
              </p>
            ) : null}

            <button
              type="button"
              onClick={() => void submitRegistration()}
              disabled={!hydrated || loading}
              data-testid="register-submit-action"
              className="min-h-11 rounded-full bg-primary px-4 py-2.5 text-white shadow-sm disabled:opacity-50"
            >
              {!hydrated ? '页面初始化中...' : loading ? '注册中...' : '创建账号'}
            </button>
          </form>

          <div className="panel-soft mt-4 rounded-[20px] px-4 py-3 text-xs leading-5 text-text-secondary">
            提交前会先校验密码长度和确认密码一致性，避免错误请求先发出去再失败。
          </div>

          <p className="mb-0 mt-4 text-sm text-text-secondary">
            已有账号？
            <Link href="/login" className="ml-1 text-primary underline underline-offset-4">
              去登录
            </Link>
          </p>
        </section>
      </div>
    </main>
  );
}
