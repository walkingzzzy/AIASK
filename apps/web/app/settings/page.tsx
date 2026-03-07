'use client';

import { useEffect, useMemo, useState } from 'react';
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
  const [riskLevel, setRiskLevel] = useState('稳健');
  const [nickname, setNickname] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [reportText, setReportText] = useState('');

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const logsQ = useApiQuery<Record<string, unknown>>('/audit/my-logs?limit=30');
  const sessionsQ = useApiQuery<Record<string, unknown>>('/auth/sessions');
  const profileApi = useApiMutation<Record<string, unknown>>({ successToast: '个人资料已保存' });
  const passwordApi = useApiMutation<Record<string, unknown>>({ successToast: false });
  const revokeApi = useApiMutation<Record<string, unknown>>({ successToast: '会话已吊销' });
  const exportApi = useApiMutation<Record<string, unknown>>({ successToast: false });
  const reportApi = useApiMutation<Record<string, unknown>>({ successToast: false });

  useEffect(() => {
    const data = profileQ.data ?? {};
    setRiskLevel(String(data.riskLevel ?? '稳健'));
    setNickname(String(data.nickname ?? ''));
    setAvatarUrl(String(data.avatarUrl ?? ''));
  }, [profileQ.data]);

  const logRows = useMemo(() => (((logsQ.data?.data as any)?.items ?? (logsQ.data as any)?.items ?? []) as Record<string, unknown>[]).map((item) => ({
    time: new Date(String(item.ts ?? '')).toLocaleString('zh-CN'),
    action: `${String(item.method ?? '-')} ${String(item.path ?? '-')}`,
    status: Number(item.status ?? 0),
    duration: `${Number(item.duration_ms ?? 0)}ms`,
  })), [logsQ.data]);
  const sessionRows = useMemo(() => (((sessionsQ.data?.data as any)?.items ?? (sessionsQ.data as any)?.items ?? []) as Record<string, unknown>[]), [sessionsQ.data]);

  async function saveProfile() {
    const data = await profileApi.triggerAsync('/auth/profile', { method: 'POST' }, { riskLevel, nickname, avatarUrl });
    setUser(data as any);
    profileQ.refetch();
  }

  async function changePassword() {
    if (!oldPassword || !newPassword) return toast('请填写完整密码信息', 'warning');
    if (newPassword !== confirmPassword) return toast('两次新密码不一致', 'warning');
    await passwordApi.triggerAsync('/auth/change-password', { method: 'POST' }, { oldPassword, newPassword });
    clearLoggedIn();
    setUser(null);
    toast('密码修改成功，请重新登录', 'success');
    window.location.href = '/login';
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

  return (
    <PageContainer>
      <div className="mb-4">
        <h1 className="text-xl font-semibold m-0">设置中心</h1>
        <p className="text-sm text-text-secondary mt-1">管理个人资料、密码、安全日志和活跃会话。</p>
      </div>
      <TabBar tabs={TABS} active={tab} onChange={setTab} />

      {tab === 'account' ? <SectionCard className="p-4"><div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-3">
          <div><div className="text-xs text-text-secondary mb-1">昵称</div><input value={nickname} onChange={(e) => setNickname(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="输入昵称" /></div>
          <div><div className="text-xs text-text-secondary mb-1">头像 URL</div><input value={avatarUrl} onChange={(e) => setAvatarUrl(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="https://..." /></div>
          <div><div className="text-xs text-text-secondary mb-1">风险偏好</div><select value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm">{RISK_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
          <button onClick={() => void saveProfile()} disabled={profileApi.isPending} className="px-4 py-2 rounded bg-primary text-white text-sm cursor-pointer disabled:opacity-50">{profileApi.isPending ? '保存中...' : '保存资料'}</button>
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-3">{avatarUrl ? <img src={avatarUrl} alt="头像预览" className="w-12 h-12 rounded-full object-cover border border-glass-border" /> : <div className="w-12 h-12 rounded-full bg-primary text-white flex items-center justify-center">{(nickname || String(profileQ.data?.username ?? '?')).slice(0, 1)}</div>}<div><div className="text-sm font-medium">{nickname || String(profileQ.data?.username ?? '-')}</div><div className="text-xs text-text-secondary">{String(profileQ.data?.role ?? 'user')}</div></div></div>
          <div className="pt-2 border-t border-glass-border space-y-2">
            <div className="text-sm font-medium">修改密码</div>
            <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="旧密码" />
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="新密码（至少 6 位）" />
            <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="w-full border border-border rounded px-3 py-2 bg-surface text-sm" placeholder="确认新密码" />
            <button onClick={() => void changePassword()} disabled={passwordApi.isPending} className="px-4 py-2 rounded border border-primary/40 text-primary text-sm cursor-pointer disabled:opacity-50">{passwordApi.isPending ? '提交中...' : '修改密码'}</button>
          </div>
          <div className="pt-2 border-t border-glass-border space-y-2">
            <div className="text-sm font-medium">数据导出</div>
            <div className="flex items-center gap-2 flex-wrap">
              <button onClick={() => void exportMyData()} disabled={exportApi.isPending} className="px-4 py-2 rounded border border-glass-border text-sm cursor-pointer disabled:opacity-50">导出我的数据</button>
              <button onClick={() => void generateReport()} disabled={reportApi.isPending} className="px-4 py-2 rounded border border-glass-border text-sm cursor-pointer disabled:opacity-50">生成投资报告</button>
            </div>
            {reportText ? <pre className="text-xs whitespace-pre-wrap bg-surface rounded p-3 border border-border max-h-64 overflow-auto">{reportText}</pre> : null}
          </div>
        </div>
      </div></SectionCard> : null}

      {tab === 'security' ? <SectionCard className="p-4"><DataTable rows={logRows} columns={[{ key: 'time', label: '时间' }, { key: 'action', label: '操作' }, { key: 'status', label: '状态' }, { key: 'duration', label: '耗时' }]} pageSize={10} /></SectionCard> : null}

      {tab === 'sessions' ? <SectionCard className="p-4"><DataTable rows={sessionRows.map((row) => ({ ...row, createdAt: new Date(String(row.createdAt ?? '')).toLocaleString('zh-CN'), accessExpiresAt: new Date(String(row.accessExpiresAt ?? '')).toLocaleString('zh-CN'), refreshExpiresAt: new Date(String(row.refreshExpiresAt ?? '')).toLocaleString('zh-CN') }))} columns={[{ key: 'createdAt', label: '创建时间' }, { key: 'accessExpiresAt', label: '访问过期' }, { key: 'refreshExpiresAt', label: '刷新过期' }, { key: 'status', label: '状态' }, { key: 'action', label: '操作', sortable: false, render: (_v, row) => row.current ? '当前会话' : <button className="text-xs text-danger cursor-pointer" onClick={(e) => { e.stopPropagation(); void revokeApi.triggerAsync('/auth/sessions/revoke', { method: 'POST' }, { sessionId: row.id }); sessionsQ.refetch(); }}>踢出</button> }]} pageSize={10} /></SectionCard> : null}
    </PageContainer>
  );
}

