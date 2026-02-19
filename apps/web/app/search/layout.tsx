import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '智能搜索',
  description: '语义化股票搜索，支持按名称、代码、行业与相似K线查找',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
