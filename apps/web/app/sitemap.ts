import type { MetadataRoute } from 'next';

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://aiask.example.com';

export default function sitemap(): MetadataRoute.Sitemap {
  const routes = [
    '/',
    '/market',
    '/stock',
    '/fundamental',
    '/fund-flow',
    '/research',
    '/strategy-market',
    '/backtest',
    '/paper-trading',
    '/portfolio',
    '/risk',
    '/alerts',
  ];

  return routes.map((route) => ({
    url: `${BASE_URL}${route}`,
    lastModified: new Date(),
    changeFrequency: 'daily' as const,
    priority: route === '/' ? 1 : 0.8,
  }));
}
