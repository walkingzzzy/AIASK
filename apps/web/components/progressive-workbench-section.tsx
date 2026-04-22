'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui';
import { FreshnessTag } from '@/components/ui/freshness-tag';
import ResultWorkbench from '@/components/result-workbench';
import type { ResultAction, ResultContract, ResultLink } from '@aiask/shared-types';
import type { WorkspacePageKey } from '@/store/workbench-store';

type ProgressiveWorkbenchSectionProps = {
  pageKey: WorkspacePageKey;
  title: string;
  result: ResultContract | null | undefined;
  compareContent?: ReactNode;
  visualContent?: ReactNode;
  extraActions?: ResultAction[];
  extraLinks?: ResultLink[];
  className?: string;
  defaultOpen?: boolean;
  summaryMode?: 'panel' | 'strip';
};

const STATUS_LABELS: Record<NonNullable<ResultContract['status']>, string> = {
  ready: '已就绪',
  loading: '加载中',
  empty: '待输入',
  degraded: '降级',
  unavailable: '不可用',
};

export default function ProgressiveWorkbenchSection({
  pageKey,
  title,
  result,
  compareContent,
  visualContent,
  extraActions = [],
  extraLinks = [],
  className = '',
  defaultOpen = false,
  summaryMode = 'panel',
}: ProgressiveWorkbenchSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    setOpen(defaultOpen);
  }, [defaultOpen]);

  const nextActionLabel = result?.primaryAction?.label ?? result?.secondaryActions?.[0]?.label ?? '查看详细下一步';
  const nextSteps = useMemo(
    () => (result?.recommendedNextActions ?? []).filter(Boolean).slice(0, 2),
    [result?.recommendedNextActions],
  );

  if (!result) return null;

  if (summaryMode === 'strip') {
    return (
      <section className={`panel-soft rounded-[20px] p-3.5 sm:p-4 ${className}`}>
        <button type="button" onClick={() => setOpen((value) => !value)} className="w-full cursor-pointer text-left">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <div className="eyebrow">Result Summary</div>
                <Badge variant={result.status === 'degraded' || result.status === 'unavailable' ? 'warning' : 'neutral'}>
                  {STATUS_LABELS[result.status ?? 'ready']}
                </Badge>
              </div>
              <div className="mt-2 text-sm font-semibold text-text-primary">{title}</div>
              <p className="mb-0 mt-1 text-sm leading-6 text-text-secondary">{result.summary}</p>
              {nextSteps[0] ? (
                <div className="mt-2 inline-flex rounded-[16px] border border-white/55 bg-white/28 px-3 py-1.5 text-xs text-text-secondary">
                  {nextSteps[0]}
                </div>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">{open ? '收起工作台' : nextActionLabel}</Badge>
              {result.freshness?.updatedAt ? (
                <FreshnessTag
                  updatedAt={result.freshness.updatedAt}
                  label={result.freshness.label ?? undefined}
                  source={result.platformMeta?.sourceTool ?? undefined}
                />
              ) : null}
            </div>
          </div>
        </button>

        {open ? (
          <ResultWorkbench
            pageKey={pageKey}
            title={title}
            result={result}
            compareContent={compareContent}
            visualContent={visualContent}
            extraActions={extraActions}
            extraLinks={extraLinks}
            className="mt-3"
          />
        ) : null}
      </section>
    );
  }

  return (
    <section className={`panel-soft rounded-[24px] p-4 sm:p-5 ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="w-full cursor-pointer text-left"
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="eyebrow">Result Summary</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <h2 className="m-0 text-lg font-semibold text-text-primary">{title}</h2>
              <Badge variant={result.status === 'degraded' || result.status === 'unavailable' ? 'warning' : 'neutral'}>
                {STATUS_LABELS[result.status ?? 'ready']}
              </Badge>
            </div>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{result.summary}</p>
            {nextSteps.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {nextSteps.map((step) => (
                  <span key={step} className="metric-tile rounded-[18px] px-3 py-2 text-xs text-text-secondary">
                    {step}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">{open ? '收起工作台' : nextActionLabel}</Badge>
            {result.freshness?.updatedAt ? (
              <FreshnessTag
                updatedAt={result.freshness.updatedAt}
                label={result.freshness.label ?? undefined}
                source={result.platformMeta?.sourceTool ?? undefined}
              />
            ) : null}
          </div>
        </div>
      </button>

      {open ? (
        <ResultWorkbench
          pageKey={pageKey}
          title={title}
          result={result}
          compareContent={compareContent}
          visualContent={visualContent}
          extraActions={extraActions}
          extraLinks={extraLinks}
          className="mt-4"
        />
      ) : null}
    </section>
  );
}
