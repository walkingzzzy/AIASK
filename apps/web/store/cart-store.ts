import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

type CartItem = { strategyId: string; name: string; weight: number };

type CartState = {
  items: CartItem[];
  addStrategy: (item: CartItem) => void;
  removeStrategy: (id: string) => void;
  setWeight: (id: string, weight: number) => void;
  clear: () => void;
};

export const useCartStore = create<CartState>()(
  persist(
    (set) => ({
      items: [],

      addStrategy: (item) =>
        set((state) => {
          if (state.items.some((i) => i.strategyId === item.strategyId)) return state;
          return { items: [...state.items, item] };
        }),

      removeStrategy: (id) =>
        set((state) => ({
          items: state.items.filter((i) => i.strategyId !== id),
        })),

      setWeight: (id, weight) =>
        set((state) => ({
          items: state.items.map((i) => (i.strategyId === id ? { ...i, weight } : i)),
        })),

      clear: () => set({ items: [] }),
    }),
    {
      name: 'strategy_cart',
      storage: createJSONStorage(() => localStorage),
      skipHydration: true,
    },
  ),
);

// Hydrate on client only — avoids SSR mismatch
if (typeof window !== 'undefined') {
  useCartStore.persist.rehydrate();
}
