'use client';

import { useEffect, useMemo, useState } from 'react';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useHydrated } from '@/hooks/use-hydrated';
import {
  DEFAULT_TRANSACTION_CONFIRMATIONS,
  readTransactionConfirmations,
  type TransactionConfirmKey,
  type TransactionConfirmations,
} from '@/lib/transaction-confirmations';

type TotpSetup = { secret: string; uri: string; backupCodes: string[] };
type MessageState = { type: 'success' | 'error'; text: string } | null;

const TRANSACTION_CONFIRM_ITEMS: Array<{ key: TransactionConfirmKey; label: string; description: string }> = [
  { key: 'paperOrder', label: '模拟交易下单', description: '提交模拟单前展示确认弹窗' },
  { key: 'paperCancel', label: '模拟交易撤单', description: '撤单前展示确认弹窗' },
  { key: 'alertRuleChange', label: '告警规则修改', description: '敏感规则变更前需确认' },
  { key: 'portfolioRebalance', label: '组合调仓', description: '组合调仓动作需确认后执行' },
];

export default function SecurityPage() {
  const hydrated = useHydrated();
  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const statusQ = useApiQuery<Record<string, unknown>>('/auth/2fa/status');
  const setupApi = useApiMutation<TotpSetup>({ successToast: false, errorToast: false });
  const verifyApi = useApiMutation<Record<string, unknown>>({
    successToast: false,
    errorToast: false,
    effects: ['auth.security.updated'],
  });
  const disableApi = useApiMutation<Record<string, unknown>>({
    successToast: false,
    errorToast: false,
    effects: ['auth.security.updated'],
  });
  const preferencesApi = useApiMutation<Record<string, unknown>>({
    successToast: false,
    errorToast: false,
    effects: ['auth.security.updated'],
  });

  const [totpSetup, setTotpSetup] = useState<TotpSetup | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [message, setMessage] = useState<MessageState>(null);
  const [transactionConfirmations, setTransactionConfirmations] = useState<TransactionConfirmations>(DEFAULT_TRANSACTION_CONFIRMATIONS);
  const [savingKey, setSavingKey] = useState<TransactionConfirmKey | null>(null);

  useEffect(() => {
    setTransactionConfirmations(readTransactionConfirmations(profileQ.data));
  }, [profileQ.data]);

  const totpEnabled = useMemo(() => {
    const enabledFromStatus = statusQ.data?.enabled;
    if (typeof enabledFromStatus === 'boolean') return enabledFromStatus;
    return Boolean(profileQ.data?.preferences && typeof profileQ.data.preferences === 'object'
      ? (profileQ.data.preferences as { totpEnabled?: boolean }).totpEnabled
      : false);
  }, [profileQ.data, statusQ.data]);
  const setupProgress = totpEnabled ? 3 : totpSetup ? 2 : 1;

  const loading = setupApi.isPending || verifyApi.isPending || disableApi.isPending;
  const actionDisabled = !hydrated || loading;

  async function handleSetup() {
    setMessage(null);
    try {
      const data = await setupApi.triggerAsync('/auth/2fa/setup', { method: 'POST' });
      setTotpSetup(data ?? null);
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '获取二维码失败' });
    }
  }

  async function handleVerify() {
    if (verifyCode.length !== 6) return;
    setMessage(null);
    try {
      await verifyApi.triggerAsync('/auth/2fa/verify', { method: 'POST' }, { code: verifyCode });
      setTotpSetup(null);
      setMessage({ type: 'success', text: '双因素认证已启用' });
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '验证码错误' });
    } finally {
      setVerifyCode('');
    }
  }

  async function handleDisable() {
    setMessage(null);
    try {
      await disableApi.triggerAsync('/auth/2fa/disable', { method: 'POST' });
      setTotpSetup(null);
      setMessage({ type: 'success', text: '双因素认证已关闭' });
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '关闭 2FA 失败' });
    }
  }

  async function handleToggleTransactionConfirmation(key: TransactionConfirmKey) {
    const previous = transactionConfirmations;
    const next = { ...transactionConfirmations, [key]: !transactionConfirmations[key] };
    setTransactionConfirmations(next);
    setSavingKey(key);
    setMessage(null);

    try {
      await preferencesApi.triggerAsync('/auth/profile', { method: 'POST' }, {
        preferences: {
          transactionConfirmations: next,
        },
      });
      setMessage({ type: 'success', text: `已保存“${TRANSACTION_CONFIRM_ITEMS.find((item) => item.key === key)?.label ?? '交易确认'}”设置` });
    } catch (error) {
      setTransactionConfirmations(previous);
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '保存设置失败' });
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <PageContainer>
      <div className="mb-4">
        <h1 className="text-lg font-semibold m-0">🔐 安全设置</h1>
        <p className="mt-1 mb-0 text-sm text-text-secondary">建议按“开启 2FA → 验证动态码 → 保存恢复码”的顺序完成配置。</p>
      </div>

      {message && (
        <div
          role="alert"
          data-testid="security-message"
          className={`mb-4 px-4 py-2 rounded-lg text-sm ${message.type === 'success' ? 'bg-success/15 text-success border border-success/30' : 'bg-danger/15 text-danger border border-danger/30'}`}
        >
          {message.text}
        </div>
      )}

      <SectionCard className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="mt-0 text-sm font-semibold">双因素认证 (2FA)</h3>
            <p className="text-xs text-text-secondary mt-1">使用 Google Authenticator 或兼容应用进行二次验证</p>
          </div>
          <Badge variant={totpEnabled ? 'success' : 'warning'}>
            {totpEnabled ? '已启用' : '未启用'}
          </Badge>
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-3">
          {[
            { step: 1, title: '开启 2FA', desc: '获取密钥并启动设置' },
            { step: 2, title: '验证动态码', desc: '输入 6 位验证码确认绑定' },
            { step: 3, title: '保存恢复码', desc: '留存备用恢复码以防设备丢失' },
          ].map((item) => {
            const active = setupProgress === item.step;
            const completed = setupProgress > item.step;
            return (
              <div
                key={item.step}
                className={`rounded-lg border px-3 py-2 text-sm ${completed ? 'border-success/40 bg-success/10' : active ? 'border-primary/40 bg-primary/10' : 'border-glass-border bg-surface'}`}
              >
                <div className="text-xs text-text-secondary">步骤 {item.step}</div>
                <div className="mt-1 font-medium">{item.title}</div>
                <div className="mt-1 text-xs text-text-secondary">{item.desc}</div>
              </div>
            );
          })}
        </div>

        {!totpEnabled && !totpSetup && (
          <button
            onClick={handleSetup}
            disabled={actionDisabled}
            data-testid="security-enable-2fa-action"
            className="mt-4 px-4 py-2 bg-primary text-white rounded-lg cursor-pointer text-sm font-medium disabled:opacity-50"
          >
            {!hydrated ? '页面初始化中...' : loading ? '加载中...' : '🔑 启用 2FA'}
          </button>
        )}

        {totpSetup && (
          <div className="mt-4 space-y-4">
            <div>
              <p className="text-sm mb-2">1. 使用 Google Authenticator 扫描以下密钥：</p>
              <code data-testid="security-2fa-secret" className="block px-3 py-2 bg-surface rounded text-xs break-all">
                {totpSetup.secret}
              </code>
            </div>
            <div>
              <p className="text-sm mb-2">2. 输入 6 位验证码确认：</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={verifyCode}
                  onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  maxLength={6}
                  data-testid="security-2fa-code-input"
                  className="w-32 px-3 py-2 rounded-lg text-center text-lg font-mono tracking-widest"
                />
                <button
                  onClick={handleVerify}
                  disabled={actionDisabled || verifyCode.length !== 6}
                  data-testid="security-2fa-verify-action"
                  className="px-4 py-2 bg-primary text-white rounded-lg cursor-pointer text-sm disabled:opacity-50"
                >
                  验证
                </button>
              </div>
            </div>
            {totpSetup.backupCodes?.length > 0 && (
              <div>
                <p className="text-sm mb-2">3. 保存备用恢复码（仅显示一次）：</p>
                <div className="grid grid-cols-2 gap-1">
                  {totpSetup.backupCodes.map((code, index) => (
                    <code key={index} className="px-2 py-1 bg-surface rounded text-xs font-mono text-center">{code}</code>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {totpEnabled && (
          <button
            onClick={handleDisable}
            disabled={actionDisabled}
            data-testid="security-disable-2fa-action"
            className="mt-4 px-4 py-2 bg-danger/20 text-danger rounded-lg cursor-pointer text-xs border border-danger/30 disabled:opacity-50"
          >
            关闭 2FA
          </button>
        )}
      </SectionCard>

      <SectionCard className="p-4 mt-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="mt-0 text-sm font-semibold">交易二次确认</h3>
            <p className="text-xs text-text-secondary mt-1">下单、撤单等敏感操作需要额外确认；设置会保存到用户偏好，相关页面会按此执行。</p>
          </div>
          <span className="text-xs text-text-secondary">
            {savingKey ? '保存中...' : '自动保存'}
          </span>
        </div>
        <div className="mt-3 space-y-2">
          {TRANSACTION_CONFIRM_ITEMS.map((item) => (
            <label key={item.key} className="flex items-center justify-between py-2 gap-4">
              <span>
                <span className="block text-sm">{item.label}</span>
                <span className="block text-xs text-text-secondary mt-0.5">{item.description}</span>
              </span>
              <input
                type="checkbox"
                checked={transactionConfirmations[item.key]}
                disabled={savingKey != null}
                onChange={() => { void handleToggleTransactionConfirmation(item.key); }}
                className="accent-primary w-4 h-4 cursor-pointer disabled:cursor-not-allowed"
              />
            </label>
          ))}
        </div>
      </SectionCard>
    </PageContainer>
  );
}
