import { Play, Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { DryRunPreview } from "../components/IntentComponents";
import { StatusLight, inferStatusFromData } from "../components/StatusLight";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, GatedNotice, JsonPanel, LinkCard, PageShell, Panel } from "../components/ui";
import type { ConnectionSettings } from "../types";
import { dataObject, firstArray, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";
import { viewToRoute } from "../routes";

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
          { label: "Action", after: "create job" },
          { label: "Name", after: String(buildPayload().name) },
          { label: "Template", after: String(buildPayload().template) },
          { label: "Control", after: "Agent /v1/jobs with control token gate" }
        ]
      : [
          { label: "Action", after: String(previewAction || "") },
          { label: "Target", after: jobName(targetJob) },
          { label: "Control", after: "Agent Jobs API controlled route" }
        ];

  return (
    <PageShell
      title="Automation"
      description="Create, run, disable, and delete controlled Agent jobs from explicit forms and dry-run previews."
      badge={<GatedNotice controlAvailable={controlAvailable} action="create / run jobs" />}
      metrics={[
        metric("Jobs", rows.length, "info"),
        metric("Enabled", enabledRows.length, "success"),
        metric("Scheduled", scheduledRows.length, "info"),
        metric("Manual", manualRows.length, "warning")
      ]}
    >
      <div className="grid-2">
        <Panel title="Create Job">
          <div className="form-grid">
            <label className="field">
              <span>Template</span>
              <select data-testid="job-template" value={form.template} onChange={(event) => setForm({ ...form, template: event.target.value })}>
                <option value="generic">Prompt job</option>
                <option value="watch">Market watch</option>
              </select>
            </label>
            <label className="field">
              <span>Name</span>
              <input data-testid="job-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Daily market brief" />
            </label>
            <label className="field">
              <span>Schedule</span>
              <select value={form.schedule} onChange={(event) => setForm({ ...form, schedule: event.target.value })}>
                <option value="interval">Interval</option>
                <option value="manual">Manual</option>
              </select>
            </label>
            <label className="field">
              <span>Interval seconds</span>
              <input data-testid="job-interval" type="number" min="60" value={form.interval_seconds} onChange={(event) => setForm({ ...form, interval_seconds: event.target.value })} disabled={form.schedule === "manual"} />
            </label>
            {form.template === "watch" ? (
              <>
                <label className="field">
                  <span>Symbol</span>
                  <input data-testid="job-watch-symbol" value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value })} />
                </label>
                <label className="field">
                  <span>Query</span>
                  <input value={form.query} onChange={(event) => setForm({ ...form, query: event.target.value })} placeholder="optional topic" />
                </label>
                <label className="field">
                  <span>Condition</span>
                  <input data-testid="job-watch-condition" value={form.condition} onChange={(event) => setForm({ ...form, condition: event.target.value })} />
                </label>
                <label className="field">
                  <span>Channel</span>
                  <select value={form.channel} onChange={(event) => setForm({ ...form, channel: event.target.value })}>
                    <option value="local">Local</option>
                    <option value="feishu">Feishu</option>
                    <option value="wecom">WeCom</option>
                    <option value="discord">Discord</option>
                  </select>
                </label>
              </>
            ) : (
              <label className="field" style={{ gridColumn: "1 / -1" }}>
                <span>Prompt</span>
                <textarea data-testid="job-prompt" value={form.prompt} onChange={(event) => setForm({ ...form, prompt: event.target.value })} rows={4} />
              </label>
            )}
            <label className="field">
              <span>Enabled</span>
              <input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />
            </label>
            <label className="field">
              <span>Dry run</span>
              <input type="checkbox" checked={form.dry_run} onChange={(event) => setForm({ ...form, dry_run: event.target.checked })} />
            </label>
          </div>
          <div className="page-actions">
            <Button data-testid="job-create" icon={<Save size={16} />} tone="success" disabled={!controlAvailable} onClick={() => setPreviewAction("create")}>
              Preview create
            </Button>
          </div>
        </Panel>

        <Panel title="Job Findings">
          <JsonPanel
            data={{
              jobs: rows,
              enabled_count: enabledRows.length,
              scheduled_count: scheduledRows.length,
              manual_count: manualRows.length,
              form_payload: buildPayload()
            }}
            title="Automation findings"
          />
        </Panel>
      </div>

      <Panel title="Jobs">
        <DataTable
          items={rows}
          columns={[
            { key: "name", header: "Job" },
            { key: "enabled", header: "Enabled" },
            { key: "schedule", header: "Schedule" },
            { key: "toolset", header: "Toolset" },
            {
              key: "id",
              header: "Actions",
              render: (job) => (
                <div className="page-actions">
                  <Button data-testid={`job-run-${jobId(job)}`} icon={<Play size={14} />} disabled={!controlAvailable} onClick={() => openJobPreview("run", job)}>
                    Run
                  </Button>
                  <Button data-testid={`job-toggle-${jobId(job)}`} icon={<ShieldCheck size={14} />} disabled={!controlAvailable} onClick={() => openJobPreview("toggle", job)}>
                    {job.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button data-testid={`job-delete-${jobId(job)}`} tone="danger" disabled={!controlAvailable} onClick={() => openJobPreview("delete", job)}>
                    Delete
                  </Button>
                </div>
              )
            }
          ]}
        />
      </Panel>

      {previewAction ? (
        <DryRunPreview
          title="Automation preview"
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

      <JsonPanel data={{ jobs: jobs.data, last_result: result }} title="Automation evidence" />
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
      title="Settings"
      description="集中管理 Agent HTTP base、API token、control token、mock / live 模式和用户上下文，保留 secret 脱敏。"
      badge={<StatusLight status={controlAvailable ? "connected" : "disconnected"} label={controlAvailable ? "Control token 已输入" : "Control token 缺失"} />}
      metrics={[
        metric("Mode", local.mode, local.mode === "mock" ? "warning" : "info"),
        metric("API Token", local.apiToken ? "已输入" : "空", local.apiToken ? "success" : "warning"),
        metric("Control", local.controlToken ? "已输入" : "空", local.controlToken ? "success" : "gated"),
        metric("User", local.userId, "info")
      ]}
    >
      <Panel title="连接设置">
        <div className="form-grid">
          <label className="field">
            <span>Agent Base URL</span>
            <input value={local.baseUrl} onChange={(event) => setLocal({ ...local, baseUrl: event.target.value })} />
          </label>
          <label className="field">
            <span>Mode</span>
            <select value={local.mode} onChange={(event) => setLocal({ ...local, mode: event.target.value as ConnectionSettings["mode"] })}>
              <option value="mock">mock</option>
              <option value="live">live</option>
            </select>
          </label>
          <label className="field">
            <span>API Token</span>
            <input type="password" value={local.apiToken} onChange={(event) => setLocal({ ...local, apiToken: event.target.value })} />
          </label>
          <label className="field">
            <span>Control Token</span>
            <input type="password" value={local.controlToken} onChange={(event) => setLocal({ ...local, controlToken: event.target.value })} />
          </label>
          <label className="field">
            <span>User ID</span>
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
            { area: "Live trading", rule: "V1 不开放", status: "blocked" }
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

function ReadinessHealthPage({ api }: PageProps) {
  const health = useAsyncResource(() => api.healthDetailed(), [api]);
  const hermes = useAsyncResource(() => api.hermesReadiness(), [api]);
  const financial = useAsyncResource(() => api.financialReadiness(), [api]);
  const capabilities = useAsyncResource(() => api.capabilities(), [api]);
  const parity = useAsyncResource(() => api.parity(), [api]);
  const healthData = dataObject(health.data, {});
  const financialData = dataObject(financial.data, {});
  const requiredGates = firstArray(financialData, ["required_gates"]);
  const optionalGates = firstArray(financialData, ["optional_gates"]);
  const nextActions = Array.isArray(financialData.next_actions) ? financialData.next_actions.map((name) => ({ name })) : [];

  return (
    <PageShell
      title="Readiness / Health"
      description="统一展示当前环境、门禁、capabilities parity、financial readiness 与下一步动作。"
      metrics={[
        metric("Agent", healthData.status || "-", statusTone(healthData.status)),
        metric("Tools", dataObject(dataObject(healthData.tools, {}), {}).count || "-", "info"),
        metric("Financial", financialData.production_ready ? "ready" : "not ready", financialData.production_ready ? "success" : "warning"),
        metric("Parity", dataObject(dataObject(parity.data, {}), {}).parity_ratio || "-", "info")
      ]}
    >
      <div className="grid-3">
        <Panel title="Required Gates">
          <DataTable items={requiredGates} columns={[{ key: "name", header: "Gate" }, { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }]} />
        </Panel>
        <Panel title="Optional Gates">
          <DataTable items={optionalGates} columns={[{ key: "name", header: "Gate" }, { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }]} />
        </Panel>
        <Panel title="Next Actions">
          <DataTable items={nextActions} columns={[{ key: "name", header: "建议" }]} />
        </Panel>
      </div>

      <JsonPanel data={{ health: health.data, hermes: hermes.data, financial: financial.data, capabilities: capabilities.data, parity: parity.data }} title="Readiness evidence" />
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
      title="Local User Memory"
      description="承接本地画像、活动摘要、数据策略、导出、删除预览和治理状态，所有动作都通过 Agent route。"
      metrics={[
        metric("User", profileData.user_id || userId, "info"),
        metric("活动", activityRows.length, "success"),
        metric("Policy", policy.data ? "loaded" : "pending", policy.data ? "success" : "warning"),
        metric("Secrets", "Redacted", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="本地画像">
          <div className="stack">
            <JsonPanel data={profile.data} title="Profile" />
            <Button onClick={() => navigate(viewToRoute("user-profile"))}>Open full profile editor</Button>
          </div>
        </Panel>
        <Panel title="活动与策略">
          <JsonPanel data={{ activity: activity.data, policy: policy.data }} title="Activity / Policy" />
        </Panel>
      </div>

      <Panel title="User Data Actions">
        <div className="page-actions">
          <Button data-testid="user-export-data" disabled={!controlAvailable} onClick={() => setPreviewAction("export")}>
            Export data
          </Button>
          <Button data-testid="user-delete-dry-run" disabled={!controlAvailable} onClick={() => setPreviewAction("delete")}>
            Preview delete dry-run
          </Button>
          <Button data-testid="user-save-policy" disabled={!controlAvailable} onClick={() => setPreviewAction("save-policy")}>
            Save safe policy
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="用户数据动作预览"
            changes={[
              { label: "动作", after: previewAction },
              { label: "用户", after: userId },
              { label: "说明", after: previewAction === "delete" ? "只执行 dry-run 预览" : "通过 Agent user data route 执行" }
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
  const learning = useAsyncResource(() => api.learningStatus(), [api]);
  const review = useAsyncResource(() => api.learningReview(), [api]);
  const envs = useAsyncResource(() => api.rlEnvironments(), [api]);
  const runs = useAsyncResource(() => api.rlRuns(), [api]);
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
        metric("Learning", learningData.enabled ? "enabled" : "disabled", learningData.enabled ? "success" : "warning"),
        metric("Proposals", reviewRows.length, "warning"),
        metric("Envs", envRows.length, "info"),
        metric("Runs", runRows.length, "success")
      ]}
    >
      <div className="grid-3">
        <Panel title="Review Proposals">
          <DataTable items={reviewRows} columns={[{ key: "title", header: "建议" }, { key: "status", header: "状态" }, { key: "risk", header: "风险" }]} />
        </Panel>
        <Panel title="RL Environments">
          <DataTable items={envRows} columns={[{ key: "id", header: "环境" }, { key: "status", header: "状态" }, { key: "side_effect", header: "副作用" }]} />
        </Panel>
        <Panel title="RL Runs">
          <DataTable items={runRows} columns={[{ key: "id", header: "运行" }, { key: "environment", header: "环境" }, { key: "status", header: "状态" }]} />
        </Panel>
      </div>

      <Panel title="Learning / RL Actions">
        <div className="page-actions">
          <Button data-testid="learning-apply-first" disabled={!controlAvailable || !reviewRows.length} onClick={() => setPreviewAction("apply")}>
            Apply first proposal
          </Button>
          <Button data-testid="rl-start-first" disabled={!controlAvailable || !envRows.length} onClick={() => setPreviewAction("start")}>
            Start first environment
          </Button>
          <Button data-testid="rl-stop-first" disabled={!controlAvailable || !runRows.length} onClick={() => setPreviewAction("stop")}>
            Stop first run
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
              { label: "模式", after: previewAction === "start" ? "dry-run" : "受控动作" }
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

      <JsonPanel data={{ learning: learning.data, review: review.data, envs: envs.data, runs: runs.data }} title="Learning capability evidence" />
    </PageShell>
  );
}

function NativeDiagnosticsPage({ api, controlAvailable }: PageProps) {
  const processes = useAsyncResource(() => api.processes(), [api]);
  const backends = useAsyncResource(() => api.terminalBackends(), [api]);
  const terminalSessions = useAsyncResource(() => api.terminalSessions(), [api]);
  const browserSessions = useAsyncResource(() => api.browserSessions(), [api]);

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
