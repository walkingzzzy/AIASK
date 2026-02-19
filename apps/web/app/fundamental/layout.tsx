import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '基本面分析',
  description: '上市公司基本面深度分析，包括财务报表、盈利能力与成长性评估',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
