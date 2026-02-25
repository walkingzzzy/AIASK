'use client';

import { PageContainer, SectionCard, StockCodeInput, Badge } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { useEffect, useRef, useState } from 'react';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState, EmptyState } from '@/components/status-state';
import { extractObject, fmtNum } from '@/lib/data-utils';
import { ensureRecord } from '@/lib/query-parse';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';

/** Convert { key: value } object to BarChart items */
function objToItems(obj: unknown): { label: string; value: number }[] {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
  return Object.entries(obj as Record<string, unknown>)
    .filter(([, v]) => typeof v === 'number')
    .map(([k, v]) => ({ label: k.replace(/_/g, ' '), value: v as number }));
}

export default function SentimentPage() {
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode();

  const [stockSentimentPath, setStockSentimentPath] = useState<string | null>(null);
  const stockSentimentQ = useApiQuery<unknown>(stockSentimentPath, {
    parse: (raw) => ensureRecord(raw, '个股情绪'),
  });

  // 自动查询
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setStockSentimentPath(`/sentiment/stock?code=${encodeURIComponent(resolvedCode)}`);
    }
  }, [resolvedCode]);

  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', {
    parse: (raw) => ensureRecord(raw, '恐贪指数'),
  });

  const isPending = stockSentimentQ.isFetching || fearGreedQ.isFetching;

  function fetchStockSentiment() {
    if (!validate()) return;
    const p = `/sentiment/stock?code=${encodeURIComponent(code.trim())}`;
    if (p === stockSentimentPath) stockSentimentQ.refetch(); else setStockSentimentPath(p);
  }

  // Extract stock sentiment data: data.result.data
  const ssRaw = extractObject(stockSentimentQ.data);
  const ssObj = ssRaw.result ? extractObject(ssRaw.result as Record<string, unknown>) : ssRaw;
  const ssScore = (ssObj.score as number) ?? null;
  const ssSentiment = String(ssObj.sentiment ?? '');
  const ssComponents = objToItems(ssObj.components);
  const ssCode = String(ssObj.code ?? resolvedCode ?? '');

  // Extract fear-greed data: data.result.data
  const fgRaw = extractObject(fearGreedQ.data);
  const fgObj = fgRaw.result ? extractObject(fgRaw.result as Record<string, unknown>) : fgRaw;
  const fgIndex = (fgObj.index as number) ?? (fgObj.value as number) ?? null;
  const fgLevel = String(fgObj.level ?? '');
  const fgComponents = objToItems(fgObj.components);

  return (
    <PageContainer>
      <h1>情绪分析</h1>
      {(stockSentimentQ.error || fearGreedQ.error) && <ErrorState text={stockSentimentQ.error || fearGreedQ.error!} />}

      <SectionCard className="p-4">
        <h3 className="mt-0">个股情绪</h3>
        <div className="flex gap-2 items-center">
          <StockCodeInput value={code} onChange={setCode} error={codeError} />
          <button type="button" disabled={isPending} onClick={fetchStockSentiment}>{isPending ? '分析中...' : '查询'}</button>
        </div>
        {ssCode && stockSentimentQ.data && (
          <div className="mt-3 flex items-center gap-2">
            <StockLink code={ssCode} name={ssCode} />
            <WatchlistButton code={ssCode} name="" />
            {ssSentiment && <Badge variant={ssSentiment === 'positive' ? 'success' : ssSentiment === 'negative' ? 'danger' : 'neutral'}>{ssSentiment}</Badge>}
          </div>
        )}
        {ssScore != null ? (
          <>
            <div className="my-4">
              <GaugeChart value={ssScore} min={0} max={100} title={`情绪分数 ${fmtNum(ssScore, 1)}`} height={250} />
            </div>
            {ssComponents.length > 0 && (
              <BarChart items={ssComponents} horizontal height={Math.max(160, ssComponents.length * 50)} yAxisName="分数" />
            )}
          </>
        ) : !stockSentimentQ.data ? <EmptyState text="输入代码查询个股情绪" /> : null}
      </SectionCard>

      <SectionCard className="p-4 mt-4">
        <h3 className="mt-0">恐贪指数</h3>
        {fgIndex != null ? (
          <>
            <div className="my-4">
              <GaugeChart
                value={fgIndex}
                min={0}
                max={100}
                title={`${fgLevel} (${fgIndex})`}
                height={280}
                zones={[
                  { start: 0, end: 25, color: COLORS.success },
                  { start: 25, end: 50, color: COLORS.warning },
                  { start: 50, end: 75, color: '#f97316' },
                  { start: 75, end: 100, color: COLORS.danger },
                ]}
              />
            </div>
            {fgComponents.length > 0 && (
              <BarChart items={fgComponents} horizontal height={Math.max(160, fgComponents.length * 50)} yAxisName="分数" />
            )}
            <button type="button" className="mt-2 text-xs text-text-secondary" onClick={() => fearGreedQ.refetch()}>刷新</button>
          </>
        ) : fearGreedQ.isPending ? <LoadingState text="加载中..." /> : <EmptyState text="暂无恐贪数据" />}
      </SectionCard>
    </PageContainer>
  );
}
