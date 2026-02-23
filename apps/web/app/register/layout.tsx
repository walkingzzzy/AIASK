import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '注册',
  description: '注册 AIASK 智能股票分析平台账号',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
