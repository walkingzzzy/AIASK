import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '智能助手',
  description: 'AI 智能投研助手，提供个性化股票分析与投资建议',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
