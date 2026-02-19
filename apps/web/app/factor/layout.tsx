import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '因子分析',
  description: '多因子模型分析与因子库管理，支持因子回测与IC分析',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
