'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { BFF_BASE } from '@/lib/api';
import { setLoggedIn } from '@/lib/auth';

export default function RegisterPage() {
  const router = useRouter();
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
      const response = await fetch(`${BFF_BASE}/auth/register`, {
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
      router.replace('/market');
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : '注册失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="max-w-[420px] mx-auto mt-20 font-sans px-4">
      <h1>注册</h1>

      <form onSubmit={onSubmit} className="grid gap-3 mt-4">
        <div>
          <label htmlFor="reg-username" className="sr-only">用户名</label>
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
        </div>
        <div>
          <label htmlFor="reg-password" className="sr-only">密码</label>
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
        </div>
        <div>
          <label htmlFor="reg-confirm" className="sr-only">确认密码</label>
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
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2 bg-primary text-white rounded cursor-pointer disabled:opacity-50"
        >
          {loading ? '注册中...' : '注册'}
        </button>
      </form>

      {error ? <p className="text-error mt-3" role="alert">{error}</p> : null}

      <p className="mt-4 text-sm text-muted-foreground">
        已有账号？<Link href="/login" className="text-primary underline">去登录</Link>
      </p>
    </main>
  );
}
