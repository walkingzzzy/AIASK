'use client';

import { useEffect, useState } from 'react';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { authedFetch, fmt } from '@/lib/api';
import type { Envelope } from '@aiask/shared-types';
import { PageContainer, SectionCard } from '@/components/ui';
import { clearCookies } from '@/lib/auth';

type UserInfo = { username?: string; role?: string; riskLevel?: string };
const RISK_OPTIONS = ['保守', '稳健', '激进'] as const;

export default function UserPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [riskLevel, setRiskLevel] = useState('稳健');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await authedFetch('/auth/me');
        const data = ((await r.json()) as Envelope<Record<string, unknown>>).data ?? {};
        const info: UserInfo = {
          username: data.username as string,
          role: data.role as string,
          riskLevel: data.riskLevel as string,
        };
        setUser(info);
        if (info.riskLevel) setRiskLevel(info.riskLevel);
      } catch (err) {
        setError(err instanceof Error ? err.message : '获取用户信息失败');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onSave() {
    setSaving(true);
    setError(null);
    try {
      await authedFetch('/auth/profile', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ riskLevel }),
      });
      setUser((prev) => (prev ? { ...prev, riskLevel } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  function onLogout() {
    clearCookies();
    window.location.href = '/login';
  }

  return (
    <PageContainer>
      <h1>用户中心</h1>
      {loading ? <LoadingState text="加载用户信息..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      {!loading && !user && !error ? <EmptyState text="未获取到用户信息" /> : null}
      {user ? (
        <SectionCard className="p-4">
          <h3 className="mt-0">个人信息</h3>
          <div className="mb-2">用户名：{fmt(user.username)}</div>
          <div className="mb-2">角色：{fmt(user.role)}</div>
          <div className="mb-2">当前风险等级：{fmt(user.riskLevel)}</div>
          <div className="flex gap-2.5 items-center mt-4">
            <label>风险等级：</label>
            <select value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)} className="border border-border rounded px-2 py-1">
              {RISK_OPTIONS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={saving}
              onClick={onSave}
              className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm"
            >
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </SectionCard>
      ) : null}
      <div className="mt-6">
        <button
          type="button"
          onClick={onLogout}
          className="bg-danger text-white border-none px-5 py-2 rounded-md cursor-pointer"
        >
          退出登录
        </button>
      </div>
    </PageContainer>
  );
}
