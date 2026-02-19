import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '策略工作台',
  description: '量化策略编写、回测与优化工作台，助力系统化投资决策',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
