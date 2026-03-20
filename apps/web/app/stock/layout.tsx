import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '个股详情',
  description: '查看个股报价、K线、技术面、资金流、基本面、估值与资讯等详情。',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}

