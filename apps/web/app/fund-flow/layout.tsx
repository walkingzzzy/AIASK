import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '资金流向',
  description: '主力资金、北向资金与板块资金流向追踪，洞察市场资金动向',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
