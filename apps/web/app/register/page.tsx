'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { setLoggedIn } from '@/lib/auth';

const REGISTER_ACTION = '/api/auth/register';

export default function RegisterPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
        throw new Error(body.message || `注册失败：HTTP ${response.status}`);
      }

      setLoggedIn();
      window.location.assign('/market');
    } catch (e) {
      setError(e instanceof Error ? e.message : '注册失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto mt-10 max-w-5xl px-4 font-sans md:mt-16">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(360px,0.95fr)] lg:items-start">
        <section className="rounded-3xl border border-glass-border bg-surface-alt/60 p-6 md:p-8 lg:min-h-[540px]">
          <span className="inline-flex rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs text-primary">新用户引导</span>
          <h1 className="mb-3 mt-4 text-3xl font-semibold">创建你的 AI 股票研究工作台</h1>
          <p className="m-0 max-w-2xl text-sm leading-6 text-text-secondary">
            注册后可统一使用行情、组合、模拟交易、告警和 AI 诊断能力。页面会优先保证提交链路稳定，避免 hydration 前退回为错误原生提交。
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            {[
              ['快速开始', '注册完成后可直接进入行情页，并继续补充自选、策略和组合。'],
              ['安全一致', '注册提交走同源 POST，避免地址栏出现错误 querystring。'],
              ['任务闭环', '后续可从组合、模拟交易和告警中心继续完成完整操作流。'],
            ].map(([title, desc]) => (
              <div key={title} className="rounded-2xl border border-border bg-surface p-4">
                <div className="text-sm font-medium text-text-primary">{title}</div>
                <p className="mb-0 mt-2 text-xs leading-5 text-text-secondary">{desc}</p>
              </div>
            ))}
          </div>
          <div className="mt-6 rounded-2xl border border-border bg-surface p-4">
            <div className="text-sm font-medium">注册前你会得到什么</div>
            <ul className="mb-0 mt-3 space-y-2 pl-5 text-xs leading-5 text-text-secondary">
              <li>清晰的可见表单标签与自动填充语义，降低移动端误填成本。</li>
              <li>密码长度与确认校验会在提交前完成，不让错误请求白跑一遍。</li>
              <li>注册成功后自动写入登录状态并跳转到 /market，减少额外步骤。</li>
            </ul>
          </div>
        </section>

        <section className="rounded-3xl border border-glass-border bg-surface p-6 shadow-sm md:p-8 lg:min-h-[540px]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="m-0 text-2xl font-semibold">注册账号</h2>
              <p className="mb-0 mt-2 text-sm text-text-secondary">使用用户名与密码快速完成注册。若浏览器尚未 hydration，也会保持正确的 POST 降级目标。</p>
            </div>
            <Link href="/login" className="text-sm text-primary underline underline-offset-4">已有账号，去登录</Link>
          </div>

          <form onSubmit={onSubmit} method="post" action={REGISTER_ACTION} noValidate className="mt-6 grid gap-4">
            <div>
              <label htmlFor="reg-username" className="mb-1.5 block text-sm font-medium text-text-primary">用户名</label>
          <input
            id="reg-username"
            type="text"
            name="username"
            placeholder="用户名"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded text-sm"
          />
            <p className="mb-0 mt-1 text-xs text-text-secondary">建议使用便于记忆且不含敏感信息的用户名。</p>
          </div>
          <div>
            <label htmlFor="reg-password" className="mb-1.5 block text-sm font-medium text-text-primary">密码</label>
          <input
            id="reg-password"
            type="password"
            name="password"
            placeholder="密码（至少6位）"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded text-sm"
          />
            <p className="mb-0 mt-1 text-xs text-text-secondary">至少 6 位，建议混合使用字母、数字或符号。</p>
          </div>
          <div>
            <label htmlFor="reg-confirm" className="mb-1.5 block text-sm font-medium text-text-primary">确认密码</label>
          <input
            id="reg-confirm"
            type="password"
            name="confirmPassword"
            placeholder="确认密码"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded text-sm"
          />
            <p className="mb-0 mt-1 text-xs text-text-secondary">再次输入新密码，避免键入错误导致后续无法登录。</p>
          </div>

          {error ? <p className="m-0 rounded-2xl border border-danger/20 bg-danger/10 px-3 py-2 text-sm text-error" role="alert">{error}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="min-h-11 rounded-xl bg-primary px-4 py-2.5 text-white cursor-pointer disabled:opacity-50"
          >
            {loading ? '注册中...' : '创建账号'}
          </button>
          <p className="m-0 text-xs leading-5 text-text-secondary">提交后将通过同源接口创建账号，并在成功后自动进入行情页。</p>
          </form>
        </section>
      </div>
    </main>
  );
}
