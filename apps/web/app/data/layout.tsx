import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '数据中心',
  description: '数据同步与缓存管理中心，监控数据源状态与更新情况',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
