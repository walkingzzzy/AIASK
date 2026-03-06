import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '模拟交易',
  description: '虚拟盘模拟交易，支持 A 股买卖、持仓跟踪与交易记录。',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
