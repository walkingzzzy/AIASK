'use client';

import { useState, createContext, useContext, useCallback, type ReactNode } from 'react';

type ToastType = 'success' | 'error' | 'warning' | 'info';
type ToastItem = { id: number; message: string; type: ToastType };

const ToastContext = createContext<{ toast: (message: string, type?: ToastType) => void }>({
  toast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

const TYPE_CLASSES: Record<ToastType, string> = {
  success: 'bg-success/80 backdrop-blur-md',
  error: 'bg-danger/80 backdrop-blur-md',
  warning: 'bg-warning/80 backdrop-blur-md',
  info: 'bg-primary/80 backdrop-blur-md',
};

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++nextId;
    setItems((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 3000);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={`${TYPE_CLASSES[t.type]} text-white px-4 py-2 rounded-xl shadow-lg text-sm border border-white/20 animate-[fadeIn_0.2s]`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
