import type { Metadata } from 'next';
import './globals.css';
import QueryProvider from '@/lib/query-provider';
import AppShell from '@/components/app-shell';
import { ToastProvider } from '@/components/ui/toast';

export const metadata: Metadata = {
  title: { default: 'AIASK 智能股票分析', template: '%s | AIASK' },
  description: '基于 AI 的智能股票分析平台',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <QueryProvider>
          <ToastProvider>
            <AppShell>{children}</AppShell>
          </ToastProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
