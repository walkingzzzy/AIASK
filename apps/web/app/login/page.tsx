'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { BFF_BASE } from '@/lib/api';
import { setLoggedIn } from '@/lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${BFF_BASE}/auth/login`, {
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
      const params = new URLSearchParams(window.location.search);
      router.replace(params.get('redirect') || '/market');
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="max-w-[420px] mx-auto mt-20 font-sans px-4">
      <h1>登录</h1>

      <form onSubmit={onSubmit} className="grid gap-3 mt-4">
        <div>
          <label htmlFor="login-username" className="sr-only">用户名</label>
          <input
            id="login-username"
            type="text"
            name="username"
            placeholder="用户名"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded text-sm"
          />
        </div>
        <div>
          <label htmlFor="login-password" className="sr-only">密码</label>
          <input
            id="login-password"
            type="password"
            name="password"
            placeholder="密码"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-primary text-white rounded cursor-pointer disabled:opacity-50"
        >
          {loading ? '登录中...' : '登录'}
        </button>
      </form>

      {error ? <p className="text-error mt-3" role="alert">{error}</p> : null}

      <p className="mt-4 text-sm text-muted-foreground">
        还没有账号？<Link href="/register" className="text-primary underline">去注册</Link>
      </p>
    </main>
  );
}
