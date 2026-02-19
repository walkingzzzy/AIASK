'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BFF_BASE } from '@/lib/api';
import type { LoginResponse } from '@aiask/shared-types';

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
      });

      if (!response.ok) {
        throw new Error(`登录失败：HTTP ${response.status}`);
      }

      const payload = (await response.json()) as LoginResponse;
      document.cookie = `access_token=${payload.accessToken}; Path=/; Max-Age=${payload.expiresIn}; SameSite=Lax`;
      document.cookie = `refresh_token=${payload.refreshToken}; Path=/; Max-Age=${7 * 24 * 60 * 60}; SameSite=Lax`;
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
        <input
          type="text"
          name="username"
          placeholder="用户名"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="px-3 py-2 border border-border rounded text-sm"
        />
        <input
          type="password"
          name="password"
          placeholder="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="px-3 py-2 border border-border rounded text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-primary text-white rounded cursor-pointer disabled:opacity-50"
        >
          {loading ? '登录中...' : '登录'}
        </button>
      </form>

      {error ? <p className="text-error mt-3">{error}</p> : null}
    </main>
  );
}
