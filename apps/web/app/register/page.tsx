'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui';
import { setLoggedIn } from '@/lib/auth';

const REGISTER_ACTION = '/api/auth/register';

const REGISTER_STEPS = [
  {
    title: '创建账户',
    description: '使用用户名和密码完成注册，保持现有同源接口和跳转路径。',
  },
  {
    title: '进入工作台',
    description: '注册成功后自动写入登录状态并跳转到 `/market`，减少额外步骤。',
  },
  {
    title: '补齐配置',
    description: '后续再去完善自选、组合、策略和模拟交易，不把所有信息塞在首屏。',
  },
] as const;

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
    <main className="mx-auto min-h-screen w-full max-w-[1180px] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_460px]">
        <section className="page-hero p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Register Workspace</Badge>
            <Badge variant="neutral">New Account</Badge>
          </div>
          <h1 className="mt-3">创建你的 AI 股票研究工作台。</h1>
          <p className="page-lead mt-3 mb-0">
            注册页也切入了统一的 glass
            视觉语言。左侧用更清晰的路径说明告诉用户注册之后会进入什么工作流，右侧把账号创建压缩成更轻的单列面板。
          </p>

          <div className="mt-6 grid gap-3 md:grid-cols-3">
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
                <h2 className="mt-2">先进入核心页面，再逐步补齐个性化配置</h2>
              </div>
              <Link
                href="/login"
                className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-secondary no-underline shadow-sm"
              >
                已有账号，去登录
              </Link>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="metric-tile rounded-[20px] px-4 py-3">
                <div className="metric-label">优先入口</div>
                <div className="mt-2 text-sm font-semibold text-text-primary">行情页、策略页、AI 工作台</div>
              </div>
              <div className="metric-tile rounded-[20px] px-4 py-3">
                <div className="metric-label">表单策略</div>
                <div className="mt-2 text-sm font-semibold text-text-primary">
                  最少字段、清晰标签、提交前完成密码校验
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="panel-solid rounded-[30px] p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warning">账户注册</Badge>
            <Badge variant="neutral">Create Access</Badge>
          </div>
          <h2 className="mt-2">创建账号</h2>
          <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
            保留现有注册链路：提交到同源接口，通过前端完成密码一致性校验，成功后直接进入 `/market`。
          </p>

          <form onSubmit={onSubmit} method="post" action={REGISTER_ACTION} noValidate className="mt-6 grid gap-4">
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
              type="submit"
              disabled={loading}
              className="min-h-11 rounded-full bg-primary px-4 py-2.5 text-white shadow-sm disabled:opacity-50"
            >
              {loading ? '注册中...' : '创建账号'}
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
