import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '情绪分析',
  description: '市场情绪指标与舆情分析，量化投资者情绪与恐贪指数',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
