import { Play, RefreshCw, Save, Search, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { DryRunPreview, GatedActionButton } from "../components/IntentComponents";
import { EmptyState as SharedEmptyState, MockDataNotice } from "../components/StateComponents";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, EmptyState, GatedNotice, JsonPanel, LinkCard, PageShell, Panel, ResourcePanel, StatusBadge } from "../components/ui";
import { dataObject, firstArray, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";

export function FinancePages(props: PageProps) {
  switch (props.view) {
    case "stock-data-sources":
      return <StockDataSourcesPage {...props} />;
    case "data-sync":
      return <DataSyncPage {...props} />;
    case "finance-lab":
      return <FinanceLabPage {...props} />;
    case "stock-radar":
      return <StockRadarPage {...props} />;
    case "market-temperature":
      return <MarketTemperaturePage {...props} />;
    case "quant-research":
      return <QuantResearchPage {...props} />;
    case "financial-manager":
      return <FinancialManagerPage {...props} />;
    default:
      return null;
  }
}

function StockDataSourcesPage({ api, controlAvailable, settings }: PageProps) {
  const sources = useAsyncResource(() => api.stockDataSources(), [api]);
  const [form, setForm] = useState({ provider: "akshare", enabled: true, api_key: "", base_url: "" });
  const [result, setResult] = useState<unknown>(null);

  async function testSource() {
    setResult(await api.stockDataSourceTest(form));
  }

  async function saveSource() {
    setResult(await api.stockDataSourceSave(form));
    await sources.reload();
  }

  const rows = list(sources.data);
  return (
    <PageShell
      title="股票数据源配置与测试"
      description="统一管理 AKShare、Tushare、TDX、TQCenter 等数据源，只展示配置状态与脱敏结果。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="保存 / 测试数据源" />}
      metrics={[
        metric("数据源", rows.length, "info"),
        metric("Ready", rows.filter((item) => statusTone(item.status) === "success").length, "success"),
        metric("Missing", rows.filter((item) => statusTone(item.status) === "warning").length, "warning"),
        metric("模式", settings?.mode || "mock", settings?.mode === "mock" ? "warning" : "info")
      ]}
    >
      {settings?.mode === "mock" ? <MockDataNotice /> : null}
      <div className="grid-2">
        <Panel title="数据源列表">
          <DataTable
            items={rows}
            columns={[
              { key: "name", header: "来源" },
              { key: "configured", header: "已配置" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
              },
              { key: "secrets_redacted", header: "已脱敏" }
            ]}
          />
        </Panel>

        <Panel title="配置表单">
          <div className="form-grid">
            <label className="field">
              <span>Source</span>
              <select data-testid="stock-source-provider" value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })}>
                <option value="akshare">AKShare</option>
                <option value="tushare">Tushare</option>
                <option value="tdx">TDX</option>
                <option value="tqcenter">TQCenter</option>
              </select>
            </label>
            <label className="field">
              <span>Base URL / Path</span>
              <input data-testid="stock-source-base-url" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} />
            </label>
            <label className="field">
              <span>API Key</span>
              <input data-testid="stock-source-api-key" type="password" value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} />
            </label>
            <label className="field">
              <span>Enabled</span>
              <select value={String(form.enabled)} onChange={(event) => setForm({ ...form, enabled: event.target.value === "true" })}>
                <option value="true">enabled</option>
                <option value="false">disabled</option>
              </select>
            </label>
          </div>

          <div className="page-actions">
            <Button data-testid="stock-source-test" icon={<Play size={16} />} disabled={!controlAvailable} onClick={() => void testSource()}>
              测试
            </Button>
            <Button data-testid="stock-source-save" icon={<Save size={16} />} disabled={!controlAvailable} onClick={() => void saveSource()}>
              保存
            </Button>
          </div>
        </Panel>
      </div>

      <JsonPanel data={{ sources: sources.data, last_result: result }} title="数据源证据" />
    </PageShell>
  );
}

function DataSyncPage({ api }: PageProps) {
  const status = useAsyncResource(() => api.dataStatus(), [api]);
  const [codes, setCodes] = useState("600519,300750,000858");
  const [plan, setPlan] = useState<unknown>(null);
  const statusData = dataObject(status.data, {});
  const freshness = dataObject(statusData.freshness, {});
  const missing = Array.isArray(statusData.missing) ? statusData.missing : [];
  const stale = Array.isArray(statusData.stale) ? statusData.stale : [];

  async function createPlan() {
    setPlan(await api.dataSyncPlan({ codes, task_type: "preflight", dry_run: true }));
  }

  return (
    <PageShell
      title="数据状态与同步计划"
      description="总览数据库、freshness、缺失项与 dry-run 同步计划；真正执行仍受后端意图与控制策略约束。"
      metrics={[
        metric("Database", valueOf(dataObject(statusData.database, {}), ["status"]), statusTone(dataObject(statusData.database, {}).status)),
        metric("Freshness", freshness.status || "-", statusTone(freshness.status)),
        metric("Missing", missing.length, missing.length ? "warning" : "success"),
        metric("Stale", stale.length, stale.length ? "warning" : "success")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="数据状态" resource={status}>
          {(data) => <JsonPanel data={data} title="Data status payload" />}
        </ResourcePanel>

        <Panel title="同步计划">
          <label className="field">
            <span>股票代码</span>
            <textarea data-testid="data-sync-codes" value={codes} onChange={(event) => setCodes(event.target.value)} />
            <small>这里只生成计划，不直接写入数据；实际执行需要后端的 intent / control 门禁。</small>
          </label>
          <Button data-testid="data-sync-plan" icon={<RefreshCw size={16} />} onClick={() => void createPlan()}>
            生成同步计划
          </Button>
          {plan ? <JsonPanel data={plan} title="同步计划结果" /> : null}
        </Panel>
      </div>

      <Panel title="缺失与过期项">
        <DataTable
          items={[...missing.map((name) => ({ name, status: "missing" })), ...stale.map((name) => ({ name, status: "stale" }))]}
          columns={[
            { key: "name", header: "对象" },
            {
              key: "status",
              header: "状态",
              render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
            }
          ]}
        />
      </Panel>
    </PageShell>
  );
}

function FinanceLabPage({ api, workbench }: PageProps) {
  const dataStatus = useAsyncResource(() => api.dataStatus(), [api]);
  const radar = useAsyncResource(() => api.stockRadarStatus(), [api]);
  const broker = useAsyncResource(() => api.brokerReadiness(), [api]);
  const manager = useAsyncResource(() => api.financialManagerStatus(), [api]);
  const data = dataObject(dataStatus.data, {});
  const radarData = dataObject(radar.data, {});
  const brokerData = dataObject(broker.data, {});
  const managerData = dataObject(manager.data, {});

  return (
    <PageShell
      title="Finance Lab"
      description="按总览、数据、雷达、温度、量化、经理台六个分区组织金融工作面，并保持四工厂仅作为内部高级能力或重定向目标。"
      metrics={[
        metric("数据状态", valueOf(dataObject(data.database, {}), ["status"]), statusTone(dataObject(data.database, {}).status)),
        metric("雷达候选", radarData.candidate_count || "-", "success"),
        metric("经理台", managerData.ready ? "ready" : "degraded", managerData.ready ? "success" : "warning"),
        metric("券商", brokerData.read_only ? "read-only" : "blocked", brokerData.read_only ? "info" : "warning")
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/finance" title="总览" detail="承接金融研究总览、当前线程上下文与关键 readiness。" tone="info" />
        <LinkCard to="/stock-data-sources" title="数据" detail="数据源、同步计划、freshness 和缺失项。" tone="success" />
        <LinkCard to="/stock-radar" title="雷达" detail="候选股、摘要、受控动作与推送意图。" tone="warning" />
        <LinkCard to="/market-temperature" title="温度" detail="市场广度、行业冷热和 cache readiness。" />
        <LinkCard to="/quant-research" title="量化" detail="Preset、研究运行、报告与证据。" />
        <LinkCard to="/financial-manager" title="经理台" detail="只读查询、受控意图与券商只读信息。" tone="gated" />
      </div>

      <div className="grid-2">
        <Panel title="当前上下文">
          <JsonPanel
            data={{
              current_thread: workbench?.currentThread,
              current_run: workbench?.currentRun,
              data_status: dataStatus.data,
              radar: radar.data
            }}
            title="Finance lab context"
          />
        </Panel>
        <Panel title="产品边界">
          <p>四个延迟能力入口继续隐藏为直接产品入口，仅保留内部高级能力承接与兼容重定向。</p>
          <JsonPanel data={{ broker: broker.data, manager: manager.data }} title="Broker / Manager readiness" />
        </Panel>
      </div>
    </PageShell>
  );
}

function StockRadarPage({ api, controlAvailable }: PageProps) {
  const status = useAsyncResource(() => api.stockRadarStatus(), [api]);
  const candidates = useAsyncResource(() => api.stockRadarCandidates(), [api]);
  const digest = useAsyncResource(() => api.stockRadarDigest(), [api]);
  const candidateRows = firstArray(dataObject(candidates.data, {}), ["candidates", "data"]);
  const statusData = dataObject(status.data, {});
  const digestData = dataObject(digest.data, {});
  const [actionResult, setActionResult] = useState<unknown>(null);

  async function createRadarIntent(action: "run" | "deliver") {
    setActionResult(
      await api.createIntent({
        action: action === "run" ? "stock_radar.run_once" : "stock_radar.push_digest",
        params: {
          run_id: statusData.latest_run_id,
          channels: action === "deliver" ? ["local"] : undefined,
          dry_run: true
        },
        rationale: `Desktop V1 stock radar ${action} intent`
      })
    );
  }

  return (
    <PageShell
      title="Stock Radar"
      description="独立承接股票发现、候选池、摘要、风险说明和受控动作意图。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="运行 / 推送雷达意图" />}
      metrics={[
        metric("最新运行", statusData.latest_run_id || "-", "info"),
        metric("候选数", candidateRows.length || statusData.candidate_count || 0, "success"),
        metric("摘要", digestData.digest ? "ready" : "empty", digestData.digest ? "success" : "warning"),
        metric("投递", digestData.delivery_intent_required ? "intent" : "read-only", digestData.delivery_intent_required ? "gated" : "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="候选股">
          <DataTable
            items={candidateRows}
            columns={[
              { key: "symbol", header: "代码" },
              { key: "name", header: "名称" },
              { key: "tier", header: "层级" },
              { key: "score", header: "分数" },
              { key: "risk", header: "风险" }
            ]}
            empty="暂无候选股"
          />
        </Panel>

        <Panel title="摘要与动作">
          {digestData.digest ? <p>{String(digestData.digest)}</p> : <EmptyState title="暂无摘要" detail="等待雷达 digest 或 live Agent 返回。" />}
          <div className="page-actions">
            <Button data-testid="stock-radar-run-intent" icon={<Play size={16} />} disabled={!controlAvailable} onClick={() => void createRadarIntent("run")}>
              创建运行意图
            </Button>
            <Button data-testid="stock-radar-deliver-intent" icon={<ShieldAlert size={16} />} disabled={!controlAvailable} onClick={() => void createRadarIntent("deliver")}>
              创建投递意图
            </Button>
          </div>
          {actionResult ? <JsonPanel data={actionResult} title="Radar intent result" /> : null}
        </Panel>
      </div>

      <JsonPanel data={{ status: status.data, candidates: candidates.data, digest: digest.data }} title="Stock radar evidence" />
    </PageShell>
  );
}

function MarketTemperaturePage({ api }: PageProps) {
  const snapshot = useAsyncResource(() => api.marketTemperatureSnapshot(), [api]);
  const readiness = useAsyncResource(() => api.marketTemperatureReadiness(), [api]);
  const snapshotData = dataObject(snapshot.data, {});
  const readinessData = dataObject(readiness.data, {});
  const market = dataObject(snapshotData.market, {});
  const hot = firstArray(snapshotData, ["hot_industries"]);
  const cold = firstArray(snapshotData, ["cold_industries"]);

  return (
    <PageShell
      title="Market Temperature"
      description="通过 `agent_market_temperature_*` 只读工具展示市场广度、行业冷热、缓存新鲜度与诊断信息。"
      metrics={[
        metric("温度", market.temperature || "-", statusTone(market.state)),
        metric("状态", market.state || "-", statusTone(market.state)),
        metric("样本", market.sample_count || "-", "info"),
        metric("缓存", readinessData.status || readinessData.ready || "-", statusTone(readinessData.status || readinessData.ready))
      ]}
    >
      <div className="grid-2">
        <Panel title="热门行业">
          <DataTable items={hot} columns={[{ key: "industry", header: "行业" }, { key: "temperature", header: "温度" }, { key: "breadth", header: "广度" }]} />
        </Panel>
        <Panel title="低温行业">
          <DataTable items={cold} columns={[{ key: "industry", header: "行业" }, { key: "temperature", header: "温度" }, { key: "breadth", header: "广度" }]} />
        </Panel>
      </div>

      <JsonPanel data={{ snapshot: snapshot.data, readiness: readiness.data }} title="Market temperature evidence" />
    </PageShell>
  );
}

function QuantResearchPage({ api }: PageProps) {
  const presets = useAsyncResource(() => api.quantPresets(), [api]);
  const [preset, setPreset] = useState("momentum_research");
  const [symbol, setSymbol] = useState("600519");
  const [run, setRun] = useState<unknown>(null);
  const [report, setReport] = useState<unknown>(null);
  const rows = list(presets.data);

  async function createRun() {
    const result = await api.quantRun({ preset, universe: [symbol], dry_run: true, source: "desktop_v1" });
    setRun(result);
    setReport(null);
  }

  async function loadReport() {
    const runData = dataObject(run, {});
    const inner = dataObject(runData.data || runData, {});
    const research = dataObject(inner.research, {});
    const researchId = String(research.research_id || research.id || inner.id || inner.research_id || runData.id || "");
    if (!researchId) return;
    setReport(await api.quantReport(researchId));
  }

  const runData = dataObject(run, {});
  const runInner = dataObject(runData.data || runData, {});
  return (
    <PageShell
      title="Quant Research"
      description="用 preset、参数、研究运行与报告构成量化分区，保持 dry-run 与证据链清晰可见。"
      metrics={[
        metric("Presets", rows.length, "success"),
        metric("当前 preset", preset, "info"),
        metric("运行状态", runInner.status || "未运行", statusTone(runInner.status)),
        metric("报告", run ? "ready" : "pending", run ? "success" : "warning")
      ]}
    >
      <div className="grid-2">
        <Panel title="研究参数">
          <div className="form-grid">
            <label className="field">
              <span>Preset</span>
              <select data-testid="quant-preset" value={preset} onChange={(event) => setPreset(event.target.value)}>
                {rows.map((item) => (
                  <option value={String(item.id || item.name)} key={String(item.id || item.name)}>
                    {String(item.name || item.id)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Symbol</span>
              <input data-testid="quant-symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
            </label>
          </div>
          <div className="page-actions">
            <Button data-testid="quant-create-run" icon={<Play size={16} />} onClick={() => void createRun()}>
              创建研究运行
            </Button>
            <Button data-testid="quant-load-report" disabled={!run} onClick={() => void loadReport()}>
              Load report
            </Button>
          </div>
        </Panel>

        <Panel title="Preset 列表">
          <DataTable items={rows} columns={[{ key: "name", header: "名称" }, { key: "risk", header: "风险" }, { key: "default_universe", header: "默认范围" }]} />
        </Panel>
      </div>

      {run ? <JsonPanel data={{ run, report }} title="研究报告 / 运行证据" /> : null}
    </PageShell>
  );
}

function FinancialManagerPage({ api, controlAvailable }: PageProps) {
  const catalog = useAsyncResource(() => api.financialManagerCatalog(), [api]);
  const status = useAsyncResource(() => api.financialManagerStatus(), [api]);
  const broker = useAsyncResource(() => api.brokerReadiness(), [api]);
  const accounts = useAsyncResource(() => api.brokerAccounts(), [api]);
  const positions = useAsyncResource(() => api.brokerPositions(), [api]);
  const orders = useAsyncResource(() => api.brokerOrders(), [api]);
  const [query, setQuery] = useState("请复核当前组合风险，只返回只读分析。");
  const [result, setResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "intent" | "broker-run">(null);
  const statusData = dataObject(status.data, {});
  const brokerData = dataObject(broker.data, {});

  async function runQuery() {
    setResult(
      await api.financialManagerQuery({
        capability_id: "portfolio",
        action_id: "risk",
        params: { codes: ["600519", "000001"], weights: [0.6, 0.4], query },
        read_only: true
      })
    );
  }

  async function createIntent() {
    setResult(
      await api.financialManagerIntent({
        capability_id: "portfolio",
        action_id: "create",
        params: { name: "Desktop V1 dry-run book" },
        rationale: query
      })
    );
    setPreviewAction(null);
  }

  async function runBrokerAnalytics() {
    setResult(await api.brokerAnalyticsRun({ dry_run: true, source: "desktop_v1", read_only: true }));
    setPreviewAction(null);
  }

  async function loadBrokerAnalytics() {
    setResult(await api.brokerAnalyticsLatest());
  }

  return (
    <PageShell
      title="Financial Manager / Broker 只读"
      description="统一承接 manager catalog、status、只读 query、受控 intent 与 broker 只读信息，不暴露交易按钮。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="受控金融意图" />}
      metrics={[
        metric("Manager", statusData.ready ? "ready" : "degraded", statusData.ready ? "success" : "warning"),
        metric("Broker", brokerData.read_only ? "read-only" : "blocked", brokerData.read_only ? "info" : "warning"),
        metric("Live Trading", brokerData.live_trading_enabled ? "enabled" : "disabled", brokerData.live_trading_enabled ? "danger" : "success"),
        metric("Catalog", list(catalog.data).length, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="只读查询">
          <label className="field">
            <span>查询</span>
            <textarea data-testid="financial-query" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="page-actions">
            <Button data-testid="financial-run-query" icon={<Search size={16} />} onClick={() => void runQuery()}>
              运行只读查询
            </Button>
            <Button data-testid="financial-create-intent" icon={<ShieldAlert size={16} />} disabled={!controlAvailable} onClick={() => setPreviewAction("intent")}>
              创建受控意图
            </Button>
            <Button data-testid="broker-analytics-run" disabled={!controlAvailable} onClick={() => setPreviewAction("broker-run")}>
              Broker analytics dry-run
            </Button>
            <Button data-testid="broker-analytics-latest" disabled={!controlAvailable} onClick={() => void loadBrokerAnalytics()}>
              Latest broker analytics
            </Button>
          </div>

          {previewAction ? (
            <DryRunPreview
              title={previewAction === "intent" ? "金融意图预览" : "Broker analytics dry-run 预览"}
              changes={[
                { label: "动作", after: previewAction === "intent" ? "portfolio_manager.create" : "broker.analytics.run" },
                { label: "模式", after: "read-only / dry-run" },
                { label: "说明", after: query }
              ]}
              onCancel={() => setPreviewAction(null)}
              onConfirm={() => void (previewAction === "intent" ? createIntent() : runBrokerAnalytics())}
            />
          ) : null}
        </Panel>

        <Panel title="Catalog">
          <DataTable items={list(catalog.data)} columns={[{ key: "name", header: "能力" }, { key: "side_effect", header: "副作用" }]} />
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title="账户">
          <DataTable items={list(accounts.data)} columns={[{ key: "provider", header: "Provider" }, { key: "account_id", header: "账户" }, { key: "read_only", header: "只读" }]} />
        </Panel>
        <Panel title="持仓">
          <DataTable items={list(positions.data)} columns={[{ key: "symbol", header: "代码" }, { key: "quantity", header: "数量" }, { key: "market_value", header: "市值" }]} />
        </Panel>
        <Panel title="订单只读">
          <DataTable items={list(orders.data)} columns={[{ key: "id", header: "订单" }, { key: "symbol", header: "代码" }, { key: "status", header: "状态" }]} />
        </Panel>
      </div>

      <JsonPanel data={{ status: status.data, broker: broker.data, result }} title="Financial manager evidence" />
    </PageShell>
  );
}
