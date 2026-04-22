'use client';

import { CSSProperties, useEffect } from 'react';
import { reportClientException } from '@/lib/runtime-sentry';

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => {
    void reportClientException(error);
  }, [error]);

  const digest = (error as Error & { digest?: string }).digest;
  const pageStyle: CSSProperties = {
    minHeight: '100vh',
    margin: 0,
    padding: '24px',
    display: 'grid',
    placeItems: 'center',
    background: 'radial-gradient(circle at top, #18324d 0%, #0d1522 48%, #06080d 100%)',
    color: '#f5f7fb',
    fontFamily: '"SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  };
  const cardStyle: CSSProperties = {
    width: '100%',
    maxWidth: 760,
    borderRadius: 28,
    padding: '32px',
    background: 'rgba(10, 16, 26, 0.82)',
    border: '1px solid rgba(255,255,255,0.12)',
    boxShadow: '0 24px 80px rgba(0,0,0,0.35)',
    backdropFilter: 'blur(16px)',
  };
  const buttonRowStyle: CSSProperties = {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 12,
    marginTop: 24,
  };
  const primaryButtonStyle: CSSProperties = {
    borderRadius: 999,
    padding: '10px 18px',
    border: 'none',
    background: '#3b82f6',
    color: '#fff',
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 600,
  };
  const secondaryButtonStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    padding: '10px 18px',
    border: '1px solid rgba(255,255,255,0.16)',
    background: 'transparent',
    color: '#d7dde7',
    cursor: 'pointer',
    fontSize: 14,
    textDecoration: 'none',
  };

  return (
    <html lang="zh-CN">
      <body style={{ margin: 0 }}>
        <main style={pageStyle}>
          <section style={cardStyle} role="alert" aria-live="assertive">
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 16 }}>
              <div>
                <p style={{ margin: 0, fontSize: 12, letterSpacing: '0.18em', textTransform: 'uppercase', color: '#94a3b8' }}>
                  全局异常恢复
                </p>
                <h1 style={{ margin: '14px 0 0', fontSize: 32, lineHeight: 1.2 }}>应用暂时无法继续</h1>
                <p style={{ margin: '14px 0 0', maxWidth: 560, fontSize: 16, lineHeight: 1.7, color: '#cbd5e1' }}>
                  这是一次影响整站渲染的错误。你可以先尝试恢复页面，如果连续失败，建议稍后再试，或把错误编号反馈给维护人员。
                </p>
              </div>
              <div
                style={{
                  alignSelf: 'flex-start',
                  borderRadius: 999,
                  padding: '6px 12px',
                  border: '1px solid rgba(248,113,113,0.3)',
                  background: 'rgba(248,113,113,0.12)',
                  color: '#fca5a5',
                  fontSize: 12,
                }}
              >
                需要立即恢复
              </div>
            </div>

            <div
              style={{
                display: 'grid',
                gap: 16,
                marginTop: 24,
                gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              }}
            >
              <div
                style={{
                  borderRadius: 20,
                  padding: 18,
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                }}
              >
                <h2 style={{ margin: 0, fontSize: 15 }}>建议先做什么</h2>
                <ol style={{ margin: '12px 0 0', paddingLeft: 18, color: '#cbd5e1', lineHeight: 1.8, fontSize: 14 }}>
                  <li>先点击“重新尝试”，确认是不是临时抖动。</li>
                  <li>如果你刚提交过关键操作，请先确认结果是否已生效。</li>
                  <li>仍然失败时，请记录错误编号并联系维护人员。</li>
                </ol>
              </div>

              <div
                style={{
                  borderRadius: 20,
                  padding: 18,
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                }}
              >
                <h2 style={{ margin: 0, fontSize: 15 }}>错误信息</h2>
                <p style={{ margin: '12px 0 0', color: '#e2e8f0', fontSize: 14, lineHeight: 1.7, wordBreak: 'break-word' }}>
                  {error.message || '未提供额外错误信息'}
                </p>
                {digest ? (
                  <p style={{ margin: '8px 0 0', color: '#94a3b8', fontSize: 12 }}>
                    错误编号：{digest}
                  </p>
                ) : null}
              </div>
            </div>

            <div style={buttonRowStyle}>
              <button type="button" onClick={reset} style={primaryButtonStyle}>
                重新尝试
              </button>
              <button type="button" onClick={() => window.location.reload()} style={secondaryButtonStyle}>
                刷新页面
              </button>
              <a href="/" style={secondaryButtonStyle}>
                返回首页
              </a>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}
