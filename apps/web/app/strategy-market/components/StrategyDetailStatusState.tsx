'use client';

import Link from 'next/link';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { PageContainer, SectionCard } from '@/components/ui';
import { extractTraceId, isMissingStrategyError } from '@/app/strategy-market/lib/strategy-detail-view';
import { chipButtonCls, chipLinkCls } from './strategy-detail-panel-styles';

export function StrategyDetailLoadingState() {
  return (
    <PageContainer>
      <LoadingState text="加载策略详情..." />
    </PageContainer>
  );
}

export function StrategyDetailEmptyState({
  strategyId,
}: {
  strategyId: string | null | undefined;
}) {
  return (
    <PageContainer narrow>
      <SectionCard className="p-5 sm:p-6">
        <div className="mb-4">
          <Link href="/strategy-market" className="text-sm text-text-secondary no-underline hover:text-primary">
            &larr; 返回策略超市
          </Link>
        </div>
        <EmptyState
          variant="full"
          text="当前环境还没有可用的策略详情数据"
          hint={`当前路由使用的是详情空态契约（ID: ${strategyId ?? '-'}）。可以先回到策略超市查看空态提示，或先运行工厂生成可进入的策略详情。`}
          action={
            <>
              <Link href="/strategy-market" className={chipLinkCls}>
                返回策略列表
              </Link>
              <button type="button" onClick={() => window.location.reload()} className={chipButtonCls}>
                重新加载
              </button>
            </>
          }
        />
      </SectionCard>
    </PageContainer>
  );
}

type StrategyDetailErrorStateProps = {
  strategyId: string | null | undefined;
  detailError: string | null;
};

export function StrategyDetailErrorState({
  strategyId,
  detailError,
}: StrategyDetailErrorStateProps) {
  const traceId = extractTraceId(detailError);
  const missingStrategy = isMissingStrategyError(detailError);

  return (
    <PageContainer narrow>
      <SectionCard className="p-5 sm:p-6">
        <div className="mb-4">
          <Link href="/strategy-market" className="text-sm text-text-secondary no-underline hover:text-primary">
            &larr; 返回策略超市
          </Link>
        </div>
        {missingStrategy ? (
          <EmptyState
            text="策略不存在或已下架"
            hint={`你访问的策略 ID「${strategyId ?? '-'}」目前不可用，可能是链接无效、策略已归档，或当前环境没有这条记录。`}
            action={
              <>
                <Link href="/strategy-market" className={chipLinkCls}>
                  返回策略列表
                </Link>
                <button type="button" onClick={() => window.location.reload()} className={chipButtonCls}>
                  重新加载
                </button>
              </>
            }
          />
        ) : (
          <>
            <ErrorState
              text="策略详情暂时无法加载"
              hint="可以先返回策略超市重新选择，或稍后再试；原始接口路径和技术细节已下沉到下方折叠区。"
            />
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/strategy-market" className={chipLinkCls}>
                返回策略列表
              </Link>
              <button type="button" onClick={() => window.location.reload()} className={chipButtonCls}>
                重新加载
              </button>
            </div>
          </>
        )}
        {detailError ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-text-muted">查看技术详情</summary>
            <div className="panel-soft mt-2 rounded-[22px] p-3 text-xs text-text-secondary">
              <div>策略 ID：{strategyId ?? '-'}</div>
              {traceId ? <div className="mt-1">Trace ID：{traceId}</div> : null}
              <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{detailError}</pre>
            </div>
          </details>
        ) : null}
      </SectionCard>
    </PageContainer>
  );
}
