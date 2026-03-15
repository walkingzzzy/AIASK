'use client';

import { PageContainer, SectionCard, StockCodeInput, Badge } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState, EmptyState } from '@/components/status-state';
import { extractObject, fmtNum } from '@/lib/data-utils';
import { ensureRecord } from '@/lib/query-parse';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { unwrapToolPayload } from '@/lib/tool-result';

/** Convert { key: value } object to BarChart items */
function objToItems(obj: unknown): { label: string; value: number }[] {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
  return Object.entries(obj as Record<string, unknown>)
    .filter(([, v]) => typeof v === 'number')
    .map(([k, v]) => ({ label: k.replace(/_/g, ' '), value: v as number }));
}

export default function SentimentPage() {
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode();
  const autoStockSentimentPath = resolvedCode ? `/sentiment/stock?code=${encodeURIComponent(resolvedCode)}` : null;
  const [stockSentimentPath, setStockSentimentPath] = useState<string | null>(null);
  const effectiveStockSentimentPath = stockSentimentPath ?? autoStockSentimentPath;
  const stockSentimentQ = useApiQuery<unknown>(effectiveStockSentimentPath, {
    parse: (raw) => ensureRecord(raw, '个股情绪'),
  });

  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', {
    parse: (raw) => ensureRecord(raw, '恐贪指数'),
  });

  const isPending = stockSentimentQ.isFetching || fearGreedQ.isFetching;

  function fetchStockSentiment() {
    if (!validate()) return;
    const p = `/sentiment/stock?code=${encodeURIComponent(code.trim())}`;
    if (p === effectiveStockSentimentPath) stockSentimentQ.refetch(); else setStockSentimentPath(p);
  }

  // Extract stock sentiment data: data.result.data
  const ssObj = unwrapToolPayload(stockSentimentQ.data);
  const ssScore = (ssObj.score as number) ?? null;
  const ssSentiment = String(ssObj.sentiment ?? '');
  const ssComponents = objToItems(ssObj.components);
  const ssCode = String(ssObj.code ?? resolvedCode ?? '');

  // Extract fear-greed data: data.result.data
  const fgObj = unwrapToolPayload(fearGreedQ.data);
  const fgIndex = (fgObj.index as number) ?? (fgObj.value as number) ?? null;
  const fgLevel = String(fgObj.level ?? '');
  const fgComponents = objToItems(fgObj.components);
  const primaryActionCls = 'rounded-full border border-primary px-3 py-1 text-xs text-primary';
  const secondaryActionCls = 'rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline';
  const sentimentSummary = useMemo(() => {
    if (ssScore == null) return null;
    if (ssScore >= 70) return { title: '情绪偏热', description: '短期乐观情绪较强，适合结合估值或资金流确认是否已经过热。' };
    if (ssScore <= 30) return { title: '情绪偏冷', description: '市场预期较谨慎，适合叠加基本面或风险页判断是否属于错杀。' };
    return { title: '情绪中性', description: '当前情绪没有明显单边倾向，更适合与技术形态和资金流一起交叉验证。' };
  }, [ssScore]);

  function loadSampleSentiment(sampleCode = '600519') {
    setCode(sampleCode);
    const p = `/sentiment/stock?code=${encodeURIComponent(sampleCode)}`;
    if (p === effectiveStockSentimentPath) stockSentimentQ.refetch(); else setStockSentimentPath(p);
  }

  return (
    <PageContainer>
      <h1>情绪分析</h1>
      {(stockSentimentQ.error || fearGreedQ.error) && <ErrorState text={stockSentimentQ.error || fearGreedQ.error!} />}

      <SectionCard className="p-4">
        <h3 className="mt-0">个股情绪</h3>
        <div className="flex gap-3 flex-wrap items-end">
          <StockCodeInput id="sentiment-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
          <button type="button" disabled={isPending} onClick={fetchStockSentiment}>{isPending ? '分析中...' : '查询'}</button>
        </div>
        <p className="mt-2 text-sm text-text-secondary">适合快速判断一只股票当前舆情和市场预期偏乐观还是偏谨慎，再决定是否继续看资金流或估值。</p>
        {ssCode && stockSentimentQ.data && (
          <div className="mt-3 flex items-center gap-2">
            <StockLink code={ssCode} name={ssCode} />
            <WatchlistButton code={ssCode} name="" />
            {ssSentiment && <Badge variant={ssSentiment === 'positive' ? 'success' : ssSentiment === 'negative' ? 'danger' : 'neutral'}>{ssSentiment}</Badge>}
          </div>
        )}
        {ssScore != null ? (
          <>
            {sentimentSummary ? (
              <div className="mt-3 rounded-xl border border-border bg-surface-alt/60 p-3">
                <div className="text-sm font-medium text-text-primary">{sentimentSummary.title}</div>
                <p className="mt-1 text-sm text-text-secondary">{sentimentSummary.description}</p>
              </div>
            ) : null}
            <div className="my-4">
              <GaugeChart value={ssScore} min={0} max={100} title={`情绪分数 ${fmtNum(ssScore, 1)}`} height={250} />
            </div>
            {ssComponents.length > 0 && (
              <BarChart items={ssComponents} horizontal height={Math.max(160, ssComponents.length * 50)} yAxisName="分数" />
            )}
          </>
        ) : !stockSentimentQ.data ? (
          <EmptyState
            text="输入股票代码后查看个股情绪分数"
            hint="推荐先从关注名单中的个股开始，确认市场讨论与预期是偏热还是偏冷。"
            action={
              <>
                <button type="button" onClick={() => loadSampleSentiment('600519')} className={primaryActionCls}>示例：600519</button>
                <Link href="/watchlist" className={secondaryActionCls}>查看自选股</Link>
              </>
            }
          />
        ) : (
          <EmptyState text="当前没有可展示的个股情绪结果" hint="可以换一只股票后重试，或稍后刷新等待情绪数据更新。" />
        )}
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
        ) : fearGreedQ.isPending ? <LoadingState text="加载中..." /> : <EmptyState text="当前没有可用的恐贪指数" hint="非交易时段或上游情绪源暂缺时可能为空，建议稍后再刷新。" />}
      </SectionCard>
    </PageContainer>
  );
}
