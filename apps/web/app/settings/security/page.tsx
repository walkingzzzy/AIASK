'use client';

import { useState, useEffect } from 'react';
import { PageContainer, SectionCard, Badge } from '@/components/ui';
import { BFF_BASE } from '@/lib/api';

/**
 * T-039: Security Settings Page
 * TOTP setup, backup codes management, transaction confirmation settings.
 */
export default function SecurityPage() {
    const [totpEnabled, setTotpEnabled] = useState(false);
    const [totpSetup, setTotpSetup] = useState<{ secret: string; uri: string; backupCodes: string[] } | null>(null);
    const [verifyCode, setVerifyCode] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    useEffect(() => {
        fetch(`${BFF_BASE}/auth/2fa/status`, { credentials: 'include' })
            .then((r) => r.json())
            .then((d) => setTotpEnabled(d?.data?.enabled ?? false))
            .catch(() => { });
    }, []);

    const handleSetup = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${BFF_BASE}/auth/2fa/setup`, { method: 'POST', credentials: 'include' });
            const data = await res.json();
            setTotpSetup(data?.data ?? null);
        } catch (e) {
            setMessage({ type: 'error', text: '获取二维码失败' });
        } finally {
            setLoading(false);
        }
    };

    const handleVerify = async () => {
        if (!verifyCode || verifyCode.length !== 6) return;
        setLoading(true);
        try {
            const res = await fetch(`${BFF_BASE}/auth/2fa/verify`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: verifyCode }),
            });
            if (res.ok) {
                setTotpEnabled(true);
                setTotpSetup(null);
                setMessage({ type: 'success', text: '双因素认证已启用' });
            } else {
                setMessage({ type: 'error', text: '验证码错误' });
            }
        } finally {
            setLoading(false);
            setVerifyCode('');
        }
    };

    const handleDisable = async () => {
        setLoading(true);
        try {
            await fetch(`${BFF_BASE}/auth/2fa/disable`, { method: 'POST', credentials: 'include' });
            setTotpEnabled(false);
            setMessage({ type: 'success', text: '双因素认证已关闭' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <PageContainer>
            <h2 className="text-lg font-semibold mb-4">🔐 安全设置</h2>

            {message && (
                <div className={`mb-4 px-4 py-2 rounded-lg text-sm ${message.type === 'success' ? 'bg-success/15 text-success border border-success/30' : 'bg-danger/15 text-danger border border-danger/30'
                    }`}>
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

                {!totpEnabled && !totpSetup && (
                    <button
                        onClick={handleSetup}
                        disabled={loading}
                        className="mt-4 px-4 py-2 bg-primary text-white rounded-lg cursor-pointer text-sm font-medium"
                    >
                        {loading ? '加载中...' : '🔑 启用 2FA'}
                    </button>
                )}

                {totpSetup && (
                    <div className="mt-4 space-y-4">
                        <div>
                            <p className="text-sm mb-2">1. 使用 Google Authenticator 扫描以下密钥：</p>
                            <code className="block px-3 py-2 bg-surface rounded text-xs break-all">{totpSetup.secret}</code>
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
                                    className="w-32 px-3 py-2 rounded-lg text-center text-lg font-mono tracking-widest"
                                />
                                <button
                                    onClick={handleVerify}
                                    disabled={loading || verifyCode.length !== 6}
                                    className="px-4 py-2 bg-primary text-white rounded-lg cursor-pointer text-sm"
                                >
                                    验证
                                </button>
                            </div>
                        </div>
                        {totpSetup.backupCodes?.length > 0 && (
                            <div>
                                <p className="text-sm mb-2">3. 保存备用恢复码（仅显示一次）：</p>
                                <div className="grid grid-cols-2 gap-1">
                                    {totpSetup.backupCodes.map((code, i) => (
                                        <code key={i} className="px-2 py-1 bg-surface rounded text-xs font-mono text-center">{code}</code>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {totpEnabled && (
                    <button
                        onClick={handleDisable}
                        disabled={loading}
                        className="mt-4 px-4 py-2 bg-danger/20 text-danger rounded-lg cursor-pointer text-xs border border-danger/30"
                    >
                        关闭 2FA
                    </button>
                )}
            </SectionCard>

            <SectionCard className="p-4 mt-4">
                <h3 className="mt-0 text-sm font-semibold">交易二次确认</h3>
                <p className="text-xs text-text-secondary mt-1">下单、撤单等敏感操作需要额外确认</p>
                <div className="mt-3 space-y-2">
                    {['模拟交易下单', '模拟交易撤单', '告警规则修改', '组合调仓'].map((item) => (
                        <label key={item} className="flex items-center justify-between py-1.5">
                            <span className="text-sm">{item}</span>
                            <input type="checkbox" defaultChecked className="accent-primary w-4 h-4 cursor-pointer" />
                        </label>
                    ))}
                </div>
            </SectionCard>
        </PageContainer>
    );
}
