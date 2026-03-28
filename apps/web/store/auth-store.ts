import { create } from 'zustand';
import { clearLoggedIn } from '@/lib/auth';
import { getBffBaseUrl } from '@/lib/bff-base';

export type User = {
  id: string;
  username: string;
  role: 'admin' | 'user';
  riskLevel?: string | null;
  nickname?: string | null;
  avatarUrl?: string | null;
  preferences?: Record<string, unknown>;
};

type AuthState = {
  user: User | null;
  isAuthenticated: boolean;
  isLoggingOut: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoggingOut: false,
  setUser: (user) => set({ user, isAuthenticated: !!user, isLoggingOut: false }),
  logout: () => {
    clearLoggedIn();
    set({ user: null, isAuthenticated: false, isLoggingOut: true });
    fetch(`${getBffBaseUrl()}/auth/logout`, { method: 'POST', credentials: 'include', keepalive: true }).catch(() => {});
  },
}));
