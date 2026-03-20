'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useToast } from '@/components/ui/toast';
import { useAuthStore } from '@/store/auth-store';
import { clearLoggedIn } from '@/lib/auth';

type TabKey = 'account' | 'security' | 'sessions';
const TABS = [{ key: 'account', label: '账户信息' }, { key: 'security', label: '安全日志' }, { key: 'sessions', label: '活跃会话' }] as const;
const RISK_OPTIONS = ['保守', '稳健', '激进'] as const;

export default function SettingsPage() {
  const { toast } = useToast();
  const setUser = useAuthStore((s) => s.setUser);
  const [tab, setTab] = useState<TabKey>('account');
  const [riskLevel, setRiskLevel] = useState<string | null>(null);
  const [nickname, setNickname] = useState<string | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordFormError, setPasswordFormError] = useState<string | null>(null);
  const [reportText, setReportText] = useState('');

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const logsQ = useApiQuery<Record<string, unknown>>(tab === 'security' ? '/audit/my-logs?limit=30' : null);
  const sessionsQ = useApiQuery<Record<string, unknown>>(tab === 'sessions' ? '/auth/sessions' : null);
  const profileApi = useApiMutation<Record<string, unknown>>({ successToast: '个人资料已保存' });
  const passwordApi = useApiMutation<Record<string, unknown>>({ successToast: false });
  const revokeApi = useApiMutation<Record<string, unknown>>({ successToast: '会话已吊销' });
  const exportApi = useApiMutation<Record<string, unknown>>({ successToast: false });
  const reportApi = useApiMutation<Record<string, unknown>>({ successToast: false });
  const riskLevelValue = riskLevel ?? String(profileQ.data?.riskLevel ?? '稳健');
  const nicknameValue = nickname ?? String(profileQ.data?.nickname ?? '');
  const avatarUrlValue = avatarUrl ?? String(profileQ.data?.avatarUrl ?? '');

  const logRows = useMemo(() => (((logsQ.data?.data as any)?.items ?? (logsQ.data as any)?.items ?? []) as Record<string, unknown>[]).map((item) => ({
    time: new Date(String(item.ts ?? '')).toLocaleString('zh-CN'),
    action: `${String(item.method ?? '-')} ${String(item.path ?? '-')}`,
    status: Number(item.status ?? 0),
    duration: `${Number(item.duration_ms ?? 0)}ms`,
  })), [logsQ.data]);
  const sessionRows = useMemo(() => (((sessionsQ.data?.data as any)?.items ?? (sessionsQ.data as any)?.items ?? []) as Record<string, unknown>[]), [sessionsQ.data]);
  const activeSessionCount = sessionRows.length;

  async function saveProfile() {
    const data = await profileApi.triggerAsync('/auth/profile', { method: 'POST' }, { riskLevel: riskLevelValue, nickname: nicknameValue, avatarUrl: avatarUrlValue });
    setUser(data as any);
    profileQ.refetch();
  }

  async function changePassword() {
    setPasswordFormError(null);
    if (!oldPassword || !newPassword || !confirmPassword) {
      const message = '请填写完整密码信息';
      setPasswordFormError(message);
      toast(message, 'warning');
      return;
    }
    if (newPassword.length < 6) {
      const message = '新密码至少需要 6 位';
      setPasswordFormError(message);
      toast(message, 'warning');
      return;
    }
    if (newPassword !== confirmPassword) {
      const message = '两次新密码不一致';
      setPasswordFormError(message);
      toast(message, 'warning');
      return;
    }
    await passwordApi.triggerAsync('/auth/change-password', { method: 'POST' }, { oldPassword, newPassword });
    clearLoggedIn();
    setUser(null);
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
    link.href = url;
    link.download = 'aiask-my-data.json';
    link.click();
    URL.revokeObjectURL(url);
    toast('已导出个人数据', 'success');
  }

  async function generateReport() {
    const data = await reportApi.triggerAsync('/export/report?period=monthly');
    setReportText(String((data as any).report ?? ''));
    toast('投资报告已生成', 'success');
  }

  async function revokeSession(sessionId: string) {
    await revokeApi.triggerAsync('/auth/sessions/revoke', { method: 'POST' }, { sessionId });
    await sessionsQ.refetch();
  }

  return (
    <PageContainer>
      <div className="mb-4">
        <h1 className="text-xl font-semibold m-0">设置中心</h1>
        <p className="text-sm text-text-secondary mt-1">管理个人资料、密码、安全日志和活跃会话。</p>
      </div>
      <SectionCard className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-border bg-surface p-3">
            <div className="text-xs text-text-secondary">账户资料</div>
            <div className="mt-1 text-sm font-medium">昵称、头像与风险偏好统一维护</div>
          </div>
          <div className="rounded-xl border border-border bg-surface p-3">
            <div className="text-xs text-text-secondary">安全操作</div>
            <div className="mt-1 text-sm font-medium">密码修改、审计日志与会话吊销分层清晰</div>
          </div>
          <div className="rounded-xl border border-border bg-surface p-3">
            <div className="text-xs text-text-secondary">当前会话</div>
            <div className="mt-1 text-sm font-medium">共 {activeSessionCount} 个活跃会话，可按需逐个踢出</div>
          </div>
        </div>
      </SectionCard>
      <TabBar tabs={TABS} active={tab} onChange={setTab} />

      {tab === 'account' ? <SectionCard className="p-4"><div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-3">
          <label htmlFor="settings-nickname" className="block">
            <span className="text-xs text-text-secondary mb-1 block">昵称</span>
            <input id="settings-nickname" value={nicknameValue} onChange={(e) => setNickname(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="输入昵称" />
          </label>
          <label htmlFor="settings-avatar-url" className="block">
            <span className="text-xs text-text-secondary mb-1 block">头像 URL</span>
            <input id="settings-avatar-url" value={avatarUrlValue} onChange={(e) => setAvatarUrl(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="https://..." />
          </label>
          <label htmlFor="settings-risk-level" className="block">
            <span className="text-xs text-text-secondary mb-1 block">风险偏好</span>
            <select id="settings-risk-level" value={riskLevelValue} onChange={(e) => setRiskLevel(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm">{RISK_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}</select>
          </label>
          <button type="button" onClick={() => void saveProfile()} disabled={profileApi.isPending} className="px-4 py-2 rounded bg-primary text-white text-sm cursor-pointer disabled:opacity-50">{profileApi.isPending ? '保存中...' : '保存资料'}</button>
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-3">{avatarUrlValue ? <img src={avatarUrlValue} alt="头像预览" className="w-12 h-12 rounded-full object-cover border border-glass-border" /> : <div className="w-12 h-12 rounded-full bg-primary text-white flex items-center justify-center">{(nicknameValue || String(profileQ.data?.username ?? '?')).slice(0, 1)}</div>}<div><div className="text-sm font-medium">{nicknameValue || String(profileQ.data?.username ?? '-')}</div><div className="text-xs text-text-secondary">{String(profileQ.data?.role ?? 'user')}</div></div></div>
          <form onSubmit={handlePasswordSubmit} className="pt-2 border-t border-glass-border space-y-2">
            <div className="text-sm font-medium">修改密码</div>
            <p className="m-0 text-xs text-text-secondary">此区域使用独立表单提交。修改成功后会要求重新登录，避免旧会话继续生效。</p>
            <label htmlFor="settings-old-password" className="block">
              <span className="text-xs text-text-secondary mb-1 block">旧密码</span>
              <input id="settings-old-password" type="password" autoComplete="current-password" value={oldPassword} onChange={(e) => { setOldPassword(e.target.value); setPasswordFormError(null); }} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="输入当前密码" />
            </label>
            <label htmlFor="settings-new-password" className="block">
              <span className="text-xs text-text-secondary mb-1 block">新密码</span>
              <input id="settings-new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(e) => { setNewPassword(e.target.value); setPasswordFormError(null); }} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="至少 6 位" />
            </label>
            <label htmlFor="settings-confirm-password" className="block">
              <span className="text-xs text-text-secondary mb-1 block">确认新密码</span>
              <input id="settings-confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => { setConfirmPassword(e.target.value); setPasswordFormError(null); }} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="再次输入新密码" />
            </label>
            {passwordFormError ? <p className="m-0 text-xs text-danger" role="alert">{passwordFormError}</p> : null}
            <button type="submit" disabled={passwordApi.isPending} className="px-4 py-2 rounded border border-primary/40 text-primary text-sm cursor-pointer disabled:opacity-50">{passwordApi.isPending ? '提交中...' : '修改密码'}</button>
          </form>
          <div className="pt-2 border-t border-glass-border space-y-2">
            <div className="text-sm font-medium">数据导出</div>
            <div className="flex items-center gap-2 flex-wrap">
              <button type="button" onClick={() => void exportMyData()} disabled={exportApi.isPending} className="px-4 py-2 rounded border border-glass-border text-sm cursor-pointer disabled:opacity-50">导出我的数据</button>
              <button type="button" onClick={() => void generateReport()} disabled={reportApi.isPending} className="px-4 py-2 rounded border border-glass-border text-sm cursor-pointer disabled:opacity-50">生成投资报告</button>
            </div>
            {reportText ? <pre className="text-xs whitespace-pre-wrap bg-surface rounded p-3 border border-border max-h-64 overflow-auto">{reportText}</pre> : null}
          </div>
        </div>
      </div></SectionCard> : null}

      {tab === 'security' ? <SectionCard className="p-4"><DataTable rows={logRows} columns={[{ key: 'time', label: '时间' }, { key: 'action', label: '操作' }, { key: 'status', label: '状态' }, { key: 'duration', label: '耗时' }]} pageSize={10} emptyText={logsQ.isFetching ? '加载安全日志中...' : '暂无安全日志'} mobileCardRender={(row) => (<div className="space-y-2"><div className="flex items-center justify-between gap-3"><div className="text-sm font-medium text-text-primary">{String(row.action ?? '-')}</div><div className="text-xs text-text-secondary">{String(row.status ?? '-')}</div></div><div className="text-xs text-text-secondary">时间：{String(row.time ?? '-')}</div><div className="text-xs text-text-secondary">耗时：{String(row.duration ?? '-')}</div></div>)} /></SectionCard> : null}

      {tab === 'sessions' ? <SectionCard className="p-4"><DataTable rows={sessionRows.map((row) => ({ ...row, createdAt: new Date(String(row.createdAt ?? '')).toLocaleString('zh-CN'), accessExpiresAt: new Date(String(row.accessExpiresAt ?? '')).toLocaleString('zh-CN'), refreshExpiresAt: new Date(String(row.refreshExpiresAt ?? '')).toLocaleString('zh-CN') }))} columns={[{ key: 'createdAt', label: '创建时间' }, { key: 'accessExpiresAt', label: '访问过期' }, { key: 'refreshExpiresAt', label: '刷新过期' }, { key: 'status', label: '状态' }, { key: 'action', label: '操作', sortable: false, render: (_v, row) => row.current ? '当前会话' : <button className="text-xs text-danger cursor-pointer" onClick={(e) => { e.stopPropagation(); void revokeSession(String(row.id ?? '')); }}>踢出</button> }]} pageSize={10} emptyText={sessionsQ.isFetching ? '加载会话中...' : '暂无活跃会话'} mobileCardRender={(row) => (<div className="space-y-2"><div className="flex items-center justify-between gap-3"><div className="text-sm font-medium text-text-primary">{row.current ? '当前会话' : '异地会话'}</div><div className="text-xs text-text-secondary">{String(row.status ?? '-')}</div></div><div className="text-xs text-text-secondary">创建：{String(row.createdAt ?? '-')}</div><div className="text-xs text-text-secondary">访问过期：{String(row.accessExpiresAt ?? '-')}</div><div className="text-xs text-text-secondary">刷新过期：{String(row.refreshExpiresAt ?? '-')}</div>{row.current ? <div className="text-xs text-success">当前设备会话</div> : <button type="button" className="text-xs text-danger cursor-pointer" onClick={() => void revokeSession(String(row.id ?? ''))}>踢出该会话</button>}</div>)} /></SectionCard> : null}
    </PageContainer>
  );
}
