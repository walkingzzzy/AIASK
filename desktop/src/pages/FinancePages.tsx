import { Play, RefreshCw, Save, Search, ShieldAlert } from "lucide-react";
import { useState } from "react";

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

function StockDataSourcesPage({ api, controlAvailable }: PageProps) {
  const sources = useAsyncResource(() => api.stockDataSources(), [api]);
  const [form, setForm] = useState({ name: "tushare", enabled: true, api_key: "", base_url: "" });
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
      description="配置 AKShare、Tushare、TDX、TQCenter 等来源；secret 只显示配置状态，不回显原值。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="保存/测试数据源" />}
      metrics={[
        metric("数据源", rows.length, "info"),
        metric("Ready", rows.filter((item) => statusTone(item.status) === "success").length, "success"),
        metric("Missing", rows.filter((item) => statusTone(item.status) === "warning").length, "warning"),
        metric("Secrets", "Redacted", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="数据源列表">
          <DataTable
            items={rows}
            columns={[
              { key: "name", header: "来源" },
              { key: "configured", header: "配置" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> },
              { key: "secrets_redacted", header: "脱敏" }
            ]}
          />
        </Panel>
        <Panel title="配置表单">
          <div className="form-grid">
            <label className="field">
              <span>Source</span>
              <select value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })}>
                <option value="akshare">AKShare</option>
                <option value="tushare">Tushare</option>
                <option value="tdx">TDX</option>
                <option value="tqcenter">TQCenter</option>
              </select>
            </label>
            <label className="field">
              <span>Base URL / Path</span>
              <input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} />
            </label>
            <label className="field">
              <span>API Key</span>
              <input type="password" value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} />
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
            <Button icon={<Play size={16} />} disabled={!controlAvailable} onClick={() => void testSource()}>
              测试
            </Button>
            <Button icon={<Save size={16} />} disabled={!controlAvailable} onClick={() => void saveSource()}>
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
      title="数据库状态与数据同步"
      description="展示本地数据库、新鲜度、缺失项、同步计划和受控执行入口；同步计划先 dry-run/intent，不直接越权执行。"
      metrics={[
        metric("Database", valueOf(dataObject(statusData.database, {}), ["status"]), statusTone(dataObject(statusData.database, {}).status)),
        metric("Freshness", freshness.status || "-", statusTone(freshness.status)),
        metric("Missing", missing.length, missing.length ? "warning" : "success"),
        metric("Stale", stale.length, stale.length ? "warning" : "success")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="数据状态" resource={status}>
          {(data) => <JsonPanel data={data} title="数据状态 payload" />}
        </ResourcePanel>
        <Panel title="同步计划">
          <label className="field">
            <span>股票代码</span>
            <textarea value={codes} onChange={(event) => setCodes(event.target.value)} />
            <small>计划生成不会直接同步；执行需要后端 intent/control 策略。</small>
          </label>
          <Button icon={<RefreshCw size={16} />} onClick={() => void createPlan()}>
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
            { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }
          ]}
        />
      </Panel>
    </PageShell>
  );
}

function FinanceLabPage({ api }: PageProps) {
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
      title="金融工作台"
      description="V1 金融枢纽，只展示数据、雷达、市场、量化、经理台、券商只读和自动化工作流。"
      metrics={[
        metric("数据", valueOf(dataObject(data.database, {}), ["status"]), statusTone(dataObject(data.database, {}).status)),
        metric("雷达候选", radarData.candidate_count || "-", "success"),
        metric("经理台", managerData.ready ? "ready" : "degraded", managerData.ready ? "success" : "warning"),
        metric("券商", brokerData.read_only ? "read-only" : "blocked", brokerData.read_only ? "info" : "warning")
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/data-sync" title="Data & Sync" detail="数据库状态、新鲜度、缺失项和同步计划。" tone="info" />
        <LinkCard to="/stock-radar" title="Stock Radar" detail="候选、摘要、运行/推送/调度意图。" tone="success" />
        <LinkCard to="/market-temperature" title="Market Temperature" detail="市场广度、行业冷热和缓存验证。" tone="warning" />
        <LinkCard to="/quant-research" title="Quant Research" detail="Preset、研究运行、报告和证据链。" />
        <LinkCard to="/financial-manager" title="Financial Manager" detail="查询、意图、券商只读和风险标注。" tone="gated" />
        <LinkCard to="/workflows" title="Automation / Workflows" detail="V1 金融研究流程和调度入口。" />
      </div>
      <div className="grid-2">
        <Panel title="券商只读状态">
          <JsonPanel data={broker.data} title="Broker readiness" />
        </Panel>
        <Panel title="金融摘要">
          <JsonPanel data={{ data_status: dataStatus.data, radar: radar.data, manager: manager.data }} title="摘要证据" />
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

  return (
    <PageShell
      title="股票雷达"
      description="独立股票发现入口：状态、候选、摘要、运行意图、推送意图和调度意图。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="运行/推送/调度意图" />}
      metrics={[
        metric("最新运行", statusData.latest_run_id || "-", "info"),
        metric("候选", candidateRows.length || statusData.candidate_count || 0, "success"),
        metric("摘要", digestData.digest ? "ready" : "empty", digestData.digest ? "success" : "warning"),
        metric("投递", digestData.delivery_intent_required ? "intent" : "read-only", digestData.delivery_intent_required ? "gated" : "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="候选股票">
          <DataTable
            items={candidateRows}
            columns={[
              { key: "symbol", header: "代码" },
              { key: "name", header: "名称" },
              { key: "tier", header: "层级" },
              { key: "score", header: "分数" },
              { key: "risk", header: "风险" }
            ]}
          />
        </Panel>
        <Panel title="摘要与动作">
          {digestData.digest ? <p>{String(digestData.digest)}</p> : <EmptyState title="暂无摘要" detail="等待雷达 digest 或 live Agent 返回。" />}
          <div className="page-actions">
            <Button icon={<Play size={16} />} disabled={!controlAvailable}>
              创建运行意图
            </Button>
            <Button icon={<ShieldAlert size={16} />} disabled={!controlAvailable}>
              创建投递意图
            </Button>
          </div>
        </Panel>
      </div>
      <JsonPanel data={{ status: status.data, candidates: candidates.data, digest: digest.data }} title="股票雷达证据" />
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
      title="热力图与市场温度"
      description="通过 agent_market_temperature_* 只读工具展示市场广度、行业冷热、缓存新鲜度和验证信息。"
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
      <JsonPanel data={{ snapshot: snapshot.data, readiness: readiness.data }} title="市场温度证据" />
    </PageShell>
  );
}

function QuantResearchPage({ api }: PageProps) {
  const presets = useAsyncResource(() => api.quantPresets(), [api]);
  const [preset, setPreset] = useState("momentum_research");
  const [symbol, setSymbol] = useState("600519");
  const [run, setRun] = useState<unknown>(null);
  const rows = list(presets.data);

  async function createRun() {
    setRun(await api.quantRun({ preset, universe: [symbol], dry_run: true, source: "desktop_v1" }));
  }

  const runData = dataObject(run, {});
  const runInner = dataObject(runData.data || runData, {});
  return (
    <PageShell
      title="量化研究与报告"
      description="选择 preset、参数、数据门禁后创建研究运行；报告展示指标、表格、限制和来源链。"
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
              <select value={preset} onChange={(event) => setPreset(event.target.value)}>
                {rows.map((item) => (
                  <option value={String(item.id || item.name)} key={String(item.id || item.name)}>
                    {String(item.name || item.id)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Symbol</span>
              <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
            </label>
          </div>
          <Button icon={<Play size={16} />} onClick={() => void createRun()}>
            创建研究运行
          </Button>
        </Panel>
        <Panel title="Preset 列表">
          <DataTable items={rows} columns={[{ key: "name", header: "名称" }, { key: "risk", header: "风险" }, { key: "default_universe", header: "默认范围" }]} />
        </Panel>
      </div>
      {run ? <JsonPanel data={run} title="研究报告/运行证据" /> : null}
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
  const [query, setQuery] = useState("复核当前组合风险，只返回只读分析。");
  const [result, setResult] = useState<unknown>(null);
  const statusData = dataObject(status.data, {});
  const brokerData = dataObject(broker.data, {});

  async function runQuery() {
    setResult(await api.financialManagerQuery({ query, read_only: true }));
  }

  async function createIntent() {
    setResult(await api.financialManagerIntent({ action: "review", query, dry_run: true }));
  }

  return (
    <PageShell
      title="Financial Manager 与 Broker 只读"
      description="金融经理台提供 catalog、status、query 和受控 intent；券商能力 V1 只读，不提供下单/撤单按钮。"
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
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="page-actions">
            <Button icon={<Search size={16} />} onClick={() => void runQuery()}>
              运行只读查询
            </Button>
            <Button icon={<ShieldAlert size={16} />} disabled={!controlAvailable} onClick={() => void createIntent()}>
              创建受控意图
            </Button>
          </div>
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
      <JsonPanel data={{ status: status.data, broker: broker.data, result }} title="经理台证据" />
    </PageShell>
  );
}
