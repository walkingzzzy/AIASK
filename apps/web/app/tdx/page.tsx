'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { ProgressBar } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState } from '@/components/status-state';
import { extractArray, extractObject } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

export default function TdxPage() {
  const [formError, setFormError] = useState<string | null>(null);

  const { code: indCode, setCode: setIndCode, codeError: indCodeError } = useStockCode('600519');
  const [indName, setIndName] = useState('MACD');
  const indMut = useApiMutation<unknown>();

  const [formula, setFormula] = useState('');
  const screenMut = useApiMutation<unknown>();

  const [pushMsg, setPushMsg] = useState('');
  const [pushCode, setPushCode] = useState('');
  const pushMut = useApiMutation<unknown>();
  const warnMut = useApiMutation<unknown>();

  const [wlName, setWlName] = useState('');
  const [wlCodes, setWlCodes] = useState('');
  const wlMut = useApiMutation<unknown>();

  const { code: sigCode, setCode: setSigCode, codeError: sigCodeError } = useStockCode('600519');
  const sigMut = useApiMutation<unknown>();

  const loading = indMut.isPending || screenMut.isPending || pushMut.isPending || warnMut.isPending || wlMut.isPending || sigMut.isPending;
  const error = formError || indMut.error || screenMut.error || pushMut.error || warnMut.error || wlMut.error || sigMut.error;

  const indValues = useMemo(() => extractArray(indMut.data, 'values', 'indicators', 'data') as Record<string, unknown>[], [indMut.data]);
  const indHasDate = indValues.length > 0 && ('date' in indValues[0] || 'time' in indValues[0]);
  const indNumericKeys = useMemo(() => {
    if (!indValues.length) return [] as string[];
    const first = indValues[0];
    return Object.keys(first).filter(k => k !== 'date' && k !== 'time' && typeof first[k] === 'number');
  }, [indValues]);
  const screenStocks = useMemo(() => extractArray(screenMut.data, 'stocks', 'results', 'data') as Record<string, unknown>[], [screenMut.data]);
  const sigSignals = useMemo(() => extractArray(sigMut.data, 'signals', 'data') as Record<string, unknown>[], [sigMut.data]);
  const pushResult = pushMut.data ? extractObject(pushMut.data) as Record<string, unknown> | null : null;
  const warnResult = warnMut.data ? extractObject(warnMut.data) as Record<string, unknown> | null : null;
  const wlResult = wlMut.data ? extractObject(wlMut.data) as Record<string, unknown> | null : null;

  function clearAndRun(fn: () => void) { setFormError(null); fn(); }

  return (
    <PageContainer>
      <h1>TDX 集成</h1>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}

      <SectionCard>
        <h3 className="mt-0">指标计算</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <StockCodeInput value={indCode} onChange={setIndCode} error={indCodeError} placeholder="股票代码" />
          <input value={indName} onChange={(e) => setIndName(e.target.value)} placeholder="指标名称，如 MACD" className="w-40" />
          <button type="button" disabled={loading} onClick={() => clearAndRun(() =>
            indMut.trigger('/tdx/calculate-indicator', { method: 'POST' }, { code: indCode.trim(), indicator: indName.trim() })
          )}>计算</button>
        </div>
        {indValues.length > 0 && indHasDate && indNumericKeys.length > 0 && (
          <LineChart
            categories={indValues.map(v => String(v.date ?? v.time ?? ''))}
            series={indNumericKeys.map(key => ({ name: key, data: indValues.map(v => Number(v[key]) || 0) }))}
            height={300}
          />
        )}
        {indValues.length > 0 ? (
          <DataTable rows={indValues} pageSize={20} onExport={() => exportCSV(indValues, `indicator-${indName}`)} />
        ) : indMut.data ? (
          <DataTable rows={[extractObject(indMut.data) as Record<string, unknown>].filter(Boolean)} />
        ) : null}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">选股器</h3>
        <textarea value={formula} onChange={(e) => setFormula(e.target.value)} placeholder="输入筛选公式" rows={3} className="w-full resize-y" />
        <button type="button" disabled={loading} className="mt-1.5" onClick={() => {
          if (!formula.trim()) { setFormError('请输入筛选公式'); return; }
          clearAndRun(() => screenMut.trigger('/tdx/screen-stocks', { method: 'POST' }, { formula: formula.trim() }));
        }}>筛选</button>
        {screenStocks.length > 0 && (
          <DataTable
            rows={screenStocks}
            columns={[
              { key: 'code', label: '代码', width: 100 },
              { key: 'name', label: '名称', width: 120 },
              { key: 'matchScore', label: '匹配度', render: (v: unknown) => <ProgressBar value={Number(v) || 0} max={100} />, width: 200 },
            ]}
            onExport={() => exportCSV(screenStocks, 'screen-results')}
          />
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">推送消息</h3>
        <textarea value={pushMsg} onChange={(e) => setPushMsg(e.target.value)} placeholder="消息内容" rows={2} className="w-full resize-y" />
        <div className="flex gap-2 flex-wrap items-center mt-1.5">
          <input value={pushCode} onChange={(e) => setPushCode(e.target.value)} maxLength={6} placeholder="股票代码（可选）" className="w-[140px]" />
          <button type="button" disabled={loading} onClick={() => {
            if (!pushMsg.trim()) { setFormError('请输入推送消息'); return; }
            const body: Record<string, unknown> = { message: pushMsg.trim() };
            if (pushCode.trim()) body.code = pushCode.trim();
            clearAndRun(() => pushMut.trigger('/tdx/push-message', { method: 'POST' }, body));
          }}>发送</button>
          <button type="button" disabled={loading} onClick={() => {
            if (!pushMsg.trim()) { setFormError('请输入预警消息'); return; }
            const body: Record<string, unknown> = { message: pushMsg.trim() };
            if (pushCode.trim()) body.code = pushCode.trim();
            clearAndRun(() => warnMut.trigger('/tdx/push-warn', { method: 'POST' }, body));
          }}>发送预警</button>
        </div>
        {pushResult && (
          <div className="mt-2 flex items-center gap-2">
            <Badge variant={String(pushResult.status) === 'error' ? 'danger' : 'success'}>{String(pushResult.status ?? '已发送')}</Badge>
            {pushResult.message ? <span className="text-sm text-text-secondary">{String(pushResult.message)}</span> : null}
          </div>
        )}
        {warnResult && (
          <div className="mt-2 flex items-center gap-2">
            <Badge variant={String(warnResult.status) === 'error' ? 'danger' : 'warning'}>{String(warnResult.status ?? '预警已发送')}</Badge>
            {warnResult.message ? <span className="text-sm text-text-secondary">{String(warnResult.message)}</span> : null}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">自选股创建</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={wlName} onChange={(e) => setWlName(e.target.value)} placeholder="自选股名称" className="w-40" />
          <input value={wlCodes} onChange={(e) => setWlCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={loading} onClick={() => {
            if (!wlName.trim() || !wlCodes.trim()) { setFormError('名称和股票代码不能为空'); return; }
            clearAndRun(() => wlMut.trigger('/tdx/create-watchlist', { method: 'POST' }, {
              name: wlName.trim(), codes: wlCodes.split(',').map((s) => s.trim()),
            }));
          }}>创建</button>
        </div>
        {wlResult && (
          <div className="mt-2 flex items-center gap-2">
            <Badge variant={String(wlResult.status) === 'error' ? 'danger' : 'success'}>{String(wlResult.status ?? '创建成功')}</Badge>
            {wlResult.name ? <span className="text-sm text-text-secondary">自选股: {String(wlResult.name)}</span> : null}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">专家信号</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <StockCodeInput value={sigCode} onChange={setSigCode} error={sigCodeError} placeholder="股票代码" />
          <button type="button" disabled={loading} onClick={() => clearAndRun(() =>
            sigMut.trigger(`/tdx/expert-signals?code=${encodeURIComponent(sigCode.trim())}`)
          )}>查询</button>
        </div>
        {sigSignals.length > 0 && (
          <DataTable
            rows={sigSignals}
            columns={[
              { key: 'name', label: '名称' },
              { key: 'type', label: '类型', render: (v: unknown) => <Badge variant="info">{String(v)}</Badge> },
              { key: 'value', label: '数值', align: 'right' as const },
              {
                key: 'direction', label: '方向',
                render: (v: unknown) => {
                  const d = String(v);
                  if (d === 'up') return <Badge variant="danger">买入</Badge>;
                  if (d === 'down') return <Badge variant="success">卖出</Badge>;
                  return <Badge variant="neutral">{d}</Badge>;
                },
              },
            ]}
            onExport={() => exportCSV(sigSignals, 'expert-signals')}
          />
        )}
      </SectionCard>
    </PageContainer>
  );
}
