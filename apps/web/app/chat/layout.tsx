import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'AI 对话',
  description: '与 AI 自由对话，获取实时股票数据解读与投资分析',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
