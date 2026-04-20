import type { Metadata, Viewport } from 'next';
import { IBM_Plex_Mono, IBM_Plex_Sans } from 'next/font/google';
import { Suspense } from 'react';
import './globals.css';
import QueryProvider from '@/lib/query-provider';
import AppShell from '@/components/app-shell';
import { ToastProvider } from '@/components/ui/toast';
import { GlobalOverlays } from '@/components/global-overlays';

const appSans = IBM_Plex_Sans({
  subsets: ['latin'],
  variable: '--font-app-sans',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
});

const appMono = IBM_Plex_Mono({
  subsets: ['latin'],
  variable: '--font-app-mono',
  display: 'swap',
  weight: ['400', '500', '600'],
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0b6bcb',
};

export const metadata: Metadata = {
  title: { default: 'AIASK 智能股票分析平台', template: '%s | AIASK' },
  description: 'AI 驱动的智能股票分析平台 — 实时行情、技术分析、AI 诊断、模拟交易、风控管理',
  keywords: ['股票分析', 'AI投资', '量化交易', '技术分析', '模拟交易', 'AIASK'],
  authors: [{ name: 'AIASK Team' }],
  icons: {
    icon: '/favicon.svg',
    shortcut: '/favicon.svg',
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

const themeBootstrapScript = `
  (() => {
    try {
      const stored = localStorage.getItem('theme') || 'system';
      const root = document.documentElement;
      root.classList.remove('light', 'dark');
      const next = stored === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : stored;
      root.classList.add(next);
    } catch {}
  })();
`;

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
    <html lang="zh-CN" className={`${appSans.variable} ${appMono.variable}`} suppressHydrationWarning>
      <head>
        <script src="/runtime-config.js" />
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body suppressHydrationWarning>
        <QueryProvider>
          <ToastProvider>
            <Suspense fallback={<LoadingFallback />}>
              <AppShell>{children}</AppShell>
            </Suspense>
            <GlobalOverlays />
          </ToastProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
