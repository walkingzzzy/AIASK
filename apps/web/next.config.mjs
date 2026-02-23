import { withSentryConfig } from '@sentry/nextjs';

const bffUrl = process.env.NEXT_PUBLIC_BFF_BASE_URL || 'http://localhost:3001/api';
let bffOrigin;
try { bffOrigin = new URL(bffUrl).origin; } catch { bffOrigin = 'http://localhost:3001'; }

const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${bffOrigin} ws://localhost:* https://*.ingest.sentry.io`,
  "frame-ancestors 'none'",
].join('; ');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-DNS-Prefetch-Control', value: 'on' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
          { key: 'Content-Security-Policy', value: csp },
        ],
      },
    ];
  },
};

export default withSentryConfig(nextConfig, {
  silent: true,
  org: process.env.SENTRY_ORG || '',
  project: process.env.SENTRY_PROJECT || '',
  disableSourceMapUpload: !process.env.SENTRY_AUTH_TOKEN,
});
