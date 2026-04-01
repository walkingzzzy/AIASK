import { GaugeChart } from '@/components/charts';
import { Badge, SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import { unwrapToolPayload } from '@/lib/tool-result';

type StockTechnicalTabProps = {
  technicalData: unknown;
  patternData: unknown;
  showSentiment: boolean;
  sentimentScore: number;
};

function readBadgeVariant(className: string) {
  if (className.includes('danger')) return 'danger' as const;
  if (className.includes('success')) return 'success' as const;
  return 'neutral' as const;
}

export default function StockTechnicalTab({
  technicalData,
  patternData,
  showSentiment,
  sentimentScore,
}: StockTechnicalTabProps) {
  const payload = technicalData ? unwrapToolPayload(technicalData) : null;
  const patternPayload = patternData ? unwrapToolPayload(patternData) : null;
  const rsi = payload?.rsi as Record<string, unknown> | undefined;
  const macd = payload?.macd as Record<string, unknown> | undefined;
  const kdj = payload?.kdj as Record<string, unknown> | undefined;

  const rsiVal = Number(rsi?.value ?? 0);
  const rsiSignal = String(rsi?.signal ?? 'hold');
  const rsiLabel =
    rsiSignal === 'buy' ? '买入' : rsiSignal === 'sell' ? '卖出' : rsiVal > 70 ? '超买' : rsiVal < 30 ? '超卖' : '中性';
  const rsiColor = rsiVal > 70 ? 'text-danger' : rsiVal < 30 ? 'text-success' : '';

  const macdArr = (macd?.macd ?? macd?.MACD) as number[] | undefined;
  const sigArr = (macd?.signal ?? macd?.Signal) as number[] | undefined;
  const macdLast = macdArr?.length ? macdArr[macdArr.length - 1] : null;
  const sigLast = sigArr?.length ? sigArr[sigArr.length - 1] : null;
  const macdCross = macdLast != null && sigLast != null ? (macdLast > sigLast ? '金叉' : '死叉') : '-';
  const macdCrossColor = macdCross === '金叉' ? 'text-danger' : macdCross === '死叉' ? 'text-success' : '';

  const kArr = (kdj?.k ?? kdj?.K) as number[] | undefined;
  const dArr = (kdj?.d ?? kdj?.D) as number[] | undefined;
  const jArr = (kdj?.j ?? kdj?.J) as number[] | undefined;
  const kLast = kArr?.length ? kArr[kArr.length - 1] : null;
  const dLast = dArr?.length ? dArr[dArr.length - 1] : null;
  const jLast = jArr?.length ? jArr[jArr.length - 1] : null;
  const kdjSignal = kLast != null && dLast != null ? (kLast > dLast ? '金叉' : '死叉') : '-';
  const kdjColor = kdjSignal === '金叉' ? 'text-danger' : kdjSignal === '死叉' ? 'text-success' : '';

  const patterns = (Array.isArray(patternPayload?.patterns) ? patternPayload.patterns : []) as Array<Record<string, unknown>>;

  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <h3 className="mt-0">技术指标</h3>
          {payload ? (
            <div className="space-y-3">
              <div className="panel-soft rounded-[22px] p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">RSI(14)</span>
                  <Badge variant={readBadgeVariant(rsiColor)}>{rsiLabel}</Badge>
                </div>
                <div className={`mt-1 text-2xl font-bold ${rsiColor}`}>{fmtNum(rsiVal, 2)}</div>
              </div>
              <div className="panel-soft rounded-[22px] p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">MACD</span>
                  <Badge variant={readBadgeVariant(macdCrossColor)}>{macdCross}</Badge>
                </div>
                <div className="mt-1 text-sm text-text-secondary">
                  DIF: {fmtNum(macdLast, 2)} / DEA: {fmtNum(sigLast, 2)}
                </div>
              </div>
              <div className="panel-soft rounded-[22px] p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">KDJ</span>
                  <Badge variant={readBadgeVariant(kdjColor)}>{kdjSignal}</Badge>
                </div>
                <div className="mt-1 text-sm text-text-secondary">
                  K: {fmtNum(kLast, 2)} / D: {fmtNum(dLast, 2)} / J: {fmtNum(jLast, 2)}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">查询股票后显示技术指标</p>
          )}
        </div>

        <div>
          <h3 className="mt-0">K线形态</h3>
          {patternPayload ? (
            patterns.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {patterns.map((pattern, index) => (
                  <Badge key={`${String(pattern.name ?? pattern.pattern ?? 'pattern')}-${index}`} variant={pattern.bullish ? 'danger' : 'success'}>
                    {String(pattern.name ?? pattern.pattern ?? '')} {pattern.reliability === 'high' ? '★' : ''}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">未检测到形态信号</p>
            )
          ) : (
            <p className="text-sm text-text-secondary">查询股票后显示形态检测</p>
          )}
        </div>
      </div>

      {showSentiment ? (
        <div className="mt-4">
          <h3 className="mt-0">市场情绪</h3>
          <GaugeChart
            value={sentimentScore || 50}
            min={0}
            max={100}
            title={sentimentScore > 50 ? '偏多' : sentimentScore < 50 ? '偏空' : '中性'}
            height={200}
          />
        </div>
      ) : null}
    </SectionCard>
  );
}
