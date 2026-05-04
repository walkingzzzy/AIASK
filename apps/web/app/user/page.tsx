'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { authedFetch, extractApiErrorMessage, fmt } from '@/lib/api';
import { PageContainer, KpiCard, KpiGrid, DataTable, Badge, Skeleton } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { useAuthStore } from '@/store/auth-store';

type UserInfo = { username?: string; role?: string; riskLevel?: string };

const RISK_OPTIONS = ['保守', '稳健', '激进'] as const;
const QUICK_LINKS = [
  { href: '/portfolio', label: '组合管理', desc: '创建和管理投资组合' },
  { href: '/backtest', label: '策略回测', desc: '验证交易策略表现' },
  { href: '/paper-trading', label: '模拟交易', desc: '无风险模拟下单' },
  { href: '/stock', label: '个股分析', desc: '行情、技术、情绪一站式' },
];

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

export default function UserPage() {
  const [riskLevel, setRiskLevel] = useState('稳健');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

  const authedUser = useAuthStore((state) => state.user);
  const isLoggingOut = useAuthStore((state) => state.isLoggingOut);
  const logout = useAuthStore((state) => state.logout);

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const subsQ = useApiQuery<unknown>(authedUser ? '/strategy-market/my-subscriptions' : null, {
    enabled: Boolean(authedUser),
  });
  const tradingQ = useApiQuery<unknown>('/paper-trading/summary');
  const portfolioQ = useApiQuery<unknown>('/portfolio/list');

  const user: UserInfo | null = profileQ.data
    ? {
        username: profileQ.data.username as string,
        role: profileQ.data.role as string,
        riskLevel: profileQ.data.riskLevel as string,
      }
    : null;

  useEffect(() => {
    if (profileQ.data?.riskLevel) setRiskLevel(profileQ.data.riskLevel as string);
  }, [profileQ.data]);

  async function onSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const response = await authedFetch('/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ riskLevel }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(extractApiErrorMessage(payload, '保存失败'));
      }
      profileQ.refetch();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  function onLogout() {
    if (isLoggingOut) return;
    logout();
    window.location.href = '/login';
  }

  const subs = extractArray(subsQ.data, 'strategies', 'items', 'data');
  const tradingData = (tradingQ.data ?? {}) as Record<string, unknown>;
  const account = (tradingData.account ?? {}) as Record<string, unknown>;
  const totalValue = Number(tradingData.total_value ?? account.total_value ?? 0);
  const returnPct = Number(tradingData.total_return_pct ?? 0);
  const positionCount = Number(tradingData.positions_count ?? 0);
  const portfolios = extractArray(portfolioQ.data, 'portfolios', 'items', 'data');

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">用户中心</Badge>
              <Badge variant={user ? 'success' : 'warning'}>
                {user ? `当前用户 ${fmt(user.username)}` : '等待加载用户信息'}
              </Badge>
              <Badge variant="neutral">{riskLevel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              用户中心工作台
            </h1>
            <p className="mb-0 mt-3 hidden max-w-3xl text-sm leading-7 text-text-secondary sm:block sm:text-[15px]">
              这一页用来串起账号信息、风险偏好、模拟交易概览、策略订阅和组合资产。先确认风险等级与账户状态，再决定是回组合、回测还是模拟交易继续工作。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={onSave} disabled={saving} className={HERO_PRIMARY_BUTTON_CLS}>
                {saving ? '保存中...' : '保存风险偏好'}
              </button>
              {user ? (
                <button type="button" onClick={onLogout} disabled={isLoggingOut} className={HERO_SECONDARY_BUTTON_CLS}>
                  {isLoggingOut ? '退出中...' : '退出登录'}
                </button>
              ) : null}
            </div>

            <div className="mt-5 hidden gap-3 md:grid md:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">用户</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{fmt(user?.username) || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">{fmt(user?.role) || '等待角色信息'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">风险偏好</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{riskLevel}</div>
                <div className="mt-1 text-xs text-text-secondary">用于后续工作流里的默认偏好设置</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">订阅策略</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{subs.length}</div>
                <div className="mt-1 text-xs text-text-secondary">反映你当前持续关注的策略数量</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">资产组合</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{portfolios.length}</div>
                <div className="mt-1 text-xs text-text-secondary">当前账户下可继续联动的组合数</div>
              </div>
            </div>
          </div>

          <div className="hidden gap-3 md:grid">
            <div className="panel-soft rounded-[28px] p-4 sm:p-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">工作区摘要</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  总资产：<span className="font-medium text-text-primary">{fmtNum(totalValue)}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  总收益率：<span className="font-medium text-text-primary">{fmtPct(returnPct)}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  持仓数：<span className="font-medium text-text-primary">{positionCount}</span>
                </div>
              </div>
            </div>

            <div className="panel-soft rounded-[28px] p-4 sm:p-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">快捷跳转</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {QUICK_LINKS.map((link) => (
                  <Link key={link.href} href={link.href} className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {profileQ.error || saveError ? <ErrorState text={(profileQ.error || saveError)!} hint="请稍后重试" /> : null}

      <KpiGrid cols={4} className={`${compactLayout ? 'hidden ' : ''}mb-4`}>
        <KpiCard title="总资产" value={fmtNum(totalValue)} />
        <KpiCard title="总收益率" value={fmtPct(returnPct)} change={returnPct} />
        <KpiCard title="持仓数" value={String(positionCount)} />
        <KpiCard title="订阅策略" value={String(subs.length)} />
      </KpiGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(320px,1.08fr)]">
        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="eyebrow">个人资料</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">个人信息</h2>
            </div>
          </div>

          {profileQ.isPending ? (
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="metric-tile rounded-[24px] p-4">
                  <Skeleton width="35%" height={12} />
                  <Skeleton className="mt-3" width="72%" height={22} />
                  {index === 2 ? <Skeleton className="mt-3" width="58%" height={32} /> : null}
                </div>
              ))}
            </div>
          ) : user ? (
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="metric-tile rounded-[24px] p-4">
                <div className="text-xs text-text-secondary">用户名</div>
                <div className="mt-2 font-medium text-text-primary">{fmt(user.username)}</div>
              </div>
              <div className="metric-tile rounded-[24px] p-4">
                <div className="text-xs text-text-secondary">角色</div>
                <div className="mt-2 font-medium text-text-primary">{fmt(user.role)}</div>
              </div>
              <div className="metric-tile rounded-[24px] p-4">
                <label htmlFor="user-risk-level" className="text-xs text-text-secondary">
                  风险等级
                </label>
                <div className="mt-3 flex items-end gap-2">
                  <select
                    id="user-risk-level"
                    value={riskLevel}
                    onChange={(e) => setRiskLevel(e.target.value)}
                    className={FIELD_CLS}
                  >
                    {RISK_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          ) : !profileQ.error ? (
            <EmptyState text="未获取到用户信息" />
          ) : null}
        </div>

        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="eyebrow">快捷操作</div>
          <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">快捷入口</h2>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-2">
            {QUICK_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="metric-tile rounded-[24px] p-4 text-center no-underline text-inherit transition hover:-translate-y-0.5"
              >
                <div className="text-sm font-medium text-text-primary">{link.label}</div>
                <div className="mt-1 text-xs text-text-muted">{link.desc}</div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {compactLayout ? (
        <details className="mt-4 rounded-[24px] border border-white/45 bg-white/24 px-4 py-3">
          <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
            展开账户资产、策略订阅与组合摘要
          </summary>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className={NOTE_CARD_CLS}>
              总资产：<span className="font-medium text-text-primary">{fmtNum(totalValue)}</span>
            </div>
            <div className={NOTE_CARD_CLS}>
              订阅策略：<span className="font-medium text-text-primary">{subs.length}</span>
            </div>
            <div className={NOTE_CARD_CLS}>
              资产组合：<span className="font-medium text-text-primary">{portfolios.length}</span>
            </div>
            <Link href="/strategy-market" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
              去策略超市
            </Link>
            <Link href="/portfolio" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
              去组合管理
            </Link>
            <Link href="/paper-trading" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
              去模拟交易
            </Link>
          </div>
        </details>
      ) : null}

      {!compactLayout && tradingQ.data != null ? (
        <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <div className="eyebrow">交易摘要</div>
            <Badge variant="info">实时</Badge>
          </div>
          <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">模拟交易概览</h2>
          <KpiGrid cols={3} className="mt-4">
            <KpiCard title="总资产" value={fmtNum(totalValue)} />
            <KpiCard title="总收益率" value={fmtPct(returnPct)} change={returnPct} />
            <KpiCard title="持仓数" value={String(positionCount)} />
          </KpiGrid>
        </div>
      ) : null}

      {!compactLayout ? (
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <div className="eyebrow">订阅信息</div>
            <Badge variant={subs.length > 0 ? 'success' : 'neutral'}>{subs.length}</Badge>
          </div>
          <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">我的订阅</h2>
          {subsQ.isPending ? <LoadingState text="加载中..." /> : null}
          {subs.length > 0 ? (
            <div className="mt-4">
              <DataTable
                columns={[
                  { key: 'name', label: '策略名称' },
                  { key: 'strategy_type', label: '类型' },
                  {
                    key: 'subscribed_at',
                    label: '订阅时间',
                    render: (value: unknown) => String(value ?? '-').slice(0, 10),
                  },
                ]}
                rows={subs as Record<string, unknown>[]}
              />
            </div>
          ) : !subsQ.isPending ? (
            <EmptyState
              text="暂无订阅策略"
              hint="可以先去策略超市浏览，再把常看策略拉回到个人工作台。"
              action={
                <Link href="/strategy-market" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  去策略超市
                </Link>
              }
            />
          ) : null}
        </div>

        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <div className="eyebrow">组合信息</div>
            <Badge variant={portfolios.length > 0 ? 'info' : 'neutral'}>{portfolios.length}</Badge>
          </div>
          <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">我的组合</h2>
          {portfolioQ.isPending ? <LoadingState text="加载中..." /> : null}
          {portfolios.length > 0 ? (
            <div className="mt-4">
              <DataTable
                columns={[
                  { key: 'name', label: '组合名称' },
                  {
                    key: 'currentValue',
                    label: '总资产',
                    render: (_: unknown, row: Record<string, unknown>) => {
                      const currentValue = Number(
                        row.currentValue ?? row.current_value ?? row.totalAssets ?? row.total_assets ?? 0,
                      );
                      return fmtNum(currentValue);
                    },
                  },
                  {
                    key: 'totalReturn',
                    label: '收益率',
                    render: (_: unknown, row: Record<string, unknown>) => {
                      const currentValue = Number(
                        row.currentValue ?? row.current_value ?? row.totalAssets ?? row.total_assets ?? 0,
                      );
                      const initialCapital = Number(row.initialCapital ?? row.initial_capital ?? 0);
                      const fallbackReturn =
                        initialCapital > 0 ? ((currentValue - initialCapital) / initialCapital) * 100 : 0;
                      const totalReturn = Number(row.totalReturn ?? row.total_return ?? fallbackReturn);
                      return fmtPct(totalReturn);
                    },
                  },
                ]}
                rows={portfolios as Record<string, unknown>[]}
              />
            </div>
          ) : !portfolioQ.isPending ? (
            <EmptyState
              text="暂无组合"
              hint="建议先创建至少一个组合，后续风险页、绩效页和调仓页都会围绕它展开。"
              action={
                <Link href="/portfolio" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  去组合管理
                </Link>
              }
            />
          ) : null}
        </div>
      </div>
      ) : null}
    </PageContainer>
  );
}
