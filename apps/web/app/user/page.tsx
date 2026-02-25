'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { authedFetch, fmt, BFF_BASE } from '@/lib/api';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { clearLoggedIn } from '@/lib/auth';
import { useAuthStore } from '@/store/auth-store';

type UserInfo = { username?: string; role?: string; riskLevel?: string };
const RISK_OPTIONS = ['保守', '稳健', '激进'] as const;

const QUICK_LINKS = [
  { href: '/portfolio', label: '组合管理', desc: '创建和管理投资组合' },
  { href: '/backtest', label: '策略回测', desc: '验证交易策略表现' },
  { href: '/paper-trading', label: '模拟交易', desc: '无风险模拟下单' },
  { href: '/stock', label: '个股分析', desc: '行情/技术/情绪一站式' },
];

export default function UserPage() {
  const [riskLevel, setRiskLevel] = useState('稳健');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const authedUser = useAuthStore((s) => s.user);
  const userId = authedUser?.id ?? authedUser?.username ?? null;

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const subsQ = useApiQuery<unknown>(
    userId ? `/strategy-market/my-subscriptions?user_id=${encodeURIComponent(userId)}` : null,
    { enabled: Boolean(userId) },
  );
  const tradingQ = useApiQuery<unknown>('/paper-trading/summary');
  const portfolioQ = useApiQuery<unknown>('/portfolio/list');

  const user: UserInfo | null = profileQ.data ? {
    username: profileQ.data.username as string,
    role: profileQ.data.role as string,
    riskLevel: profileQ.data.riskLevel as string,
  } : null;

  // Sync riskLevel from profile on first load
  useEffect(() => {
    if (profileQ.data?.riskLevel) setRiskLevel(profileQ.data.riskLevel as string);
  }, [profileQ.data]);

  async function onSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await authedFetch('/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ riskLevel }),
      });
      profileQ.refetch();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  function onLogout() {
    clearLoggedIn();
    fetch(`${BFF_BASE}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
    window.location.href = '/login';
  }

  const subs = extractArray(subsQ.data, 'strategies', 'items', 'data');
  const tradingData = (tradingQ.data ?? {}) as Record<string, unknown>;
  const acct = (tradingData.account ?? {}) as Record<string, unknown>;
  const totalValue = Number(tradingData.total_value ?? acct.total_value ?? 0);
  const returnPct = Number(tradingData.total_return_pct ?? 0);
  const posCount = Number(tradingData.positions_count ?? 0);
  const portfolios = extractArray(portfolioQ.data, 'portfolios', 'items', 'data');

  return (
    <PageContainer>
      <h1>用户中心</h1>
      {profileQ.isPending ? <LoadingState text="加载用户信息..." /> : null}
      {(profileQ.error || saveError) ? <ErrorState text={(profileQ.error || saveError)!} hint="请稍后重试" /> : null}
      {!profileQ.isPending && !user && !profileQ.error ? <EmptyState text="未获取到用户信息" /> : null}

      {user ? (
        <SectionCard className="p-4">
          <div className="flex items-center justify-between">
            <h3 className="mt-0">个人信息</h3>
            <button type="button" onClick={onLogout}
              className="text-xs bg-danger/10 text-danger px-3 py-1 rounded cursor-pointer hover:bg-danger/20">
              退出登录
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
            <div className="glass rounded-lg p-3">
              <div className="text-text-secondary text-xs">用户名</div>
              <div className="font-medium">{fmt(user.username)}</div>
            </div>
            <div className="glass rounded-lg p-3">
              <div className="text-text-secondary text-xs">角色</div>
              <div className="font-medium">{fmt(user.role)}</div>
            </div>
            <div className="glass rounded-lg p-3">
              <div className="text-text-secondary text-xs">风险等级</div>
              <div className="flex items-center gap-2 mt-1">
                <select value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)} className="text-sm px-2 py-1 rounded">
                  {RISK_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
                <button type="button" disabled={saving} onClick={onSave}
                  className="text-xs px-2 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50">
                  {saving ? '...' : '保存'}
                </button>
              </div>
            </div>
          </div>
        </SectionCard>
      ) : null}

      {/* Paper Trading Summary */}
      {tradingQ.data != null && (
        <SectionCard className="p-4 mt-4">
          <h3 className="mt-0 flex items-center gap-2">模拟交易概览 <Badge variant="info">实时</Badge></h3>
          <KpiGrid cols={3}>
            <KpiCard title="总资产" value={fmtNum(totalValue)} />
            <KpiCard title="总收益率" value={fmtPct(returnPct)} change={returnPct} />
            <KpiCard title="持仓数" value={String(posCount)} />
          </KpiGrid>
        </SectionCard>
      )}

      {/* My Subscriptions */}
      <SectionCard className="p-4 mt-4">
        <h3 className="mt-0 flex items-center gap-2">
          我的订阅 <Badge variant={subs.length > 0 ? 'success' : 'neutral'}>{subs.length}</Badge>
        </h3>
        {subsQ.isPending ? <LoadingState text="加载中..." /> : null}
        {subs.length > 0 ? (
          <DataTable
            columns={[
              { key: 'name', label: '策略名称' },
              { key: 'strategy_type', label: '类型' },
              { key: 'subscribed_at', label: '订阅时间', render: (v: unknown) => String(v ?? '-').slice(0, 10) },
            ]}
            rows={subs as Record<string, unknown>[]}
          />
        ) : !subsQ.isPending ? <p className="text-text-muted text-sm">暂无订阅策略，前往<Link href="/strategy-market" className="text-primary underline mx-1">策略超市</Link>浏览</p> : null}
      </SectionCard>

      {/* My Portfolios */}
      <SectionCard className="p-4 mt-4">
        <h3 className="mt-0 flex items-center gap-2">
          我的组合 <Badge variant={portfolios.length > 0 ? 'info' : 'neutral'}>{portfolios.length}</Badge>
        </h3>
        {portfolioQ.isPending ? <LoadingState text="加载中..." /> : null}
        {portfolios.length > 0 ? (
          <DataTable
            columns={[
              { key: 'name', label: '组合名称' },
              { key: 'total_assets', label: '总资产', render: (v: unknown) => fmtNum(Number(v)) },
              { key: 'total_return', label: '收益率', render: (v: unknown) => fmtPct(Number(v)) },
            ]}
            rows={portfolios as Record<string, unknown>[]}
          />
        ) : !portfolioQ.isPending ? <p className="text-text-muted text-sm">暂无组合，前往<Link href="/portfolio" className="text-primary underline mx-1">组合管理</Link>创建</p> : null}
      </SectionCard>

      {/* Quick Links */}
      <SectionCard className="p-4 mt-4">
        <h3 className="mt-0">快捷入口</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {QUICK_LINKS.map((lk) => (
            <Link key={lk.href} href={lk.href} className="glass glass-hover rounded-xl p-4 text-center no-underline text-inherit">
              <div className="font-medium text-sm">{lk.label}</div>
              <div className="text-xs text-text-muted mt-1">{lk.desc}</div>
            </Link>
          ))}
        </div>
      </SectionCard>
    </PageContainer>
  );
}
