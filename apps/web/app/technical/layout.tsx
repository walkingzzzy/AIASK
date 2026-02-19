import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '技术分析',
  description: '技术指标计算与K线形态识别，辅助技术面交易决策',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
