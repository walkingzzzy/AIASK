'use client';

import Link from 'next/link';
import { useStablePathname } from '@/hooks/use-stable-pathname';

const ADMIN_NAV = [
    { href: '/admin', label: '概览', icon: '📊' },
    { href: '/admin/tools', label: 'MCP 工具', icon: '🔧' },
    { href: '/admin/cache', label: '缓存管理', icon: '💾' },
    { href: '/admin/dead-letters', label: '死信队列', icon: '📭' },
    { href: '/admin/users', label: '用户管理', icon: '👥' },
    { href: '/settings/audit-log', label: '审计日志', icon: '📋' },
];

/**
 * T-048: Admin Layout
 * Admin-specific layout with sidebar navigation.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
    const pathname = useStablePathname();

    return (
        <div className="flex gap-4 min-h-[60vh]">
            {/* Admin sidebar */}
            <aside className="w-48 flex-shrink-0 hidden md:block">
                <div className="surface-card rounded-xl p-2 sticky top-4">
                    <h3 className="text-xs font-bold text-text-secondary px-3 py-2 uppercase tracking-wider">管理后台</h3>
                    <nav className="space-y-0.5">
                        {ADMIN_NAV.map((item) => {
                            const active = pathname === item.href;
                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm no-underline transition-colors ${active ? 'bg-primary/15 text-primary font-medium' : 'text-text-secondary hover:text-text hover:bg-white/5'
                                        }`}
                                >
                                    <span>{item.icon}</span>
                                    <span>{item.label}</span>
                                </Link>
                            );
                        })}
                    </nav>
                </div>
            </aside>
            {/* Content */}
            <main className="flex-1 min-w-0 animate-page-enter">{children}</main>
        </div>
    );
}
