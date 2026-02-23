'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { ErrorState, LoadingState } from '@/components/status-state';
import { StrategyCard, type Strategy } from '@/components/strategy-card';
import { useCartStore } from '@/store/cart-store';

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'momentum', label: '动量' },
  { key: 'value', label: '价值' },
  { key: 'quality', label: '质量' },
  { key: 'multi_factor', label: '多因子' },
  { key: 'macro', label: '宏观' },
] as const;

type RankingResponse = { strategies?: Strategy[] } | Strategy[];

export default function StrategyMarketPage() {
  const [category, setCategory] = useState<string>('all');
  const [search, setSearch] = useState('');
  const rankQ = useApiQuery<RankingResponse>(
    '/strategy-market/ranking?limit=50' + (category === 'all' ? '' : '&strategy_type=' + category),
  );
  const addToCart = useCartStore((s) => s.addStrategy);
  const cartItems = useCartStore((s) => s.items);

  const strategies = useMemo(() => {
    const d = rankQ.data;
    const raw = Array.isArray(d) ? d : (d as Record<string, unknown>)?.strategies ?? d ?? [];
    const list = Array.isArray(raw) ? raw as Strategy[] : [];
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter((s) =>
      s.name.toLowerCase().includes(q) ||
      (s.description ?? '').toLowerCase().includes(q) ||
      (s.strategy_type ?? '').toLowerCase().includes(q),
    );
  }, [rankQ.data, search]);

  const [showCart, setShowCart] = useState(false);

  return (
    <PageContainer>
      <div className="flex items-center justify-between">
        <h1>策略超市</h1>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索策略名称..."
            className="px-2 py-1 border border-border rounded text-sm w-[180px]"
          />
          <button
            onClick={() => setShowCart(!showCart)}
            className="relative px-3 py-1 text-sm rounded border border-border cursor-pointer hover:bg-surface-alt"
          >
            组合购物车
            {cartItems.length > 0 && (
              <span className="absolute -top-1.5 -right-1.5 bg-primary text-white text-[10px] w-4 h-4 rounded-full flex items-center justify-center">
                {cartItems.length}
              </span>
            )}
          </button>
        </div>
      </div>

      <TabBar tabs={CATEGORIES} active={category} onChange={setCategory} />

      {rankQ.isPending && <LoadingState text="加载策略列表..." />}
      {rankQ.error && <ErrorState text={rankQ.error} />}

      {strategies.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 mt-4">
          {strategies.map((s) => (
            <StrategyCard
              key={s.id}
              s={s}
              onAdd={(st) => addToCart({ strategyId: st.id, name: st.name, weight: 0 })}
            />
          ))}
        </div>
      )}

      {!rankQ.isPending && strategies.length === 0 && !rankQ.error && (
        <SectionCard className="mt-4 p-6 text-center text-text-secondary">
          暂无已发布的策略
        </SectionCard>
      )}

      {/* Cart Drawer */}
      {showCart && <CartDrawer onClose={() => setShowCart(false)} />}
    </PageContainer>
  );
}

function CartDrawer({ onClose }: { onClose: () => void }) {
  const { items, removeStrategy, setWeight, clear } = useCartStore();
  const createApi = useApiMutation();
  const [name, setName] = useState('');

  const totalWeight = items.reduce((sum, i) => sum + i.weight, 0);
  const weightValid = items.length > 0 && Math.abs(totalWeight - 100) < 0.01;

  function autoBalance() {
    const w = Math.floor(100 / items.length);
    const remainder = 100 - w * items.length;
    items.forEach((item, idx) => setWeight(item.strategyId, w + (idx === 0 ? remainder : 0)));
  }

  async function handleSubmit() {
    if (!weightValid) return;
    const portfolioName = name.trim() || `策略组合 ${new Date().toLocaleDateString()}`;
    await createApi.triggerAsync('/portfolio/create', { method: 'POST' }, {
      name: portfolioName,
      description: `策略组合: ${items.map((i) => `${i.name}(${i.weight}%)`).join(', ')}`,
    });
    clear();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-[340px] bg-surface-alt border-l border-border p-4 overflow-y-auto z-10">
        <div className="flex items-center justify-between mb-4">
          <h3 className="m-0 text-sm font-semibold">组合购物车 ({items.length})</h3>
          <button onClick={onClose} className="text-lg cursor-pointer">✕</button>
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
    </div>
  );
}
