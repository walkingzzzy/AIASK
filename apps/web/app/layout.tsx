import type { Metadata, Viewport } from 'next';
import { Suspense } from 'react';
import './globals.css';
import QueryProvider from '@/lib/query-provider';
import AppShell from '@/components/app-shell';
import { ToastProvider } from '@/components/ui/toast';
import { AlertToastProvider } from '@/components/alert-toast';
import { Spotlight } from '@/components/spotlight';
import { MobileBottomNav } from '@/components/mobile-nav';
import { WatchlistInit } from '@/components/watchlist-init';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#1a73e8',
};

export const metadata: Metadata = {
  title: { default: 'AIASK 智能股票分析平台', template: '%s | AIASK' },
  description: 'AI 驱动的智能股票分析平台 — 实时行情、技术分析、AI 诊断、模拟交易、风控管理',
  keywords: ['股票分析', 'AI投资', '量化交易', '技术分析', '模拟交易', 'AIASK'],
  authors: [{ name: 'AIASK Team' }],
  icons: {
    icon: '/favicon.ico',
    apple: '/apple-touch-icon.png',
  },
  openGraph: {
    type: 'website',
    title: 'AIASK 智能股票分析平台',
    description: 'AI 驱动的智能股票分析 — 实时行情 · 多维度诊断 · 量化回测 · 模拟交易',
    siteName: 'AIASK',
    locale: 'zh_CN',
  },
  robots: { index: true, follow: true },
  manifest: '/manifest.json',
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
            <AlertToastProvider />
            <Spotlight />
            <MobileBottomNav />
            <WatchlistInit />
          </ToastProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
