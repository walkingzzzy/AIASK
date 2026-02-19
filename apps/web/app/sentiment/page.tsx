'use client';

import { PageContainer, SectionCard, StockCodeInput, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
import { GaugeChart, BarChart, LineChart, COLORS } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState, EmptyState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

export default function SentimentPage() {
  const { code, setCode, codeError, validate } = useStockCode();
  const stockSentiment = useApiMutation<unknown>();
  const fearGreed = useApiMutation<unknown>();

  const isPending = stockSentiment.isPending || fearGreed.isPending;
  const error = stockSentiment.error || fearGreed.error;

  function fetchStockSentiment() {
    if (!validate()) return;
    stockSentiment.trigger(`/sentiment/stock?code=${encodeURIComponent(code.trim())}`);
  }

  function fetchFearGreed() {
    fearGreed.trigger('/sentiment/fear-greed');
  }

  return (
    <PageContainer>
      <h1>情绪分析</h1>
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      {isPending ? <LoadingState text="分析中..." /> : null}

      <SectionCard className="p-4">
        <h3 className="mt-0">个股情绪</h3>
        <div className="flex gap-2 items-center">
          <StockCodeInput value={code} onChange={setCode} error={codeError} />
          <button
            type="button"
            disabled={isPending}
            onClick={fetchStockSentiment}
            className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm"
          >
            分析情绪
          </button>
        </div>
        {stockSentiment.data ? (() => {
          const obj = extractObject(stockSentiment.data);
          const score = (obj.score as number) ?? (obj.sentiment_score as number) ?? null;
          const positive = (obj.positive as number) ?? (obj.positive_count as number) ?? null;
          const negative = (obj.negative as number) ?? (obj.negative_count as number) ?? null;
          const neutral = (obj.neutral as number) ?? (obj.neutral_count as number) ?? null;
          const keywords = (extractArray(obj, 'keywords') as unknown as string[]).filter((k) => typeof k === 'string');
          const news = extractArray(obj, 'news', 'articles', 'list');
          return (
            <>
              {score != null && (
                <div className="flex justify-center my-4">
                  <GaugeChart value={score} min={0} max={100} title="情绪分数" height={250} />
                </div>
              )}
              <KpiGrid cols={3}>
                <KpiCard title="正面" value={positive != null ? fmtNum(positive) : '-'} />
                <KpiCard title="负面" value={negative != null ? fmtNum(negative) : '-'} />
                <KpiCard title="中性" value={neutral != null ? fmtNum(neutral) : '-'} />
              </KpiGrid>
              {keywords.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-4">
                  {keywords.map((kw, i) => <Badge key={i} variant="info">{String(kw)}</Badge>)}
                </div>
              )}
              {news.length > 0 && (
                <DataTable
                  rows={news}
                  columns={[
                    { key: 'title', label: '标题' },
                    { key: 'source', label: '来源' },
                    { key: 'date', label: '日期' },
                    { key: 'sentiment', label: '情绪', render: (v: unknown) => {
                      const s = String(v ?? '');
                      const variant = s.includes('正') || s.includes('positive') ? 'success' as const : s.includes('负') || s.includes('negative') ? 'danger' as const : 'neutral' as const;
                      return <Badge variant={variant}>{s || '-'}</Badge>;
                    }},
                  ]}
                  maxHeight={400}
                  onExport={() => exportCSV(news, '个股情绪新闻')}
                />
              )}
              {score == null && keywords.length === 0 && news.length === 0 && (
                <DataTable rows={extractArray(stockSentiment.data)} onExport={() => exportCSV(extractArray(stockSentiment.data) as Record<string, unknown>[], '个股情绪')} />
              )}
            </>
          );
        })() : <EmptyState text="输入代码查询个股情绪" />}
      </SectionCard>

      <SectionCard className="p-4">
        <h3 className="mt-0">恐贪指数</h3>
        <button
          type="button"
          disabled={isPending}
          onClick={fetchFearGreed}
          className="px-3 py-1 bg-primary text-white rounded cursor-pointer disabled:opacity-50 text-sm"
        >
          查询恐贪指数
        </button>
        {fearGreed.data ? (() => {
          const obj = extractObject(fearGreed.data);
          const indexValue = (obj.index as number) ?? (obj.value as number) ?? (obj.fear_greed_index as number) ?? null;
          const components = extractArray(obj, 'components', 'factors', 'scores');
          const history = extractArray(obj, 'history', 'trend', 'historical');
          return (
            <>
              {indexValue != null && (
                <div className="flex justify-center my-4">
                  <GaugeChart
                    value={indexValue}
                    min={0}
                    max={100}
                    title="恐贪指数"
                    height={300}
                    zones={[
                      { start: 0, end: 25, color: COLORS.success },
                      { start: 25, end: 50, color: COLORS.warning },
                      { start: 50, end: 75, color: '#f97316' },
                      { start: 75, end: 100, color: COLORS.danger },
                    ]}
                  />
                </div>
              )}
              {components.length > 0 && (
                <BarChart
                  items={components.map((c: Record<string, unknown>) => ({
                    label: (c.name as string) ?? (c.label as string) ?? '',
                    value: (c.value as number) ?? (c.score as number) ?? 0,
                  }))}
                  horizontal
                  height={Math.max(200, components.length * 40)}
                  yAxisName="分数"
                />
              )}
              {history.length > 0 && (
                <LineChart
                  categories={history.map((h: Record<string, unknown>) => String(h.date ?? h.time ?? ''))}
                  series={[{
                    name: '恐贪指数',
                    data: history.map((h: Record<string, unknown>) => (h.value as number) ?? (h.index as number) ?? 0),
                    color: COLORS.primary,
                  }]}
                  height={300}
                  yAxisName="指数"
                />
              )}
              {indexValue == null && components.length === 0 && history.length === 0 && (
                <DataTable rows={extractArray(fearGreed.data)} onExport={() => exportCSV(extractArray(fearGreed.data) as Record<string, unknown>[], '恐贪指数')} />
              )}
            </>
          );
        })() : <EmptyState text="点击按钮查询全市场恐贪指数" />}
      </SectionCard>
    </PageContainer>
  );
}