'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { isPublicPathname } from '@/lib/public-routes';

const MOBILE_NAV_ITEMS = [
    { href: '/', icon: '🏠', label: '首页' },
    { href: '/market', icon: '📊', label: '行情' },
    { href: '/watchlist', icon: '⭐', label: '自选' },
    { href: '/paper-trading', icon: '💹', label: '交易' },
    { href: '/assistant', icon: '🤖', label: 'AI' },
];

/**
 * T-024: MobileBottomNav
 * Bottom navigation bar visible only on mobile screens (sm and below).
 */
export function MobileBottomNav() {
    const pathname = usePathname();
    if (isPublicPathname(pathname)) {
        return null;
    }

    return (
        <nav
            className="fixed bottom-0 left-0 right-0 z-40 glass-strong border-t border-glass-border md:hidden safe-area-bottom"
            style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
        >
            <div className="flex justify-around items-center h-14" style={{ minHeight: 'var(--mobile-bottom-nav-height)' }}>
                {MOBILE_NAV_ITEMS.map((item) => {
                    const active = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`flex flex-col items-center justify-center gap-0.5 w-16 h-full no-underline transition-colors ${active ? 'text-primary' : 'text-text-secondary'
                                }`}
                        >
                            <span className="text-lg">{item.icon}</span>
                            <span className="text-[10px] font-medium">{item.label}</span>
                        </Link>
                    );
                })}
            </div>
        </nav>
    );
}
