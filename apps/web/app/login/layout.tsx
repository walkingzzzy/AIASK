import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '登录',
  description: '登录 AIASK 智能股票分析平台，开始您的智能投研之旅',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
