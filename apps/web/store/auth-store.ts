import { create } from 'zustand';
import { clearCookies } from '@/lib/auth';

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
  logout: () => { clearCookies(); set({ user: null, isAuthenticated: false }); },
}));
