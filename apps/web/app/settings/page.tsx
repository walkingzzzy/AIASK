'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Badge, DataTable, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { LoadingState, UnavailableState } from '@/components/status-state';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { useToast } from '@/components/ui/toast';
import { useAuthStore } from '@/store/auth-store';
import { clearLoggedIn } from '@/lib/auth';
import { getLlmConfig, saveLlmConfig, probeModels } from '@/lib/chat-api';
import { useChatStore } from '@/store/chat-store';

type TabKey = 'account' | 'ai' | 'security' | 'sessions';
const TABS = [
  { key: 'account', label: '账户信息' },
  { key: 'ai', label: 'AI 模型' },
  { key: 'security', label: '安全日志' },
  { key: 'sessions', label: '活跃会话' },
] as const;
const RISK_OPTIONS = ['保守', '稳健', '激进'] as const;

const LABEL_CLS = 'mb-1 block text-xs font-medium text-text-secondary';
const INPUT_CLS = 'w-full rounded-xl border border-glass-border bg-white/55 px-3 py-2.5 text-sm outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';
const BTN_PRIMARY = 'cursor-pointer rounded-full bg-primary px-5 py-2 text-sm font-medium text-white shadow-sm transition hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:translate-y-0';
const BTN_GHOST = 'cursor-pointer rounded-full border border-glass-border bg-white/35 px-5 py-2 text-sm text-text-primary shadow-sm transition hover:-translate-y-0.5';
const CARD_CLS = 'panel-soft rounded-[26px] p-5';

type ProfileFormState = {
  riskLevel: string;
  nickname: string;
  avatarUrl: string;
};

function readRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function buildProfileForm(value: unknown): ProfileFormState {
  const record = readRecord(value);
  return {
    riskLevel: String(record.riskLevel ?? '稳健'),
    nickname: String(record.nickname ?? ''),
    avatarUrl: String(record.avatarUrl ?? ''),
  };
}

function parseTabKey(value: unknown): TabKey | null {
  return value === 'account' || value === 'ai' || value === 'security' || value === 'sessions'
    ? value
    : null;
}

export default function SettingsPage() {
  const router = useRouter();
  const searchParams = useStableSearchParams();
  const { toast } = useToast();
  const setUser = useAuthStore((s) => s.setUser);
  const tab = parseTabKey(searchParams.get('tab')) ?? 'account';
  const [profileForm, setProfileForm] = useState<ProfileFormState>(() => buildProfileForm(null));
  const [profileReady, setProfileReady] = useState(false);
  const [profileDirty, setProfileDirty] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordFormError, setPasswordFormError] = useState<string | null>(null);
  const [reportText, setReportText] = useState('');

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile', { critical: true });
  const logsQ = useApiQuery<Record<string, unknown>>(tab === 'security' ? '/audit/my-logs?limit=30' : null, { critical: true });
  const sessionsQ = useApiQuery<Record<string, unknown>>(tab === 'sessions' ? '/auth/sessions' : null, { critical: true });
  const profileApi = useApiMutation<Record<string, unknown>>({ successToast: '个人资料已保存', critical: true });
  const passwordApi = useApiMutation<Record<string, unknown>>({ successToast: false, critical: true });
  const revokeApi = useApiMutation<Record<string, unknown>>({ successToast: '会话已吊销', critical: true });
  const exportApi = useApiMutation<Record<string, unknown>>({ successToast: false, critical: true });
  const reportApi = useApiMutation<Record<string, unknown>>({ successToast: false, critical: true });

  const setTabAndUrl = useCallback((nextTab: TabKey) => {
    const params = new URLSearchParams(searchParams.toString());
    if (nextTab === 'account') {
      params.delete('tab');
    } else {
      params.set('tab', nextTab);
    }

    const nextQuery = params.toString();
    const currentQuery = searchParams.toString();
    if (nextQuery === currentQuery) return;
    router.replace(nextQuery ? `/settings?${nextQuery}` : '/settings', { scroll: false });
  }, [router, searchParams]);

  useEffect(() => {
    if (profileDirty) return;
    if (profileQ.data == null && profileQ.error == null && profileQ.isPending) return;
    const timer = window.setTimeout(() => {
      setProfileForm(buildProfileForm(profileQ.data));
      setProfileReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [profileDirty, profileQ.data, profileQ.error, profileQ.isPending]);

  const riskLevelValue = profileForm.riskLevel;
  const nicknameValue = profileForm.nickname;
  const avatarUrlValue = profileForm.avatarUrl;
  const profileRecord = readRecord(profileQ.data);
  const displayName = nicknameValue || String(profileRecord.username ?? '-');
  const displayRole = String(profileRecord.role ?? 'user');
  const displayInitial = (displayName || '?').slice(0, 1).toUpperCase();
  const reportReady = reportText.trim().length > 0;

  const logRows = useMemo(() => {
    const root = readRecord(logsQ.data);
    const data = readRecord(root.data);
    const items = Array.isArray(data.items) ? data.items : Array.isArray(root.items) ? root.items : [];
    return items
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
      .map((item) => ({
        time: new Date(String(item.ts ?? '')).toLocaleString('zh-CN'),
        action: `${String(item.method ?? '-')} ${String(item.path ?? '-')}`,
        status: Number(item.status ?? 0),
        duration: `${Number(item.duration_ms ?? 0)}ms`,
      }));
  }, [logsQ.data]);

  const sessionRows = useMemo(() => {
    const root = readRecord(sessionsQ.data);
    const data = readRecord(root.data);
    const items = Array.isArray(data.items) ? data.items : Array.isArray(root.items) ? root.items : [];
    return items.filter(
      (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
    );
  }, [sessionsQ.data]);

  const activeSessionCount = sessionRows.length;

  async function saveProfile() {
    const payload = {
      riskLevel: profileForm.riskLevel || '稳健',
      nickname: profileForm.nickname,
      avatarUrl: profileForm.avatarUrl,
    };
    const data = await profileApi.triggerAsync(
      '/auth/profile',
      { method: 'POST' },
      payload,
    );
    const profile = readRecord(data);
    const existing = readRecord(profileQ.data);
    const roleValue = profile.role ?? existing.role;
    setProfileForm(buildProfileForm({ ...existing, ...profile, ...payload }));
    setProfileDirty(false);
    setUser({
      id: String(profile.id ?? existing.id ?? ''),
      username: String(profile.username ?? existing.username ?? ''),
      role: roleValue === 'admin' ? 'admin' : 'user',
      riskLevel: String(profile.riskLevel ?? existing.riskLevel ?? payload.riskLevel),
      nickname: String(profile.nickname ?? existing.nickname ?? payload.nickname),
      avatarUrl: String(profile.avatarUrl ?? existing.avatarUrl ?? payload.avatarUrl),
      preferences: readRecord(profile.preferences ?? existing.preferences),
    });
    profileQ.refetch();
  }

  async function changePassword() {
    setPasswordFormError(null);
    if (!oldPassword || !newPassword || !confirmPassword) {
      const msg = '请填写完整密码信息';
      setPasswordFormError(msg); toast(msg, 'warning'); return;
    }
    if (newPassword.length < 6) {
      const msg = '新密码至少需要 6 位';
      setPasswordFormError(msg); toast(msg, 'warning'); return;
    }
    if (newPassword !== confirmPassword) {
      const msg = '两次新密码不一致';
      setPasswordFormError(msg); toast(msg, 'warning'); return;
    }
    await passwordApi.triggerAsync('/auth/change-password', { method: 'POST' }, { oldPassword, newPassword });
    clearLoggedIn(); setUser(null);
    toast('密码修改成功，请重新登录', 'success');
    window.location.href = '/login';
  }

  function handlePasswordSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void changePassword();
  }

  async function exportMyData() {
    const data = await exportApi.triggerAsync('/export/my-data');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'aiask-my-data.json'; link.click();
    URL.revokeObjectURL(url);
    toast('已导出个人数据', 'success');
  }

  async function generateReport() {
    const data = await reportApi.triggerAsync('/export/report?period=monthly');
    setReportText(String(readRecord(data).report ?? ''));
    toast('投资报告已生成', 'success');
  }

  async function revokeSession(sessionId: string) {
    await revokeApi.triggerAsync('/auth/sessions/revoke', { method: 'POST' }, { sessionId });
    await sessionsQ.refetch();
  }

  if (tab === 'account' && profileQ.isPending && !profileQ.data) {
    return (
      <PageContainer>
        <LoadingState text="正在加载账户设置..." />
      </PageContainer>
    );
  }

  if (tab === 'account' && profileQ.error && !profileQ.data) {
    return (
      <PageContainer>
        <UnavailableState
          text="账户设置主链路暂不可用"
          hint={profileQ.error}
          onRetry={() => {
            void profileQ.refetch();
          }}
        />
      </PageContainer>
    );
  }

  if (tab === 'security' && logsQ.isPending && !logsQ.data) {
    return (
      <PageContainer>
        <LoadingState text="正在加载安全日志..." />
      </PageContainer>
    );
  }

  if (tab === 'security' && logsQ.error && !logsQ.data) {
    return (
      <PageContainer>
        <UnavailableState
          text="安全日志暂不可用"
          hint={logsQ.error}
          onRetry={() => {
            void logsQ.refetch();
          }}
        />
      </PageContainer>
    );
  }

  if (tab === 'sessions' && sessionsQ.isPending && !sessionsQ.data) {
    return (
      <PageContainer>
        <LoadingState text="正在加载活跃会话..." />
      </PageContainer>
    );
  }

  if (tab === 'sessions' && sessionsQ.error && !sessionsQ.data) {
    return (
      <PageContainer>
        <UnavailableState
          text="活跃会话暂不可用"
          hint={sessionsQ.error}
          onRetry={() => {
            void sessionsQ.refetch();
          }}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      {/* ---- 精简 Hero ---- */}
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            {avatarUrlValue ? (
              <img src={avatarUrlValue} alt="头像" className="h-14 w-14 shrink-0 rounded-full border border-glass-border object-cover" />
            ) : (
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-semibold text-white">
                {displayInitial}
              </div>
            )}
            <div>
              <h1 className="m-0 text-xl font-semibold text-text-primary sm:text-2xl">设置中心</h1>
              <p className="m-0 mt-1 text-sm text-text-secondary">
                {displayName} · {displayRole} · 风险偏好 {riskLevelValue}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={activeSessionCount > 1 ? 'warning' : 'success'}>
              {activeSessionCount > 0 ? `${activeSessionCount} 个活跃会话` : '无活跃会话'}
            </Badge>
            <Badge variant={reportReady ? 'success' : 'neutral'}>
              {reportReady ? '报告已就绪' : '待生成报告'}
            </Badge>
          </div>
        </div>
      </section>

      <div>
        <TabBar tabs={TABS} active={tab} onChange={setTabAndUrl} />
      </div>


      {/* ======== 账户信息 Tab ======== */}
      {tab === 'account' ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div className="space-y-4">
            {/* 个人资料 */}
            <SectionCard>
              <div className={CARD_CLS}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="m-0 text-base font-semibold text-text-primary">个人资料</h3>
                  <Badge variant="neutral">账户资料</Badge>
                </div>
                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  <label htmlFor="settings-nickname" className="block">
                    <span className={LABEL_CLS}>昵称</span>
                    <input
                      id="settings-nickname"
                      value={nicknameValue}
                      onChange={(e) => {
                        setProfileDirty(true);
                        setProfileForm((current) => ({ ...current, nickname: e.target.value }));
                      }}
                      disabled={!profileReady}
                      className={INPUT_CLS}
                      placeholder="输入昵称"
                    />
                  </label>
                  <label htmlFor="settings-risk-level" className="block">
                    <span className={LABEL_CLS}>风险偏好</span>
                    <select
                      id="settings-risk-level"
                      value={riskLevelValue}
                      onChange={(e) => {
                        setProfileDirty(true);
                        setProfileForm((current) => ({ ...current, riskLevel: e.target.value }));
                      }}
                      disabled={!profileReady}
                      className={INPUT_CLS}
                    >
                      {RISK_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </label>
                  <label htmlFor="settings-avatar-url" className="block sm:col-span-2">
                    <span className={LABEL_CLS}>头像 URL</span>
                    <input
                      id="settings-avatar-url"
                      value={avatarUrlValue}
                      onChange={(e) => {
                        setProfileDirty(true);
                        setProfileForm((current) => ({ ...current, avatarUrl: e.target.value }));
                      }}
                      disabled={!profileReady}
                      className={INPUT_CLS}
                      placeholder="https://..."
                    />
                  </label>
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  <button type="button" onClick={() => void saveProfile()} disabled={!profileReady || profileApi.isPending} className={BTN_PRIMARY}>
                    {profileApi.isPending ? '保存中...' : '保存资料'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setProfileForm(buildProfileForm(profileRecord));
                      setProfileDirty(false);
                    }}
                    disabled={!profileReady}
                    className={BTN_GHOST}
                  >
                    重置
                  </button>
                </div>
              </div>
            </SectionCard>

            {/* 修改密码 */}
            <SectionCard>
              <div className={CARD_CLS}>
                <h3 className="m-0 text-base font-semibold text-text-primary">修改密码</h3>
                <p className="m-0 mt-1 text-xs text-text-secondary">修改成功后需要重新登录。</p>
                <form onSubmit={handlePasswordSubmit} className="mt-4 space-y-4">
                  <label htmlFor="settings-old-password" className="block">
                    <span className={LABEL_CLS}>旧密码</span>
                    <input id="settings-old-password" type="password" autoComplete="current-password" value={oldPassword} onChange={(e) => { setOldPassword(e.target.value); setPasswordFormError(null); }} className={INPUT_CLS} placeholder="输入当前密码" />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label htmlFor="settings-new-password" className="block">
                      <span className={LABEL_CLS}>新密码</span>
                      <input id="settings-new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(e) => { setNewPassword(e.target.value); setPasswordFormError(null); }} className={INPUT_CLS} placeholder="至少 6 位" />
                    </label>
                    <label htmlFor="settings-confirm-password" className="block">
                      <span className={LABEL_CLS}>确认新密码</span>
                      <input id="settings-confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => { setConfirmPassword(e.target.value); setPasswordFormError(null); }} className={INPUT_CLS} placeholder="再次输入新密码" />
                    </label>
                  </div>
                  {passwordFormError ? <p className="m-0 text-xs text-danger" role="alert">{passwordFormError}</p> : null}
                  <button type="submit" disabled={passwordApi.isPending} className={`${BTN_GHOST} border-primary/40 text-primary`}>
                    {passwordApi.isPending ? '提交中...' : '修改密码'}
                  </button>
                </form>
              </div>
            </SectionCard>
          </div>

          {/* 右侧信息栏 */}
          <div className="space-y-4">
            <SectionCard>
              <div className={CARD_CLS}>
                <div className="text-xs font-semibold uppercase tracking-widest text-text-muted">数据导出</div>
                <p className="m-0 mt-2 text-xs leading-5 text-text-secondary">用于个人归档、合规留存和月度复盘输出。</p>
                <div className="mt-4 flex flex-col gap-2">
                  <button type="button" onClick={() => void exportMyData()} disabled={exportApi.isPending} className={BTN_GHOST}>
                    {exportApi.isPending ? '导出中...' : '导出我的数据'}
                  </button>
                  <button type="button" onClick={() => void generateReport()} disabled={reportApi.isPending} className={BTN_GHOST}>
                    {reportApi.isPending ? '生成中...' : '生成投资报告'}
                  </button>
                </div>
                {reportText ? (
                  <pre className="mt-4 max-h-56 overflow-auto rounded-xl border border-glass-border bg-white/42 p-3 text-xs whitespace-pre-wrap text-text-secondary">
                    {reportText}
                  </pre>
                ) : null}
              </div>
            </SectionCard>

            <SectionCard>
              <div className={CARD_CLS}>
                <div className="text-xs font-semibold uppercase tracking-widest text-text-muted">快捷入口</div>
                <div className="mt-3 flex flex-col gap-2">
                  <Link href="/settings/audit-log" className={`${BTN_GHOST} block text-center no-underline`}>查看完整审计日志</Link>
                </div>
              </div>
            </SectionCard>
          </div>
        </div>
      ) : null}

      {/* ======== AI 模型 Tab ======== */}
      {tab === 'ai' ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <SectionCard>
            <div className={CARD_CLS}>
              <AiModelConfig />
            </div>
          </SectionCard>
          <SectionCard>
            <div className={CARD_CLS}>
              <div className="text-xs font-semibold uppercase tracking-widest text-text-muted">说明</div>
              <ul className="mb-0 mt-3 space-y-2 pl-4 text-xs leading-6 text-text-secondary">
                <li>填写 Base URL 和 API Key 后系统会自动检测可用模型列表。</li>
                <li>支持所有 OpenAI 兼容接口（DeepSeek、Qwen、GLM 等）。</li>
                <li>配置会保存到你的账户，AI 中心和 Copilot 会使用此配置。</li>
                <li>如果自动检测失败，可以手动输入模型名称。</li>
              </ul>
            </div>
          </SectionCard>
        </div>
      ) : null}

      {/* ======== 安全日志 Tab ======== */}
      {tab === 'security' ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[clamp(240px,22vw,320px)_minmax(0,1fr)]">
          <SectionCard>
            <div className={CARD_CLS}>
              <div className="text-xs font-semibold uppercase tracking-widest text-text-muted">安全巡检</div>
              <div className="mt-4 space-y-3 text-xs leading-6 text-text-secondary">
                <div>日志条数：<span className="font-medium text-text-primary">{logRows.length}</span></div>
                <div>状态：<span className="font-medium text-text-primary">{logsQ.isFetching ? '同步中...' : logRows.length > 0 ? `最近 ${logRows.length} 条` : '暂无记录'}</span></div>
                <div>建议：<span className="font-medium text-text-primary">关注异常状态码和超长耗时</span></div>
              </div>
              <div className="mt-4">
                <Link href="/settings/audit-log" className={`${BTN_GHOST} block text-center no-underline`}>查看全量日志</Link>
              </div>
            </div>
          </SectionCard>

          <SectionCard>
            <div className={CARD_CLS}>
              <DataTable
                rows={logRows}
                columns={[
                  { key: 'time', label: '时间' },
                  { key: 'action', label: '操作' },
                  { key: 'status', label: '状态' },
                  { key: 'duration', label: '耗时' },
                ]}
                pageSize={10}
                emptyText={logsQ.isFetching ? '加载安全日志中...' : '暂无安全日志'}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-text-primary">{String(row.action ?? '-')}</div>
                      <div className="text-xs text-text-secondary">{String(row.status ?? '-')}</div>
                    </div>
                    <div className="text-xs text-text-secondary">时间：{String(row.time ?? '-')}</div>
                    <div className="text-xs text-text-secondary">耗时：{String(row.duration ?? '-')}</div>
                  </div>
                )}
              />
            </div>
          </SectionCard>
        </div>
      ) : null}

      {/* ======== 活跃会话 Tab ======== */}
      {tab === 'sessions' ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[clamp(240px,22vw,320px)_minmax(0,1fr)]">
          <SectionCard>
            <div className={CARD_CLS}>
              <div className="text-xs font-semibold uppercase tracking-widest text-text-muted">会话管理</div>
              <div className="mt-4 space-y-3 text-xs leading-6 text-text-secondary">
                <div>活跃总数：<span className="font-medium text-text-primary">{activeSessionCount}</span></div>
                <div>当前设备：<span className="font-medium text-text-primary">{sessionRows.some((row) => Boolean(row.current)) ? '已识别' : '待识别'}</span></div>
                <div>建议：<span className="font-medium text-text-primary">改密后同步清理历史会话</span></div>
              </div>
            </div>
          </SectionCard>

          <SectionCard>
            <div className={CARD_CLS}>
              <DataTable
                rows={sessionRows.map((row) => ({
                  ...row,
                  createdAt: new Date(String(row.createdAt ?? '')).toLocaleString('zh-CN'),
                  accessExpiresAt: new Date(String(row.accessExpiresAt ?? '')).toLocaleString('zh-CN'),
                  refreshExpiresAt: new Date(String(row.refreshExpiresAt ?? '')).toLocaleString('zh-CN'),
                }))}
                columns={[
                  { key: 'createdAt', label: '创建时间' },
                  { key: 'accessExpiresAt', label: '访问过期' },
                  { key: 'refreshExpiresAt', label: '刷新过期' },
                  { key: 'status', label: '状态' },
                  {
                    key: 'action', label: '操作', sortable: false,
                    render: (_v, row) => row.current
                      ? '当前会话'
                      : <button className="text-xs text-danger cursor-pointer" onClick={(e) => { e.stopPropagation(); void revokeSession(String(row.id ?? '')); }}>踢出</button>,
                  },
                ]}
                pageSize={10}
                emptyText={sessionsQ.isFetching ? '加载会话中...' : '暂无活跃会话'}
                mobileCardRender={(row) => (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-text-primary">{row.current ? '当前会话' : '异地会话'}</div>
                      <div className="text-xs text-text-secondary">{String(row.status ?? '-')}</div>
                    </div>
                    <div className="text-xs text-text-secondary">创建：{String(row.createdAt ?? '-')}</div>
                    <div className="text-xs text-text-secondary">访问过期：{String(row.accessExpiresAt ?? '-')}</div>
                    {row.current
                      ? <div className="text-xs text-success">当前设备</div>
                      : <button type="button" className="text-xs text-danger cursor-pointer" onClick={() => void revokeSession(String(row.id ?? ''))}>踢出该会话</button>
                    }
                  </div>
                )}
              />
            </div>
          </SectionCard>
        </div>
      ) : null}
    </PageContainer>
  );
}

/* ======== AI 模型配置内联组件 ======== */
function AiModelConfig() {
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [hasStoredApiKey, setHasStoredApiKey] = useState(false);
  const [apiKeyMasked, setApiKeyMasked] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  const [detectedModels, setDetectedModels] = useState<string[]>([]);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState('');
  const probeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { toast } = useToast();
  const setConfigLoaded = useChatStore((s) => s.setConfigLoaded);

  const doProbe = useCallback((url: string, key: string, preferredModel?: string) => {
    if (!url.trim() || (!key.trim() && !hasStoredApiKey)) { setDetectedModels([]); setProbeError(''); return; }
    setProbing(true); setProbeError('');
    probeModels(url, key, preferredModel || model)
      .then((r) => {
        if (r.normalizedBaseUrl) {
          setBaseUrl(r.normalizedBaseUrl);
        }
        if (r.success && r.models.length > 0) { setDetectedModels(r.models); setProbeError(''); }
        else { setDetectedModels([]); setProbeError(r.error || '未检测到可用模型'); }
      })
      .catch(() => { setDetectedModels([]); setProbeError('检测请求失败'); })
      .finally(() => setProbing(false));
  }, [hasStoredApiKey, model]);

  useEffect(() => {
    getLlmConfig().then((c) => {
      if (c) {
        setBaseUrl(c.baseUrl);
        setModel(c.model);
        setHasStoredApiKey(c.hasStoredApiKey);
        setApiKeyMasked(c.apiKeyMasked);
      }
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, []);

  useEffect(() => {
    if (baseUrl && hasStoredApiKey) {
      doProbe(baseUrl, '', model);
    }
  }, [baseUrl, doProbe, hasStoredApiKey, model]);

  function scheduleProbe(url: string, key: string) {
    if (probeTimerRef.current) clearTimeout(probeTimerRef.current);
    probeTimerRef.current = setTimeout(() => doProbe(url, key, model), 600);
  }

  async function onSave() {
    if ((!apiKey.trim() && !hasStoredApiKey) || !baseUrl.trim() || !model.trim()) { setError('请填写完整配置'); return; }
    setSaving(true); setError('');
    try {
      const saved = await saveLlmConfig({ apiKey: apiKey.trim() || undefined, baseUrl: baseUrl.trim(), model: model.trim() });
      if (saved.normalizedBaseUrl) {
        setBaseUrl(saved.normalizedBaseUrl);
      }
      const confirmed = await getLlmConfig();
      if (!confirmed) {
        throw new Error('配置保存后未能重新读取，请稍后重试');
      }
      setBaseUrl(confirmed.baseUrl);
      setModel(confirmed.model);
      setHasStoredApiKey(confirmed.hasStoredApiKey);
      setApiKeyMasked(confirmed.apiKeyMasked);
      setApiKey('');
      setConfigLoaded(true, true);
      toast('AI 模型配置已保存', 'success');
    } catch (err) { setError(err instanceof Error ? err.message : '保存失败'); }
    finally { setSaving(false); }
  }

  if (!loaded) return <div className="py-8 text-center text-sm text-text-muted">加载配置中...</div>;

  const hasModels = detectedModels.length > 0;

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h3 className="m-0 text-base font-semibold text-text-primary">AI 模型配置</h3>
        <Badge variant={model ? 'success' : 'neutral'}>{model || '未配置'}</Badge>
      </div>
      <p className="m-0 mt-1 text-xs text-text-secondary">填写 Base URL 和 API Key 后自动检测可用模型。</p>

      <div className="mt-5 space-y-4">
        <label className="block">
          <span className={LABEL_CLS}>Base URL</span>
          <input
            value={baseUrl}
            onChange={(e) => { setBaseUrl(e.target.value); setError(''); scheduleProbe(e.target.value, apiKey); }}
            placeholder="https://api.openai.com/v1"
            className={INPUT_CLS}
          />
        </label>

        <label className="block">
          <span className={LABEL_CLS}>API Key</span>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => { setApiKey(e.target.value); setError(''); scheduleProbe(baseUrl, e.target.value); }}
            placeholder={hasStoredApiKey ? `${apiKeyMasked || '已保存 API Key'}（留空表示不修改）` : 'sk-...'}
            className={INPUT_CLS}
          />
          {hasStoredApiKey ? <div className="mt-1 text-xs text-text-muted">当前已保存 Key，留空即可保留原值。</div> : null}
        </label>

        <div>
          <span className={LABEL_CLS}>模型</span>
          {probing ? (
            <div className="mt-1 rounded-xl border border-glass-border bg-white/40 px-3 py-2.5 text-xs text-text-muted">正在检测可用模型...</div>
          ) : hasModels ? (
            <select value={model} onChange={(e) => setModel(e.target.value)} className={INPUT_CLS}>
              <option value="">选择模型</option>
              {detectedModels.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          ) : (
            <>
              <input value={model} onChange={(e) => { setModel(e.target.value); setError(''); }} placeholder="gpt-4o" className={INPUT_CLS} />
              {probeError ? (
                <div className="mt-1 text-xs text-text-muted">{probeError}，可手动输入模型名称</div>
              ) : baseUrl.trim() && (apiKey.trim() || hasStoredApiKey) ? (
                <button type="button" onClick={() => doProbe(baseUrl, apiKey, model)} className="mt-1 cursor-pointer border-none bg-transparent p-0 text-xs text-primary hover:underline">
                  点击重新检测
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>

      {error ? <p className="mt-3 text-xs text-danger" role="alert">{error}</p> : null}

      <div className="mt-5 flex gap-2">
        <button type="button" onClick={() => void onSave()} disabled={saving} className={BTN_PRIMARY}>
          {saving ? '保存中...' : '保存配置'}
        </button>
      </div>
    </div>
  );
}
