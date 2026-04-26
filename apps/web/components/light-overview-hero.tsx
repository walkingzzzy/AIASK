'use client';

import { ReactNode } from 'react';

type LightHeroMetric = {
  key: string;
  label: string;
  value: string;
  hint?: string;
  tone?: 'default' | 'success' | 'danger';
};

type LightOverviewHeroProps = {
  eyebrow: string;
  title: string;
  summary: string;
  badges?: ReactNode;
  actions?: ReactNode;
  status?: ReactNode;
  metrics?: LightHeroMetric[];
  compact?: boolean;
  secondary?: ReactNode;
  detailsTitle?: string;
  detailsContent?: ReactNode;
  className?: string;
  testId?: string;
};

function metricTone(tone: LightHeroMetric['tone']) {
  if (tone === 'success') return 'text-success';
  if (tone === 'danger') return 'text-danger';
  return 'text-text-primary';
}

function MetricGrid({ metrics }: { metrics: LightHeroMetric[] }) {
  if (!metrics.length) return null;
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((item) => (
        <div key={item.key} className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">{item.label}</div>
          <div className={`mt-2 text-lg font-semibold ${metricTone(item.tone)}`}>{item.value}</div>
          {item.hint ? <div className="mt-1 text-xs text-text-secondary">{item.hint}</div> : null}
        </div>
      ))}
    </div>
  );
}

export default function LightOverviewHero({
  eyebrow,
  title,
  summary,
  badges,
  actions,
  status,
  metrics = [],
  compact = false,
  secondary,
  detailsTitle = '展开更多摘要',
  detailsContent,
  className = '',
  testId,
}: LightOverviewHeroProps) {
  const visibleMetrics = compact ? metrics.slice(0, 1) : metrics;
  const hiddenMetrics = compact ? metrics.slice(1) : [];
  const hasCompactDetails = hiddenMetrics.length > 0 || Boolean(detailsContent);

  return (
    <section className={`page-hero p-4 sm:p-5 ${className}`} {...(testId ? { 'data-testid': testId } : {})}>
      <div className={`grid gap-5 ${compact || !secondary ? '' : 'xl:grid-cols-[minmax(0,1fr)_320px]'}`}>
        <div>
          <div className="eyebrow">{eyebrow}</div>
          {badges ? <div className="mt-3 flex flex-wrap items-center gap-2">{badges}</div> : null}
          <h1 className="mb-0 mt-3 text-[1.75rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2rem]">
            {title}
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-6 text-text-secondary sm:text-[15px]">{summary}</p>
          {actions ? <div className="mt-4 flex flex-wrap gap-2">{actions}</div> : null}
          {status ? <div className="mt-4">{status}</div> : null}
          <MetricGrid metrics={visibleMetrics} />
          {compact && hasCompactDetails ? (
            <details className="mt-3 rounded-[22px] border border-white/45 bg-white/24 px-4 py-3">
              <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">{detailsTitle}</summary>
              {hiddenMetrics.length > 0 ? <MetricGrid metrics={hiddenMetrics} /> : null}
              {detailsContent ? <div className="mt-3">{detailsContent}</div> : null}
            </details>
          ) : null}
        </div>

        {!compact && secondary ? <div className="grid gap-3">{secondary}</div> : null}
      </div>
    </section>
  );
}
