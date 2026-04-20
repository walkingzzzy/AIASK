'use client';

import Link from 'next/link';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { isPublicPathname } from '@/lib/public-routes';

const MOBILE_NAV_ITEMS = [
  { href: '/', icon: '总', label: '首页' },
  { href: '/market', icon: '盘', label: '看盘' },
  { href: '/watchlist', icon: '选', label: '自选' },
  { href: '/paper-trading', icon: '交', label: '交易' },
  { href: '/assistant', icon: 'AI', label: 'AI' },
];

/**
 * T-024: MobileBottomNav
 * Bottom navigation bar visible only on mobile screens (sm and below).
 */
export function MobileBottomNav() {
    const pathname = useStablePathname();
    if (isPublicPathname(pathname)) {
        return null;
    }

  return (
    <nav
      className="safe-area-bottom fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-[color:color-mix(in_srgb,var(--color-surface)_96%,transparent)] md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
    >
      <div className="flex h-14 items-center justify-around px-2" style={{ minHeight: 'var(--mobile-bottom-nav-height)' }}>
        {MOBILE_NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex h-full w-16 flex-col items-center justify-center gap-1 no-underline transition-colors ${active ? 'text-primary' : 'text-text-secondary'
                }`}
            >
              <span
                className={`inline-flex h-8 w-8 items-center justify-center rounded-2xl border text-[11px] font-semibold tracking-[0.08em] ${active
                  ? 'border-primary/20 bg-primary/10'
                  : 'border-transparent bg-transparent'
                  }`}
              >
                {item.icon}
              </span>
              <span className="text-[10px] font-medium">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
