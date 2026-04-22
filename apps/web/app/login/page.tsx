'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/ui';
import { normalizeAppRedirectPath, setLoggedIn } from '@/lib/auth';
import { useHydrated } from '@/hooks/use-hydrated';

const LOGIN_ACTION = '/api/auth/login';
const REDIRECT_FALLBACK = '/market';
const OTP_CODE_RE = /^(\d{6}|[A-Za-z0-9]{8})$/;

const LOGIN_HIGHLIGHTS = [
  {
    title: '市场与研究',
    description: '登录后可直接回到行情、个股、自选和研究页面。',
  },
  {
    title: '策略与交易',
    description: '策略超市、回测、模拟交易和风险中心会保留原有上下文。',
  },
] as const;

const LOGIN_CAPABILITIES = [
  { label: '市场观察', value: '行情、个股、自选、告警' },
  { label: '研究验证', value: '研究、策略、回测、模拟交易' },
] as const;

export default function LoginPage() {
  const hydrated = useHydrated();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitLogin() {
    if (!hydrated || loading) return;
    const normalizedUsername = username.trim();
    const normalizedOtpCode = otpCode.trim().replace(/\s+/g, '').toUpperCase();

    if (!normalizedUsername) {
      setError('请输入用户名');
      return;
    }
    if (!password) {
      setError('请输入密码');
      return;
    }
    if (password.length < 3) {
      setError('密码至少 3 个字符');
      return;
    }
    if (normalizedOtpCode && !OTP_CODE_RE.test(normalizedOtpCode)) {
      setError('2FA 验证码必须为 6 位动态码或 8 位恢复码');
      return;
    }

    setLoading(true);
    setError(null);
    const redirectTo = normalizeAppRedirectPath(
      new URLSearchParams(window.location.search).get('redirect'),
      REDIRECT_FALLBACK,
    );

    try {
      const response = await fetch(LOGIN_ACTION, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          username: normalizedUsername,
          password,
          otpCode: normalizedOtpCode || undefined,
        }),
        credentials: 'include',
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const nextError =
          (body && typeof body === 'object' && 'error' in body && body.error && typeof body.error === 'object'
            ? (body.error as { message?: string }).message
            : null) ||
          (body && typeof body === 'object' && 'message' in body ? String(body.message) : null);
        throw new Error(nextError || `登录失败：HTTP ${response.status}`);
      }

      setLoggedIn();
      window.location.assign(redirectTo);
    } catch (e) {
      setError(e instanceof Error ? e.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitLogin();
  }

  const trimmedUsername = username.trim();
  const trimmedOtpCode = otpCode.trim().replace(/\s+/g, '').toUpperCase();
  const otpCodeValid = !trimmedOtpCode || OTP_CODE_RE.test(trimmedOtpCode);
  const submitDisabled = !hydrated || loading || !trimmedUsername || password.length < 3 || !otpCodeValid;

  return (
    <main className="mx-auto min-h-screen w-full max-w-[clamp(20rem,94vw,86rem)] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] xl:grid-cols-[minmax(0,1.14fr)_minmax(0,0.86fr)]">
        <section className="order-2 min-w-0 page-hero p-6 sm:p-8 lg:order-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">AIASK</Badge>
            <Badge variant="neutral">登录入口</Badge>
          </div>
          <h1 className="mt-3">登录后继续使用 AIASK 的市场、研究、策略与交易能力。</h1>
          <p className="page-lead mt-3 mb-0">
            AIASK 是一个覆盖市场观察、研究分析、策略验证、模拟交易和风险管理的 A 股投研平台。登录后会优先回到你刚才请求的页面。
          </p>

          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {LOGIN_HIGHLIGHTS.map((item) => (
              <div key={item.title} className="metric-tile rounded-[22px] px-4 py-4">
                <div className="metric-label">{item.title}</div>
                <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">{item.description}</p>
              </div>
            ))}
          </div>

          <div className="panel-soft mt-6 rounded-[28px] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">平台能力</div>
                <h2 className="mt-2">登录后可继续访问的核心模块</h2>
              </div>
              <Link
                href="/"
                className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-secondary no-underline shadow-sm"
              >
                查看首页介绍
              </Link>
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {LOGIN_CAPABILITIES.map((item) => (
                <div key={item.label} className="metric-tile rounded-[20px] px-4 py-3">
                  <div className="metric-label">{item.label}</div>
                  <div className="mt-2 text-sm font-semibold text-text-primary">{item.value}</div>
                </div>
              ))}
            </div>
            <div className="metric-tile mt-4 rounded-[20px] px-4 py-3 text-sm leading-6 text-text-secondary">
              登录后会优先回到你刚才访问的页面；如果没有来源页，则进入行情看板。
            </div>
          </div>
        </section>

        <section className="order-1 min-w-0 w-full panel-solid rounded-[30px] p-6 sm:p-8 lg:order-2 lg:justify-self-end lg:max-w-[clamp(22rem,34vw,32rem)]">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="warning">账户登录</Badge>
            <Badge variant="neutral">安全入口</Badge>
          </div>
          <h2 className="mt-2">登录账号</h2>
          <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">使用账号密码登录。已启用 2FA 的账户需要补充动态码或恢复码。</p>

          <form onSubmit={onSubmit} className="mt-6 grid gap-4" noValidate>
            <label htmlFor="login-username" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">用户名</span>
              <input
                id="login-username"
                type="text"
                name="username"
                placeholder="请输入用户名"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  if (error) setError(null);
                }}
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
                required
                minLength={3}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) setError(null);
                }}
                className="px-3 py-2.5 text-sm"
              />
            </label>

            <label htmlFor="login-otp" className="grid gap-1.5">
              <span className="text-sm font-medium text-text-primary">2FA 验证码（如已启用）</span>
              <input
                id="login-otp"
                type="text"
                name="otpCode"
                placeholder="6 位动态码或 8 位恢复码"
                autoComplete="one-time-code"
                maxLength={8}
                value={otpCode}
                onChange={(e) => {
                  setOtpCode(e.target.value.replace(/\s+/g, '').slice(0, 8).toUpperCase());
                  if (error) setError(null);
                }}
                className="px-3 py-2.5 text-sm font-mono tracking-[0.25em]"
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
              disabled={submitDisabled}
              data-testid="login-submit-action"
              className="min-h-11 rounded-full bg-primary px-4 py-2.5 text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {!hydrated ? '页面初始化中...' : loading ? '登录中...' : '登录'}
            </button>
          </form>

          <div className="panel-soft mt-4 rounded-[20px] px-4 py-3 text-xs leading-5 text-text-secondary">
            登录成功后会回到你刚才要访问的位置；如果没有来源页，则进入行情看板。
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
