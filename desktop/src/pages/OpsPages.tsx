import { Play, Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { DryRunPreview } from "../components/IntentComponents";
import { StatusLight, inferStatusFromData } from "../components/StatusLight";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, GatedNotice, JsonPanel, LinkCard, PageShell, Panel } from "../components/ui";
import type { ConnectionSettings, UnknownRecord } from "../types";
import { dataObject, firstArray, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";
import { viewToRoute } from "../routes";

function compactValue(value: unknown, fallback = "-") {
  if (value === true) return "yes";
  if (value === false) return "no";
  if (value === undefined || value === null || value === "") return fallback;
  if (Array.isArray(value)) return value.length ? value.join(", ") : fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function SummaryFields({ items }: { items: { label: string; value: unknown; tone?: "muted" | "strong" }[] }) {
  return (
    <div className="form-grid factory-summary-grid">
      {items.map((item) => (
        <div className="field factory-summary-field" key={item.label}>
          <span>{item.label}</span>
          <strong className={item.tone === "muted" ? "muted-value" : undefined}>{compactValue(item.value)}</strong>
        </div>
      ))}
    </div>
  );
}


export function OpsPages(props: PageProps) {
  switch (props.view) {
    case "automation":
      return <AutomationPage {...props} />;
    case "workflows":
      return <WorkflowsPage {...props} />;
    case "settings-security":
      return <SettingsSecurityPage {...props} />;
    case "readiness-health":
      return <ReadinessHealthPage {...props} />;
    case "local-user-memory":
      return <LocalUserMemoryPage {...props} />;
    case "learning-rl":
      return <LearningRlPage {...props} />;
    case "native-diagnostics":
      return <NativeDiagnosticsPage {...props} />;
    default:
      return null;
  }
}

function gatedListPayload(area: string): UnknownRecord {
  return {
    object: "list",
    data: [],
    gated: true,
    status: "control_required",
    error_code: "control_token_required",
    message: `${area} requires a control token`
  };
}

function gatedStatusPayload(area: string): UnknownRecord {
  return {
    object: "gated.status",
    gated: true,
    status: "control_required",
    error_code: "control_token_required",
    message: `${area} requires a control token`
  };
}

function useControlGatedResource<T>(controlAvailable: boolean, loader: () => Promise<T>, fallback: T, deps: unknown[] = []) {
  return useAsyncResource(() => (controlAvailable ? loader() : Promise.resolve(fallback)), [controlAvailable, ...deps]);
}

function primitiveText(value: unknown): string | null {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    const text = String(value).trim();
    return text ? text : null;
  }
  return null;
}

function readableActionText(action: unknown, index: number) {
  const direct = primitiveText(action);
  if (direct) return direct;
  const record = dataObject(action, {});
  for (const key of ["title", "name", "label", "action", "message", "detail", "description"]) {
    const text = primitiveText(record[key]);
    if (text) return text;
  }
  return `建议 ${index + 1}`;
}

function AutomationPage({ api, controlAvailable }: PageProps) {
  const jobs = useAsyncResource(() => api.jobs(), [api]);
  const [result, setResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "create" | "run" | "toggle" | "delete">(null);
  const [targetJob, setTargetJob] = useState<Record<string, unknown> | null>(null);
  const [form, setForm] = useState({
    name: "",
    prompt: "",
    schedule: "interval",
    interval_seconds: "3600",
    enabled: true,
    template: "generic",
    symbol: "600519",
    query: "",
    condition: "price_change_pct > 3",
    channel: "local",
    dry_run: true
  });
  const rows = list(jobs.data);
  const enabledRows = rows.filter((job) => Boolean(job.enabled));
  const scheduledRows = rows.filter((job) => !String(job.schedule || "").includes("manual"));
  const manualRows = rows.filter((job) => String(job.schedule || "").includes("manual"));

  function jobId(job: Record<string, unknown> | undefined | null) {
    return String(job?.id || job?.job_id || "");
  }

  function jobName(job: Record<string, unknown> | undefined | null) {
    return String(job?.name || job?.id || job?.job_id || "job");
  }

  function buildPayload() {
    const isWatch = form.template === "watch";
    const interval = Number(form.interval_seconds || 0);
    return {
      name: form.name.trim() || (isWatch ? `Watch ${form.symbol || form.query}` : "Desktop automation job"),
      prompt: isWatch
        ? `Watch ${form.symbol || form.query}: ${form.condition}. Notify ${form.channel}. Dry run: ${form.dry_run}.`
        : form.prompt.trim(),
      schedule: form.schedule,
      interval_seconds: form.schedule === "interval" && Number.isFinite(interval) && interval > 0 ? interval : undefined,
      enabled: form.enabled,
      dry_run: form.dry_run,
      source: "desktop_v1",
      template: isWatch ? "market_watch" : "generic_prompt",
      watch: isWatch
        ? {
            symbol: form.symbol.trim(),
            query: form.query.trim(),
            condition: form.condition.trim(),
            channel: form.channel,
            dry_run: form.dry_run
          }
        : undefined
    };
  }

  async function createJobFromForm() {
    setResult(await api.createJob(buildPayload()));
    setPreviewAction(null);
    await jobs.reload();
  }

  async function runJob(job: Record<string, unknown>) {
    const targetId = jobId(job);
    if (!targetId) return;
    setResult(await api.runJob(targetId));
    setPreviewAction(null);
    await jobs.reload();
  }

  async function toggleJob(job: Record<string, unknown>) {
    const targetId = jobId(job);
    if (!targetId) return;
    setResult(await api.updateJob(targetId, { enabled: !Boolean(job.enabled) }));
    setPreviewAction(null);
    await jobs.reload();
  }

  async function deleteJob(job: Record<string, unknown>) {
    const targetId = jobId(job);
    if (!targetId) return;
    setResult(await api.deleteJob(targetId));
    setPreviewAction(null);
    await jobs.reload();
  }

  function openJobPreview(action: "run" | "toggle" | "delete", job: Record<string, unknown>) {
    setTargetJob(job);
    setPreviewAction(action);
  }

  const previewChanges =
    previewAction === "create"
      ? [
          { label: "操作", after: "创建作业" },
          { label: "名称", after: String(buildPayload().name) },
          { label: "模板", after: String(buildPayload().template) },
          { label: "控制方式", after: "通过 Agent /v1/jobs 和控制权限门禁执行" }
        ]
      : [
          { label: "操作", after: String(previewAction || "") },
          { label: "目标", after: jobName(targetJob) },
          { label: "控制方式", after: "通过 Agent 作业 API 受控路由执行" }
        ];

  return (
    <PageShell
      title="自动化"
      description="通过明确表单和预览创建、运行、停用或删除受控 Agent 作业。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建或运行作业" />}
      metrics={[
        metric("作业", rows.length, "info"),
        metric("已启用", enabledRows.length, "success"),
        metric("已排程", scheduledRows.length, "info"),
        metric("手动", manualRows.length, "warning")
      ]}
    >
      <div className="grid-2">
        <Panel title="创建作业">
          <div className="form-grid">
            <label className="field">
              <span>模板</span>
              <select data-testid="job-template" value={form.template} onChange={(event) => setForm({ ...form, template: event.target.value })}>
                <option value="generic">提示词作业</option>
                <option value="watch">市场监控</option>
              </select>
            </label>
            <label className="field">
              <span>名称</span>
              <input data-testid="job-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="每日市场简报" />
            </label>
            <label className="field">
              <span>排程</span>
              <select value={form.schedule} onChange={(event) => setForm({ ...form, schedule: event.target.value })}>
                <option value="interval">按间隔执行</option>
                <option value="manual">手动执行</option>
              </select>
            </label>
            <label className="field">
              <span>间隔秒数</span>
              <input data-testid="job-interval" type="number" min="60" value={form.interval_seconds} onChange={(event) => setForm({ ...form, interval_seconds: event.target.value })} disabled={form.schedule === "manual"} />
            </label>
            {form.template === "watch" ? (
              <>
                <label className="field">
                  <span>股票代码</span>
                  <input data-testid="job-watch-symbol" value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value })} />
                </label>
                <label className="field">
                  <span>主题</span>
                  <input value={form.query} onChange={(event) => setForm({ ...form, query: event.target.value })} placeholder="可选主题" />
                </label>
                <label className="field">
                  <span>触发条件</span>
                  <input data-testid="job-watch-condition" value={form.condition} onChange={(event) => setForm({ ...form, condition: event.target.value })} />
                </label>
                <label className="field">
                  <span>通知渠道</span>
                  <select value={form.channel} onChange={(event) => setForm({ ...form, channel: event.target.value })}>
                    <option value="local">本地</option>
                    <option value="feishu">飞书</option>
                    <option value="wecom">企业微信</option>
                    <option value="discord">Discord</option>
                  </select>
                </label>
              </>
            ) : (
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>提示词</span>
                <textarea data-testid="job-prompt" value={form.prompt} onChange={(event) => setForm({ ...form, prompt: event.target.value })} rows={4} />
              </label>
            )}
            <label className="field">
              <span>启用</span>
              <input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />
            </label>
            <label className="field">
              <span>只预演</span>
              <input type="checkbox" checked={form.dry_run} onChange={(event) => setForm({ ...form, dry_run: event.target.checked })} />
            </label>
          </div>
          <div className="page-actions">
            <Button data-testid="job-create" icon={<Save size={16} />} tone="success" disabled={!controlAvailable} onClick={() => setPreviewAction("create")}>
              预览创建
            </Button>
          </div>
        </Panel>

        <Panel title="作业检查">
          <JsonPanel
            data={{
              jobs: rows,
              enabled_count: enabledRows.length,
              scheduled_count: scheduledRows.length,
              manual_count: manualRows.length,
              form_payload: buildPayload()
            }}
            title="自动化检查"
          />
        </Panel>
      </div>

      <Panel title="作业">
        <DataTable
          items={rows}
          columns={[
            { key: "name", header: "Job" },
            { key: "enabled", header: "启用状态" },
            { key: "schedule", header: "Schedule" },
            { key: "toolset", header: "Toolset" },
            {
              key: "id",
              header: "操作",
              render: (job) => (
                <div className="page-actions">
                  <Button data-testid={`job-run-${jobId(job)}`} icon={<Play size={14} />} disabled={!controlAvailable} onClick={() => openJobPreview("run", job)}>
                    运行
                  </Button>
                  <Button data-testid={`job-toggle-${jobId(job)}`} icon={<ShieldCheck size={14} />} disabled={!controlAvailable} onClick={() => openJobPreview("toggle", job)}>
                    {job.enabled ? "停用" : "启用"}
                  </Button>
                  <Button data-testid={`job-delete-${jobId(job)}`} tone="danger" disabled={!controlAvailable} onClick={() => openJobPreview("delete", job)}>
                    删除
                  </Button>
                </div>
              )
            }
          ]}
        />
      </Panel>

      {previewAction ? (
        <DryRunPreview
          title="自动化操作预览"
          changes={previewChanges}
          onCancel={() => {
            setPreviewAction(null);
            setTargetJob(null);
          }}
          onConfirm={() => {
            if (previewAction === "create") {
              void createJobFromForm();
              return;
            }
            if (!targetJob) return;
            if (previewAction === "run") {
              void runJob(targetJob);
              return;
            }
            if (previewAction === "toggle") {
              void toggleJob(targetJob);
              return;
            }
            void deleteJob(targetJob);
          }}
        />
      ) : null}

      <JsonPanel data={{ jobs: jobs.data, last_result: result }} title="自动化证据" />
    </PageShell>
  );
}

function WorkflowsPage(_props: PageProps) {
  const steps = [
    { name: "Data", detail: "数据源、状态、freshness 与同步计划。", to: "/data-sync", tone: "info" as const },
    { name: "Radar", detail: "候选股、摘要和受控投递意图。", to: "/stock-radar", tone: "success" as const },
    { name: "Market", detail: "市场温度、行业冷热与 cache readiness。", to: "/market-temperature", tone: "warning" as const },
    { name: "Quant", detail: "Preset、研究运行、报告与限制说明。", to: "/quant-research", tone: "neutral" as const },
    { name: "Manager", detail: "经理台只读查询和受控意图。", to: "/financial-manager", tone: "gated" as const },
    { name: "Gateway", detail: "投递预览、目录、消息与 Webhooks。", to: "/gateway-webhooks", tone: "neutral" as const }
  ];

  return (
    <PageShell
      title="Workflow Map"
      description="展示 Data -> Radar -> Market -> Quant -> Manager -> Gateway 的端到端编排路径。"
      metrics={[
        metric("流程节点", steps.length, "info"),
        metric("副作用动作", "Intent / Approval", "gated"),
        metric("实盘交易", "未开放", "success"),
        metric("后续能力", "Deferred", "success")
      ]}
    >
      <div className="workflow-map">
        {steps.map((step, index) => (
          <div className="workflow-step" key={step.name}>
            <span>Step {index + 1}</span>
            <strong>{step.name}</strong>
            <p>{step.detail}</p>
          </div>
        ))}
      </div>

      <div className="grid-3">
        {steps.map((step) => (
          <LinkCard key={step.name} to={step.to} title={step.name} detail={step.detail} tone={step.tone} />
        ))}
      </div>
    </PageShell>
  );
}

function SettingsSecurityPage({ settings, updateSettings, controlAvailable }: PageProps) {
  const [local, setLocal] = useState<ConnectionSettings>(
    settings || { baseUrl: "http://127.0.0.1:8765", apiToken: "", controlToken: "", mode: "mock", userId: "local-user" }
  );

  function save() {
    updateSettings?.(local);
  }

  return (
    <PageShell
      title="设置"
      description="集中管理 Agent HTTP base、API token、control token、mock / live 模式和用户上下文，保留 secret 脱敏。"
      badge={<StatusLight status={controlAvailable ? "connected" : "disconnected"} label={controlAvailable ? "控制权限已输入" : "控制权限缺失"} />}
      metrics={[
        metric("模式", local.mode === "mock" ? "演示" : "真实", local.mode === "mock" ? "warning" : "info"),
        metric("API Token", local.apiToken ? "已输入" : "空", local.apiToken ? "success" : "warning"),
        metric("控制权限", local.controlToken ? "已输入" : "空", local.controlToken ? "success" : "gated"),
        metric("用户", local.userId, "info")
      ]}
    >
      <Panel title="连接设置">
        <div className="form-grid">
          <label className="field">
            <span>Agent 服务地址</span>
            <input value={local.baseUrl} onChange={(event) => setLocal({ ...local, baseUrl: event.target.value })} />
          </label>
          <label className="field">
            <span>模式</span>
            <select value={local.mode} onChange={(event) => setLocal({ ...local, mode: event.target.value as ConnectionSettings["mode"] })}>
              <option value="mock">演示</option>
              <option value="live">真实</option>
            </select>
          </label>
          <label className="field">
            <span>API 令牌</span>
            <input type="password" value={local.apiToken} onChange={(event) => setLocal({ ...local, apiToken: event.target.value })} />
          </label>
          <label className="field">
            <span>控制权限令牌</span>
            <input type="password" value={local.controlToken} onChange={(event) => setLocal({ ...local, controlToken: event.target.value })} />
          </label>
          <label className="field">
            <span>用户 ID</span>
            <input value={local.userId} onChange={(event) => setLocal({ ...local, userId: event.target.value })} />
          </label>
        </div>
        <Button icon={<Save size={16} />} tone="success" onClick={save}>
          保存设置
        </Button>
      </Panel>

      <Panel title="安全矩阵">
        <DataTable
          items={[
            { area: "Desktop boundary", rule: "仅通过 Agent HTTP", status: "enforced" },
            { area: "Secrets", rule: "页面 / JSON 脱敏", status: "enforced" },
            { area: "Side effects", rule: "Intent / Approval / control token", status: controlAvailable ? "ready" : "gated" },
            { area: "实盘交易", rule: "V1 不开放", status: "blocked" }
          ]}
          columns={[
            { key: "area", header: "区域" },
            { key: "rule", header: "规则" },
            { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
          ]}
        />
      </Panel>
    </PageShell>
  );
}

function ReadinessHealthPage({ api, controlAvailable }: PageProps) {
  const health = useAsyncResource(() => api.healthDetailed(), [api]);
  const hermes = useAsyncResource(() => api.hermesReadiness(), [api]);
  const financial = useAsyncResource(() => api.financialReadiness(), [api]);
  const capabilities = useAsyncResource(() => api.capabilities(), [api]);
  const parity = useAsyncResource(() => api.parity(), [api]);
  const factoryFormal = useAsyncResource(() => api.strategyFactoryFormalDiagnostics(15), [api]);
  const intents = useAsyncResource(() => api.intents(), [api]);
  const [opsResult, setOpsResult] = useState<unknown>(null);
  const [opsBusy, setOpsBusy] = useState(false);
  const [previewAction, setPreviewAction] = useState<null | "dry_run" | "run_once" | "maintenance" | "factor_run">(null);
  const healthData = dataObject(health.data, {});
  const financialData = dataObject(financial.data, {});
  const requiredGates = firstArray(financialData, ["required_gates"]);
  const optionalGates = firstArray(financialData, ["optional_gates"]);
  const nextActions = Array.isArray(financialData.next_actions)
    ? financialData.next_actions.map((action, index) => ({ id: `action-${index}`, name: readableActionText(action, index) }))
    : [];
  // Prefer dedicated diagnostics tool; fall back to readiness embed.
  const factoryDiagRaw = dataObject(factoryFormal.data, {});
  const factoryDiagFromTool = dataObject(factoryDiagRaw.data || factoryDiagRaw, {});
  const factoryDiag =
    factoryDiagFromTool.object === "aiask.factory_formal_diagnostics" || factoryDiagFromTool.formal_count != null
      ? factoryDiagFromTool
      : dataObject(financialData.factory_diagnostics, {});
  const hardHist = dataObject(factoryDiag.hard_gate_histogram, {});
  const exitFunnel = dataObject(factoryDiag.exit_funnel, {});
  const exitGap = dataObject(factoryDiag.exit_gap, {});
  const evidenceGapRows = Array.isArray(factoryDiag.evidence_gaps)
    ? factoryDiag.evidence_gaps.map((item: any, index: number) => ({
        id: `eg-${index}`,
        code: item?.code,
        count: item?.count,
        coverage: item?.coverage
      }))
    : [];
  const factoryNextRows = Array.isArray(factoryDiag.next_actions)
    ? factoryDiag.next_actions.map((item: any, index: number) => ({
        id: `fna-${index}`,
        code: item?.code,
        detail: item?.detail
      }))
    : [];
  const factoryIntentRows = list(intents.data)
    .filter((item) => {
      const action = String(item.action || item.target_tool || "");
      return action.includes("incubation_factory") || action.includes("factor_factory");
    })
    .slice(0, 25)
    .map((item, index) => ({
      id: String(item.intent_id || item.id || `ops-intent-${index}`),
      action: String(item.action || item.target_action || "-"),
      status: String(item.status || "-"),
      updated_at: String(item.updated_at || item.created_at || "-"),
      error: String(item.error || "")
    }));

  async function refreshFactoryOps() {
    await Promise.all([financial.reload(), factoryFormal.reload(), intents.reload(), health.reload()]);
  }

  async function createFactoryOpsIntent(action: "dry_run" | "run_once" | "maintenance" | "factor_run") {
    setOpsBusy(true);
    try {
      const map: Record<string, { title: string; action: string; params: Record<string, unknown> }> = {
        dry_run: {
          title: "Factory Ops: incubation dry-run",
          action: "incubation_factory.dry_run",
          params: { dry_run: true, source: "desktop_factory_ops" }
        },
        run_once: {
          title: "Factory Ops: incubation run_once",
          action: "incubation_factory.run_once",
          params: { dry_run: false, source: "desktop_factory_ops", _timeout_seconds: 600 }
        },
        maintenance: {
          title: "Factory Ops: incubation maintenance",
          action: "incubation_factory.maintenance",
          params: { dry_run: true, source: "desktop_factory_ops" }
        },
        factor_run: {
          title: "Factory Ops: factor dry-run",
          action: "factor_factory.run_once",
          params: { dry_run: true, limit: 20, source: "desktop_factory_ops" }
        }
      };
      const cfg = map[action];
      const result = await api.createIntent({
        title: cfg.title,
        action: cfg.action,
        params: cfg.params,
        rationale: "Desktop Factory Ops 受控运维动作"
      });
      setOpsResult(result);
      setPreviewAction(null);
      await intents.reload();
    } finally {
      setOpsBusy(false);
    }
  }

  async function confirmFactoryIntent(intentId: string) {
    if (!intentId) return;
    setOpsBusy(true);
    try {
      setOpsResult(await api.intentConfirm(intentId));
      await refreshFactoryOps();
    } finally {
      setOpsBusy(false);
    }
  }

  async function denyFactoryIntent(intentId: string) {
    if (!intentId) return;
    setOpsBusy(true);
    try {
      setOpsResult(await api.intentDeny(intentId, "denied from factory ops"));
      await intents.reload();
    } finally {
      setOpsBusy(false);
    }
  }

  const previewLabel =
    previewAction === "run_once"
      ? "incubation_factory.run_once"
      : previewAction === "maintenance"
        ? "incubation_factory.maintenance"
        : previewAction === "factor_run"
          ? "factor_factory.run_once"
          : "incubation_factory.dry_run";

  return (
    <PageShell
      title="Readiness / Health"
      description="统一展示环境门禁、financial readiness、Factory Formal/证据/Exit 漏斗，以及 Intent 化工厂运维（默认 dry-run）。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建工厂运维意图" />}
      actions={
        <Button icon={<Play size={16} />} onClick={() => void refreshFactoryOps()}>
          刷新健康与工厂诊断
        </Button>
      }
      metrics={[
        metric("Agent", healthData.status || "-", statusTone(healthData.status)),
        metric("Tools", dataObject(dataObject(healthData.tools, {}), {}).count || "-", "info"),
        metric("Financial", financialData.production_ready ? "ready" : "not ready", financialData.production_ready ? "success" : "warning"),
        metric("Formal", factoryDiag.formal_count ?? "-", "info"),
        metric("SignalID%", factoryDiag.signal_id_coverage != null ? `${Math.round(Number(factoryDiag.signal_id_coverage) * 100)}%` : "-", Number(factoryDiag.signal_id_coverage) >= 0.95 ? "success" : "warning"),
        metric("Parity", dataObject(dataObject(parity.data, {}), {}).parity_ratio || "-", "info")
      ]}
    >
      <div className="grid-3">
        <Panel title="必需门禁">
          <DataTable items={requiredGates} columns={[{ key: "name", header: "门禁" }, { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }]} />
        </Panel>
        <Panel title="可选门禁">
          <DataTable items={optionalGates} columns={[{ key: "name", header: "门禁" }, { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }]} />
        </Panel>
        <Panel title="建议动作">
          <DataTable items={nextActions} columns={[{ key: "name", header: "建议" }]} />
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title="Factory production probes">
          <SummaryFields
            items={[
              { label: "formal_count", value: factoryDiag.formal_count },
              { label: "observe_count", value: factoryDiag.observe_count },
              { label: "signal_id_coverage", value: factoryDiag.signal_id_coverage },
              { label: "open_positions", value: exitFunnel.open_positions },
              { label: "closed_positions", value: exitFunnel.closed },
              { label: "hard_gate.passed", value: hardHist.passed },
              { label: "hard_gate.missing", value: hardHist.missing },
              { label: "hard_gate.bootstrap_pending", value: hardHist.bootstrap_pending }
            ]}
          />
        </Panel>
        <Panel title="Top formal blockers">
          <DataTable
            items={Array.isArray(factoryDiag.top_blockers) ? factoryDiag.top_blockers.map((item: any, index: number) => ({ id: `blocker-${index}`, code: item?.code, count: item?.count })) : []}
            columns={[
              { key: "code", header: "blocker" },
              { key: "count", header: "count" }
            ]}
          />
        </Panel>
        <Panel title="Exit gap">
          <SummaryFields
            items={[
              { label: "exit_signals", value: exitGap.exit_signals },
              { label: "no_exit_order_strategies", value: exitGap.strategies_with_exit_signal_no_order },
              { label: "in_universe", value: exitGap.exit_signals_in_execution_universe },
              { label: "universe_size", value: exitGap.execution_universe_size },
              {
                label: "likely_causes",
                value: Array.isArray(exitGap.likely_causes) ? (exitGap.likely_causes as unknown[]).join(", ") : exitGap.likely_causes
              }
            ]}
          />
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="Evidence gaps">
          <DataTable
            items={evidenceGapRows}
            columns={[
              { key: "code", header: "gap" },
              { key: "count", header: "count" },
              { key: "coverage", header: "coverage" }
            ]}
          />
        </Panel>
        <Panel title="Factory next actions">
          <DataTable
            items={factoryNextRows}
            columns={[
              { key: "code", header: "action" },
              { key: "detail", header: "detail" }
            ]}
          />
        </Panel>
      </div>

      <Panel title="Factory Ops（Intent 化）">
        <p className="muted-value">默认 dry-run；run_once 需 control token 并在下方 Intent 审计表确认。不直连 DB，不绕过 hard gate。</p>
        <div className="page-actions">
          <Button
            data-testid="factory-ops-dry-run"
            icon={<ShieldCheck size={16} />}
            disabled={!controlAvailable || opsBusy}
            onClick={() => setPreviewAction("dry_run")}
          >
            incubation dry-run
          </Button>
          <Button
            data-testid="factory-ops-run-once"
            icon={<Play size={16} />}
            disabled={!controlAvailable || opsBusy}
            onClick={() => setPreviewAction("run_once")}
          >
            incubation run_once
          </Button>
          <Button
            data-testid="factory-ops-maintenance"
            icon={<ShieldCheck size={16} />}
            disabled={!controlAvailable || opsBusy}
            onClick={() => setPreviewAction("maintenance")}
          >
            incubation maintenance
          </Button>
          <Button
            data-testid="factory-ops-factor-run"
            icon={<ShieldCheck size={16} />}
            disabled={!controlAvailable || opsBusy}
            onClick={() => setPreviewAction("factor_run")}
          >
            factor dry-run
          </Button>
        </div>
        {previewAction ? (
          <DryRunPreview
            title="Factory Ops 意图预览"
            busy={opsBusy}
            changes={[
              { label: "动作", after: previewLabel },
              {
                label: "模式",
                after: previewAction === "run_once" ? "真实 run_once（paper/observe，非实盘）" : "dry-run / 预演"
              },
              { label: "门禁", after: "control token + Intent confirm" },
              { label: "审计", after: "写入 action_intents，可在下方回放" }
            ]}
            onCancel={() => setPreviewAction(null)}
            onConfirm={() => void createFactoryOpsIntent(previewAction)}
          />
        ) : null}
        {opsResult ? <JsonPanel data={opsResult} title="Factory Ops 意图结果" /> : null}
      </Panel>

      <Panel title="Intent / Audit 回放（factory ops）">
        <DataTable
          items={factoryIntentRows}
          columns={[
            { key: "id", header: "intent_id" },
            { key: "action", header: "action" },
            {
              key: "status",
              header: "status",
              render: (item) => <StatusLight status={inferStatusFromData(item)} label={String(item.status || "-")} />
            },
            { key: "updated_at", header: "updated" },
            {
              key: "ops",
              header: "ops",
              render: (item) => {
                const pending = /awaiting|pending/i.test(String(item.status || ""));
                if (!pending || !controlAvailable) return <span className="muted-value">{String(item.error || "-")}</span>;
                return (
                  <div className="page-actions">
                    <Button tone="success" disabled={opsBusy} onClick={() => void confirmFactoryIntent(String(item.id))}>
                      确认
                    </Button>
                    <Button tone="danger" disabled={opsBusy} onClick={() => void denyFactoryIntent(String(item.id))}>
                      拒绝
                    </Button>
                  </div>
                );
              }
            }
          ]}
        />
      </Panel>

      <JsonPanel data={{ health: health.data, hermes: hermes.data, financial: financial.data, factory_formal: factoryFormal.data, capabilities: capabilities.data, parity: parity.data }} title="健康检查证据" />
    </PageShell>
  );
}

function LocalUserMemoryPage({ api, settings, controlAvailable }: PageProps) {
  const navigate = useNavigate();
  const profile = useAsyncResource(() => api.localProfile(), [api]);
  const activity = useAsyncResource(() => api.userActivity(settings?.userId || "local-user"), [api, settings?.userId]);
  const policy = useAsyncResource(() => api.userDataPolicy(settings?.userId || "local-user"), [api, settings?.userId]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "export" | "delete" | "save-policy">(null);
  const profileData = dataObject(profile.data, {});
  const activityRows = firstArray(dataObject(activity.data, {}), ["data", "activity", "events"]);
  const userId = settings?.userId || "local-user";

  async function exportUserData() {
    setActionResult(await api.userExport(userId));
    setPreviewAction(null);
  }

  async function previewDeleteUserData() {
    setActionResult(await api.userDelete(userId, { dry_run: true, reason: "desktop V1 dry-run preview" }));
    setPreviewAction(null);
  }

  async function savePolicy() {
    setActionResult(await api.userDataPolicySave(userId, { retention_days: 90, allow_learning: false, updated_from: "desktop_v1" }));
    setPreviewAction(null);
    await policy.reload();
  }

  return (
    <PageShell
      title="本地用户记忆"
      description="承接本地画像、活动摘要、数据策略、导出、删除预览和治理状态，所有动作都通过 Agent route。"
      metrics={[
        metric("用户", profileData.user_id || userId, "info"),
        metric("活动", activityRows.length, "success"),
        metric("策略", policy.data ? "已加载" : "待加载", policy.data ? "success" : "warning"),
        metric("敏感信息", "已隐藏", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="本地画像">
          <div className="stack">
            <JsonPanel data={profile.data} title="个人资料" />
            <Button onClick={() => navigate(viewToRoute("user-profile"))}>打开完整资料编辑器</Button>
          </div>
        </Panel>
        <Panel title="活动与策略">
          <JsonPanel data={{ activity: activity.data, policy: policy.data }} title="活动与策略" />
        </Panel>
      </div>

      <Panel title="用户数据操作">
        <div className="page-actions">
          <Button data-testid="user-export-data" disabled={!controlAvailable} onClick={() => setPreviewAction("export")}>
            导出数据
          </Button>
          <Button data-testid="user-delete-dry-run" disabled={!controlAvailable} onClick={() => setPreviewAction("delete")}>
            预览删除
          </Button>
          <Button data-testid="user-save-policy" disabled={!controlAvailable} onClick={() => setPreviewAction("save-policy")}>
            保存安全策略
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="用户数据动作预览"
            changes={[
              { label: "动作", after: previewAction },
              { label: "用户", after: userId },
              { label: "说明", after: previewAction === "delete" ? "只执行预演，不会真正删除" : "通过 Agent 用户数据路由执行" }
            ]}
            onCancel={() => setPreviewAction(null)}
            onConfirm={() => {
              if (previewAction === "export") {
                void exportUserData();
                return;
              }
              if (previewAction === "delete") {
                void previewDeleteUserData();
                return;
              }
              void savePolicy();
            }}
          />
        ) : null}

        {actionResult ? <JsonPanel data={actionResult} title="User data action result" /> : null}
      </Panel>
    </PageShell>
  );
}

function LearningRlPage({ api, controlAvailable }: PageProps) {
  const learning = useControlGatedResource(controlAvailable, () => api.learningStatus(), gatedStatusPayload("learning status"), [api]);
  const review = useControlGatedResource(controlAvailable, () => api.learningReview(), gatedListPayload("learning review"), [api]);
  const envs = useControlGatedResource(controlAvailable, () => api.rlEnvironments(), gatedListPayload("RL environments"), [api]);
  const runs = useControlGatedResource(controlAvailable, () => api.rlRuns(), gatedListPayload("RL runs"), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "apply" | "start" | "stop">(null);
  const learningData = dataObject(learning.data, {});
  const envData = dataObject(envs.data, {});
  const reviewRows = list(review.data);
  const envRows = firstArray(envData, ["environments", "data"]);
  const runRows = list(runs.data);

  async function applyFirstProposal() {
    const first = reviewRows[0];
    const proposalId = String(first?.id || first?.proposal_id || "");
    if (!proposalId) return;
    setActionResult(await api.learningApply({ proposal_id: proposalId }));
    setPreviewAction(null);
    await review.reload();
  }

  async function startFirstEnvironment() {
    const first = envRows[0];
    const environment = String(first?.id || first?.environment || first?.name || "");
    if (!environment) return;
    setActionResult(await api.rlRunCreate({ environment, config: { dry_run: true, source: "desktop_v1" } }));
    setPreviewAction(null);
    await runs.reload();
  }

  async function runAction(action: "stop" | "results" | "logs") {
    const first = runRows[0];
    const runId = String(first?.id || first?.run_id || "");
    if (!runId) return;
    const result =
      action === "stop"
        ? await api.rlRunStop(runId)
        : action === "results"
          ? await api.rlRunResults(runId)
          : await api.rlRunLogs(runId);
    setActionResult(result);
    setPreviewAction(null);
    await runs.reload();
  }

  return (
    <PageShell
      title="Learning / RL"
      description="承接学习状态、review proposals、RL environments / runs 和结果诊断，动作继续受 control 门禁约束。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="应用学习建议 / RL 运行" />}
      metrics={[
        metric("学习", learningData.enabled ? "已启用" : "已停用", learningData.enabled ? "success" : "warning"),
        metric("Proposals", reviewRows.length, "warning"),
        metric("Envs", envRows.length, "info"),
        metric("运行", runRows.length, "success")
      ]}
    >
      <div className="grid-3">
        <Panel title="Review Proposals">
          <DataTable items={reviewRows} columns={[{ key: "title", header: "建议" }, { key: "status", header: "状态" }, { key: "risk", header: "风险" }]} />
        </Panel>
        <Panel title="RL Environments">
          <DataTable items={envRows} columns={[{ key: "id", header: "环境" }, { key: "status", header: "状态" }, { key: "side_effect", header: "副作用" }]} />
        </Panel>
        <Panel title="训练运行">
          <DataTable items={runRows} columns={[{ key: "id", header: "运行" }, { key: "environment", header: "环境" }, { key: "status", header: "状态" }]} />
        </Panel>
      </div>

      <Panel title="学习训练操作">
        <div className="page-actions">
          <Button data-testid="learning-apply-first" disabled={!controlAvailable || !reviewRows.length} onClick={() => setPreviewAction("apply")}>
            Apply first proposal
          </Button>
          <Button data-testid="rl-start-first" disabled={!controlAvailable || !envRows.length} onClick={() => setPreviewAction("start")}>
            Start first environment
          </Button>
          <Button data-testid="rl-stop-first" disabled={!controlAvailable || !runRows.length} onClick={() => setPreviewAction("stop")}>
            停止第一条运行
          </Button>
          <Button data-testid="rl-load-results" disabled={!controlAvailable || !runRows.length} onClick={() => void runAction("results")}>
            Load results
          </Button>
          <Button data-testid="rl-load-logs" disabled={!controlAvailable || !runRows.length} onClick={() => void runAction("logs")}>
            Load logs
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="Learning / RL 动作预览"
            changes={[
              { label: "动作", after: previewAction },
              {
                label: "目标",
                after:
                  previewAction === "apply"
                    ? String(reviewRows[0]?.title || reviewRows[0]?.id || "-")
                    : previewAction === "start"
                      ? String(envRows[0]?.id || envRows[0]?.environment || "-")
                      : String(runRows[0]?.id || runRows[0]?.run_id || "-")
              },
              { label: "模式", after: previewAction === "start" ? "预演" : "受控动作" }
            ]}
            onCancel={() => setPreviewAction(null)}
            onConfirm={() => {
              if (previewAction === "apply") {
                void applyFirstProposal();
                return;
              }
              if (previewAction === "start") {
                void startFirstEnvironment();
                return;
              }
              void runAction("stop");
            }}
          />
        ) : null}

        {actionResult ? <JsonPanel data={actionResult} title="Learning / RL action result" /> : null}
      </Panel>

      <JsonPanel data={{ learning: learning.data, review: review.data, envs: envs.data, runs: runs.data }} title="学习能力证据" />
    </PageShell>
  );
}

function NativeDiagnosticsPage({ api, controlAvailable }: PageProps) {
  const gatedNativeList = { object: "list", data: [], gated: true, reason: "control_token_required" };
  const processes = useAsyncResource(() => (controlAvailable ? api.processes() : Promise.resolve(gatedNativeList)), [api, controlAvailable]);
  const backends = useAsyncResource(() => (controlAvailable ? api.terminalBackends() : Promise.resolve(gatedNativeList)), [api, controlAvailable]);
  const terminalSessions = useAsyncResource(() => (controlAvailable ? api.terminalSessions() : Promise.resolve(gatedNativeList)), [api, controlAvailable]);
  const browserSessions = useAsyncResource(() => (controlAvailable ? api.browserSessions() : Promise.resolve(gatedNativeList)), [api, controlAvailable]);

  return (
    <PageShell
      title="Native Diagnostics"
      description="只展示本机能力诊断、后端门禁和会话状态，不允许前端直接执行本机动作。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="本机高权限操作" />}
      metrics={[
        metric("Processes", list(processes.data).length, "info"),
        metric("Terminal backends", list(backends.data).length, "success"),
        metric("Terminal sessions", list(terminalSessions.data).length, "warning"),
        metric("Browser sessions", list(browserSessions.data).length, "warning")
      ]}
    >
      <div className="grid-3">
        <Panel title="进程">
          <DataTable items={list(processes.data)} columns={[{ key: "pid", header: "PID" }, { key: "name", header: "名称" }, { key: "status", header: "状态" }]} />
        </Panel>
        <Panel title="终端后端">
          <DataTable items={list(backends.data)} columns={[{ key: "name", header: "后端" }, { key: "available", header: "可用" }, { key: "gated", header: "门禁" }]} />
        </Panel>
        <Panel title="浏览器会话">
          <DataTable items={list(browserSessions.data)} columns={[{ key: "id", header: "会话" }, { key: "status", header: "状态" }]} />
        </Panel>
      </div>

      <Panel title="能力边界" action={<ShieldCheck size={18} />}>
        <p>前端只显示 Agent 返回的诊断状态。文件、终端、浏览器、进程等动作必须通过 Agent `agent_*` 工具和后端策略控制。</p>
      </Panel>
    </PageShell>
  );
}
