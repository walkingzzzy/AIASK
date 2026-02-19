import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'TDX 集成',
  description: '通达信数据集成与公式计算，支持自定义指标与选股',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
