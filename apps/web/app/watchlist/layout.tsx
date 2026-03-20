import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '自选股',
  description: '分组管理自选股票，实时查看涨跌、跳转行情与个股详情。',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

