import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '用户中心',
  description: '个人账户管理与偏好设置，自定义自选股与通知配置',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
