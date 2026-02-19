import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: '估值分析',
  description: '多维度估值模型分析，包括 DCF、DDM 与相对估值法',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
