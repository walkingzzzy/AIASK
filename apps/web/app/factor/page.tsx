'use client';

import { useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable, Badge } from '@/components/ui';
import { BarChart, LineChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

export default function FactorPage() {
  const [formError, setFormError] = useState<string | null>(null);

  const [libPath, setLibPath] = useState<string | null>(null);
  const libQ = useApiQuery<unknown>(libPath);

  const [calcName, setCalcName] = useState('momentum');
  const [calcCodes, setCalcCodes] = useState('600519,000858');
  const calcMut = useApiMutation<unknown>();

  const [icName, setIcName] = useState('momentum');
  const [icCodes, setIcCodes] = useState('600519,000858');
  const icMut = useApiMutation<unknown>();

  const [btName, setBtName] = useState('momentum');
  const [btCodes, setBtCodes] = useState('600519,000858');
  const btMut = useApiMutation<unknown>();

  const [oosName, setOosName] = useState('momentum');
  const [oosCodes, setOosCodes] = useState('600519,000858');
  const oosMut = useApiMutation<unknown>();

  const [robName, setRobName] = useState('momentum');
  const [robCodes, setRobCodes] = useState('600519,000858');
  const robMut = useApiMutation<unknown>();

  // Per-section loading & error — 避免跨模块互相阻塞
  const libLoading = libQ.isFetching;
  const calcLoading = calcMut.isPending;
  const icLoading = icMut.isPending;
  const btLoading = btMut.isPending;
  const oosLoading = oosMut.isPending;
  const robLoading = robMut.isPending;
  const anyLoading = libLoading || calcLoading || icLoading || btLoading || oosLoading || robLoading;
  const error = formError || libQ.error || calcMut.error || icMut.error || btMut.error || oosMut.error || robMut.error;

  function splitCodes(raw: string) {
    return raw.split(',').map((s) => s.trim()).filter(Boolean);
  }

  /** Extract MCP-level error from mutation data (success:false in nested data) */
  function mcpError(d: unknown): string | null {
    if (!d || typeof d !== 'object') return null;
    const obj = d as Record<string, unknown>;
    const inner = (typeof obj.data === 'object' && obj.data) ? obj.data as Record<string, unknown> : obj;
    if (inner.success === false && inner.error) return String(inner.error);
    if (typeof inner.data === 'object' && inner.data) {
      const deep = inner.data as Record<string, unknown>;
      if (deep.success === false && deep.error) return String(deep.error);
    }
    return null;
  }

  function validateCodes(raw: string): boolean {
    const codes = splitCodes(raw);
    if (codes.length === 0) { setFormError('请输入至少一个股票代码'); return false; }
    const invalid = codes.find((c) => !/^\d{6}$/.test(c));
    if (invalid) { setFormError(`股票代码格式错误: ${invalid}（需为6位数字）`); return false; }
    return true;
  }

  const libFactors = extractArray(libQ.data, 'factors', 'values', 'results') as Array<Record<string, unknown>>;
  const calcRows = extractArray(calcMut.data, 'factors', 'values', 'results') as Array<Record<string, unknown>>;
  const icObj = extractObject(icMut.data) as Record<string, unknown> | null;
  const icTimeSeries = extractArray(icMut.data, 'timeSeries', 'ic_series', 'series') as Array<Record<string, unknown>>;
  const btObj = extractObject(btMut.data) as Record<string, unknown> | null;
  const btEquity = extractArray(btMut.data, 'equityCurve', 'returns') as Array<Record<string, unknown>>;
  const btQuantile = extractArray(btMut.data, 'quantileReturns', 'quantiles') as Array<Record<string, unknown>>;
  const oosObj = extractObject(oosMut.data) as Record<string, unknown> | null;
  const robTests = extractArray(robMut.data, 'tests', 'checks', 'results') as Array<Record<string, unknown>>;
  const robObj = extractObject(robMut.data) as Record<string, unknown> | null;

  return (
    <PageContainer>
      <h1>因子研究</h1>
      {anyLoading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}

      <SectionCard>
        <h3 className="mt-0">因子库</h3>
        <button type="button" disabled={libLoading} onClick={() => { setFormError(null); if (libPath) libQ.refetch(); else setLibPath('/factor/library'); }}>
          加载因子库
        </button>
        {libQ.data ? (
          libFactors.length ? (
            <DataTable
              rows={libFactors}
              columns={[
                { key: 'name', label: '名称', sortable: true },
                { key: 'category', label: '分类', render: (v) => v ? <Badge variant="info">{String(v)}</Badge> : '-', sortable: true },
                { key: 'description', label: '描述' },
              ]}
              onExport={() => exportCSV(libFactors, 'factor-library')}
            />
          ) : (
            <DataTable
              rows={extractArray(libQ.data) as Array<Record<string, unknown>>}
              onExport={() => exportCSV(extractArray(libQ.data) as Array<Record<string, unknown>>, 'factor-library')}
            />
          )
        ) : <EmptyState text="点击按钮加载因子库" />}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">因子计算</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={calcName} onChange={(e) => setCalcName(e.target.value)} placeholder="因子名称" className="w-40" />
          <input value={calcCodes} onChange={(e) => setCalcCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={calcLoading} onClick={() => {
            setFormError(null);
            if (!validateCodes(calcCodes)) return;
            calcMut.trigger('/factor/calculate', { method: 'POST' }, { factor_name: calcName.trim(), stock_codes: splitCodes(calcCodes) });
          }}>计算</button>
        </div>
        {calcMut.data && mcpError(calcMut.data) ? (
          <ErrorState text={mcpError(calcMut.data)!} />
        ) : calcMut.data ? (
          calcRows.length ? (
            <BarChart
              horizontal
              items={calcRows.map((r) => ({
                label: String(r.stock_code ?? r.code ?? r.name ?? ''),
                value: Number(r.factor_value ?? r.value ?? (r.data as Record<string, unknown>)?.value ?? 0),
              }))}
              yAxisName="因子值"
            />
          ) : (
            <DataTable rows={extractArray(calcMut.data) as Array<Record<string, unknown>>} />
          )
        ) : null}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">IC 分析</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={icName} onChange={(e) => setIcName(e.target.value)} placeholder="因子名称" className="w-40" />
          <input value={icCodes} onChange={(e) => setIcCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={icLoading} onClick={() => {
            setFormError(null);
            if (!validateCodes(icCodes)) return;
            icMut.trigger('/factor/ic', { method: 'POST' }, { factor_name: icName.trim(), stock_codes: splitCodes(icCodes) });
          }}>分析</button>
        </div>
        {icMut.data && mcpError(icMut.data) ? (
          <ErrorState text={mcpError(icMut.data)!} hint="IC 分析通常需要 10 只以上股票" />
        ) : icMut.data && icObj ? (
          <>
            <KpiGrid cols={4}>
              <KpiCard title="IC" value={fmtNum(Number(icObj.ic ?? icObj.IC ?? 0), 4)} />
              <KpiCard title="IC-IR" value={fmtNum(Number(icObj.icir ?? icObj.ic_ir ?? icObj.ICIR ?? 0), 4)} />
              <KpiCard title="p-value" value={fmtNum(Number(icObj.pValue ?? icObj.p_value ?? 0), 4)} />
              <KpiCard title="t-stat" value={fmtNum(Number(icObj.tStat ?? icObj.t_stat ?? icObj.tStatistic ?? 0), 4)} />
            </KpiGrid>
            {icTimeSeries.length > 0 && (
              <LineChart
                categories={icTimeSeries.map((d) => String(d.date ?? d.period ?? ''))}
                series={[{ name: 'IC', data: icTimeSeries.map((d) => Number(d.ic ?? d.value ?? 0)) }]}
                yAxisName="IC"
              />
            )}
          </>
        ) : null}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">因子回测</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={btName} onChange={(e) => setBtName(e.target.value)} placeholder="因子名称" className="w-40" />
          <input value={btCodes} onChange={(e) => setBtCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={btLoading} onClick={() => {
            setFormError(null);
            if (!validateCodes(btCodes)) return;
            btMut.trigger('/factor/backtest', { method: 'POST' }, { factor_name: btName.trim(), stock_codes: splitCodes(btCodes) });
          }}>回测</button>
        </div>
        {btMut.data && mcpError(btMut.data) ? (
          <ErrorState text={mcpError(btMut.data)!} hint="因子回测通常需要更多股票样本" />
        ) : btMut.data && btObj ? (
          <>
            <KpiGrid cols={4}>
              <KpiCard title="总收益" value={fmtPct(Number(btObj.totalReturn ?? btObj.total_return ?? 0))} />
              <KpiCard title="年化收益" value={fmtPct(Number(btObj.annualReturn ?? btObj.annual_return ?? 0))} />
              <KpiCard title="夏普比率" value={fmtNum(Number(btObj.sharpe ?? btObj.sharpe_ratio ?? 0), 2)} />
              <KpiCard title="最大回撤" value={fmtPct(Number(btObj.maxDrawdown ?? btObj.max_drawdown ?? 0))} />
            </KpiGrid>
            {btEquity.length > 0 && (
              <LineChart
                categories={btEquity.map((d) => String(d.date ?? d.period ?? ''))}
                series={[{ name: '净值', data: btEquity.map((d) => Number(d.value ?? d.equity ?? d.nav ?? 0)) }]}
                yAxisName="净值"
              />
            )}
            {btQuantile.length > 0 && (
              <BarChart
                items={btQuantile.map((q) => ({
                  label: String(q.quantile ?? q.group ?? q.name ?? ''),
                  value: Number(q.return ?? q.value ?? 0),
                }))}
                yAxisName="收益率"
                colorByValue
              />
            )}
          </>
        ) : null}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">样本外验证</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={oosName} onChange={(e) => setOosName(e.target.value)} placeholder="因子名称" className="w-40" />
          <input value={oosCodes} onChange={(e) => setOosCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={oosLoading} onClick={() => {
            setFormError(null);
            if (!validateCodes(oosCodes)) return;
            oosMut.trigger('/factor/validate-oos', { method: 'POST' }, { factor_name: oosName.trim(), stock_codes: splitCodes(oosCodes) });
          }}>验证</button>
        </div>
        {oosMut.data && mcpError(oosMut.data) ? (
          <ErrorState text={mcpError(oosMut.data)!} />
        ) : oosMut.data && oosObj ? (
          <>
            <div className="mb-2">
              <Badge variant={(oosObj.passed ?? oosObj.pass) ? 'success' : 'danger'}>
                {(oosObj.passed ?? oosObj.pass) ? '验证通过' : '验证未通过'}
              </Badge>
            </div>
            <KpiGrid cols={4}>
              <KpiCard title="样本内 IC" value={fmtNum(Number((oosObj.inSample as Record<string, unknown>)?.ic ?? oosObj.in_sample_ic ?? oosObj.is_ic ?? 0), 4)} />
              <KpiCard title="样本外 IC" value={fmtNum(Number((oosObj.outOfSample as Record<string, unknown>)?.ic ?? oosObj.out_of_sample_ic ?? oosObj.oos_ic ?? 0), 4)} />
              <KpiCard title="样本内 Sharpe" value={fmtNum(Number((oosObj.inSample as Record<string, unknown>)?.sharpe ?? oosObj.in_sample_sharpe ?? oosObj.is_sharpe ?? 0), 2)} />
              <KpiCard title="样本外 Sharpe" value={fmtNum(Number((oosObj.outOfSample as Record<string, unknown>)?.sharpe ?? oosObj.out_of_sample_sharpe ?? oosObj.oos_sharpe ?? 0), 2)} />
            </KpiGrid>
          </>
        ) : null}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">稳健性检验</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={robName} onChange={(e) => setRobName(e.target.value)} placeholder="因子名称" className="w-40" />
          <input value={robCodes} onChange={(e) => setRobCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={robLoading} onClick={() => {
            setFormError(null);
            if (!validateCodes(robCodes)) return;
            robMut.trigger('/factor/robustness-check', { method: 'POST' }, { factor_name: robName.trim(), stock_codes: splitCodes(robCodes) });
          }}>检验</button>
        </div>
        {robMut.data && mcpError(robMut.data) ? (
          <ErrorState text={mcpError(robMut.data)!} />
        ) : robMut.data ? (
          <>
            {robObj && (
              <div className="mb-2">
                <Badge variant={(robObj.passed ?? robObj.pass ?? robObj.overall_pass) ? 'success' : 'danger'}>
                  {(robObj.passed ?? robObj.pass ?? robObj.overall_pass) ? '整体通过' : '整体未通过'}
                </Badge>
              </div>
            )}
            {robTests.length > 0 ? (
              <DataTable
                rows={robTests}
                columns={[
                  { key: 'name', label: '检验项', sortable: true },
                  { key: 'passed', label: '结果', render: (v) => <Badge variant={v ? 'success' : 'danger'}>{v ? '通过' : '未通过'}</Badge> },
                  { key: 'ic', label: 'IC', render: (v) => fmtNum(Number(v ?? 0), 4), align: 'right' as const },
                  { key: 'pValue', label: 'p-value', render: (v) => fmtNum(Number(v ?? 0), 4), align: 'right' as const },
                ]}
              />
            ) : (
              <DataTable rows={extractArray(robMut.data) as Array<Record<string, unknown>>} />
            )}
          </>
        ) : null}
      </SectionCard>
    </PageContainer>
  );
}
