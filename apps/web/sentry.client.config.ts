/**
 * T-042/T-043: Sentry + Performance Monitoring Config
 * Client-side instrumentation for error tracking and Core Web Vitals.
 */
import * as Sentry from '@sentry/nextjs';

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN || '',
  environment: process.env.NODE_ENV || 'development',
  enabled: !!process.env.NEXT_PUBLIC_SENTRY_DSN,

  // Performance monitoring
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 1.0,
  profilesSampleRate: process.env.NODE_ENV === 'production' ? 0.1 : 0,

  // Replay for debugging
  replaysSessionSampleRate: 0.01,
  replaysOnErrorSampleRate: 0.5,

  integrations: [
    Sentry.browserTracingIntegration(),
    Sentry.replayIntegration(),
  ],

  // Custom context
  beforeSend(event) {
    // Add page context
    if (typeof window !== 'undefined') {
      event.contexts = {
        ...event.contexts,
        page: {
          url: window.location.href,
          title: document.title,
        },
      };
    }
    return event;
  },
});
// Note: Core Web Vitals are automatically captured by Sentry's browserTracingIntegration().
