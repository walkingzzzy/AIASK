'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useCartStore } from '@/store/cart-store';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { ConfirmDialog } from '@/components/ui';
import { hasLoggedInHint } from '@/lib/auth';
import { readTransactionConfirmations } from '@/lib/transaction-confirmations';

export function CartDrawer({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { items, removeStrategy, setWeight, clear } = useCartStore();
  const createApi = useApiMutation();
  const hasLoginHint = hasLoggedInHint();
  const profileQ = useApiQuery<Record<string, unknown>>(hasLoginHint ? '/auth/profile' : null, {
    enabled: hasLoginHint,
    redirectOnUnauthorized: false,
    nonFatal: true,
    fallbackData: {},
  });
  const [name, setName] = useState('');
  const [pendingCreate, setPendingCreate] = useState<{ name: string; description: string } | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<Element | null>(null);

  const handleEscape = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    previousFocusRef.current = document.activeElement;
    drawerRef.current?.focus();
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
      if (previousFocusRef.current instanceof HTMLElement) {
        previousFocusRef.current.focus();
      }
    };
  }, [handleEscape]);

  const totalWeight = items.reduce((sum, i) => sum + i.weight, 0);
  const weightValid = items.length > 0 && Math.abs(totalWeight - 100) < 0.01;
  const confirmPrefs = readTransactionConfirmations(profileQ.data);

  function autoBalance() {
    const w = Math.floor(100 / items.length);
    const remainder = 100 - w * items.length;
    items.forEach((item, idx) => setWeight(item.strategyId, w + (idx === 0 ? remainder : 0)));
  }

  async function executeCreatePortfolio(payload: { name: string; description: string }) {
    const result = await createApi.triggerAsync('/portfolio/create', { method: 'POST' }, {
      name: payload.name,
      description: payload.description,
      strategies: items.map((i) => ({ strategyId: i.strategyId, weight: i.weight / 100 })),
    });
    const createdId =
      result && typeof result === 'object' && 'portfolioId' in result
        ? String((result as { portfolioId?: unknown }).portfolioId ?? '')
        : '';
    clear();
    onClose();
    if (createdId) {
      router.push(`/portfolio?portfolio_id=${encodeURIComponent(createdId)}&from=strategy-cart`);
    }
  }

  async function handleSubmit() {
    if (!weightValid) return;
    const payload = {
      name: name.trim() || `策略组合 ${new Date().toLocaleDateString()}`,
      description: `策略组合: ${items.map((i) => `${i.name}(${i.weight}%)`).join(', ')}`,
    };
    if (confirmPrefs.portfolioRebalance) {
      setPendingCreate(payload);
      return;
    }
    await executeCreatePortfolio(payload);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="组合购物车">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} role="presentation" />
      <div ref={drawerRef} tabIndex={-1} className="relative w-85 bg-surface-alt border-l border-border p-4 overflow-y-auto z-10 outline-none">
        <div className="flex items-center justify-between mb-4">
          <h3 className="m-0 text-sm font-semibold">组合购物车 ({items.length})</h3>
          <button onClick={onClose} aria-label="关闭购物车" className="text-lg cursor-pointer">✕</button>
        </div>

        {items.length === 0 && <p className="text-text-secondary text-sm">购物车为空，请从策略列表添加策略</p>}

        {items.map((item) => (
          <div key={item.strategyId} className="flex items-center gap-2 py-2 border-b border-border">
            <div className="flex-1 text-sm truncate">{item.name}</div>
            <input
              type="number"
              min={0}
              max={100}
              value={item.weight}
              onChange={(e) => setWeight(item.strategyId, Number(e.target.value))}
              className="w-14 px-1 py-0.5 border border-border rounded text-xs text-center"
              placeholder="%"
            />
            <span className="text-[10px] text-text-secondary">%</span>
            <button onClick={() => removeStrategy(item.strategyId)} className="text-danger text-xs cursor-pointer">删除</button>
          </div>
        ))}

        {items.length > 0 && (
          <>
            <div className={`text-xs mt-2 ${weightValid ? 'text-success' : 'text-danger'}`}>
              权重合计: {totalWeight.toFixed(1)}%{!weightValid && ' (需等于100%)'}
            </div>
            <div className="mt-3 space-y-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="组合名称（可选）"
                className="w-full px-2 py-1 border border-border rounded text-xs"
              />
              <div className="flex gap-2">
                <button onClick={autoBalance} className="flex-1 px-2 py-1 text-xs border border-border rounded cursor-pointer hover:bg-surface-alt">
                  等权分配
                </button>
                <button onClick={clear} className="flex-1 px-2 py-1 text-xs border border-border rounded cursor-pointer hover:bg-surface-alt">
                  清空
                </button>
              </div>
              <button
                onClick={handleSubmit}
                disabled={!weightValid || createApi.isPending}
                className="w-full px-2 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
              >
                {createApi.isPending ? '创建中...' : '创建策略组合'}
              </button>
              {createApi.error && <p className="text-danger text-xs">{createApi.error}</p>}
            </div>
          </>
        )}
      </div>
      <ConfirmDialog
        open={pendingCreate != null}
        title="确认创建策略组合"
        confirmText="确认创建"
        onCancel={() => setPendingCreate(null)}
        onConfirm={() => {
          if (!pendingCreate) return;
          const payload = pendingCreate;
          setPendingCreate(null);
          void executeCreatePortfolio(payload);
        }}
      >
        <div className="space-y-2">
          <div>当前操作已开启“组合调仓”二次确认。</div>
          <div className="text-xs text-text-secondary">
            即将创建：
            <span className="ml-1 font-medium text-text-primary">{pendingCreate?.name ?? '-'}</span>
          </div>
        </div>
      </ConfirmDialog>
    </div>
  );
}
