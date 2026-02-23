import type { Metadata, Viewport } from 'next';
import { Suspense } from 'react';
import './globals.css';
import QueryProvider from '@/lib/query-provider';
import AppShell from '@/components/app-shell';
import { ToastProvider } from '@/components/ui/toast';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#1a73e8',
};

export const metadata: Metadata = {
  title: { default: 'AIASK 智能股票分析', template: '%s | AIASK' },
  description: '基于 AI 的智能股票分析平台',
};

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="flex items-center gap-3">
        <div className="relative w-5 h-5">
          <div className="absolute inset-0 rounded-full border-2 border-primary/30" />
          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-primary animate-[spin_0.8s_linear_infinite]" />
        </div>
        <span className="text-text-secondary text-sm">加载中...</span>
      </div>
    </div>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="preconnect" href={process.env.NEXT_PUBLIC_BFF_BASE_URL ? new URL(process.env.NEXT_PUBLIC_BFF_BASE_URL).origin : 'http://localhost:3001'} />
      </head>
      <body>
        <QueryProvider>
          <ToastProvider>
            <Suspense fallback={<LoadingFallback />}>
              <AppShell>{children}</AppShell>
            </Suspense>
          </ToastProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
