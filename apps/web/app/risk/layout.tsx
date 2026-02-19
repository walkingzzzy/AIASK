import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '风险分析',
  description: '投资组合风险评估与压力测试，全面监控市场风险敞口',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
