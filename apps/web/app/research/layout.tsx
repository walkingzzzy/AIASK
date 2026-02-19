import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '研报公告',
  description: '券商研报与上市公司公告聚合，快速获取最新研究观点与信息披露',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
