'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => { Sentry.captureException(error); }, [error]);

  return (
    <html lang="zh-CN">
      <body>
        <div style={{ maxWidth: 600, margin: '80px auto', textAlign: 'center', fontFamily: 'system-ui, sans-serif' }}>
          <h2>应用出错了</h2>
          <p style={{ color: '#666', marginTop: 8 }}>{error.message}</p>
          <button onClick={reset} style={{ marginTop: 16, padding: '8px 16px', cursor: 'pointer' }}>
            重试
          </button>
        </div>
      </body>
    </html>
  );
}
