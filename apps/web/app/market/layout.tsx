import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '行情看板',
  description: '实时行情数据看板，涵盖沪深港美等多市场指数与个股行情',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
