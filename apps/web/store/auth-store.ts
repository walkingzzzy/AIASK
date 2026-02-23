import { create } from 'zustand';
import { clearLoggedIn } from '@/lib/auth';
import { BFF_BASE } from '@/lib/api';

type User = { id: string; username: string; role: 'admin' | 'user' };

type AuthState = {
  user: User | null;
  isAuthenticated: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  logout: () => {
    fetch(`${BFF_BASE}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
    clearLoggedIn();
    set({ user: null, isAuthenticated: false });
  },
}));
