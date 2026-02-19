import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '告警中心',
  description: '自定义股票告警与监控，支持价格、指标与组合条件触发通知',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
