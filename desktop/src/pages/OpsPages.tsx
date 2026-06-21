import { Play, Save, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, GatedNotice, JsonPanel, LinkCard, PageShell, Panel, StatusBadge } from "../components/ui";
import type { ConnectionSettings } from "../types";
import { dataObject, firstArray, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";

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
  const rows = list(jobs.data);
  const sampleJobName = "desktop-v1-smoke-job";

  async function runFirstJob() {
    const first = rows[0];
    if (!first?.id) return;
    setResult(await api.runJob(String(first.id)));
    await jobs.reload();
  }

  async function createSampleJob() {
    setResult(await api.createJob({ name: sampleJobName, prompt: "AIASK Desktop V1 smoke job", interval_seconds: 3600, enabled: false }));
    await jobs.reload();
  }

  async function disableSampleJob() {
    const target = rows.find((job) => String(job.name || "") === sampleJobName);
    if (!target?.id) return;
    setResult(await api.updateJob(String(target.id), { enabled: false }));
    await jobs.reload();
  }

  async function deleteSampleJob() {
    const target = rows.find((job) => String(job.name || "") === sampleJobName);
    if (!target?.id) return;
    setResult(await api.deleteJob(String(target.id)));
    await jobs.reload();
  }

  return (
    <PageShell
      title="自动化盯盘与任务处理"
      description="管理 jobs、运行历史、手动触发和调度门禁；运行任务需要 control token 或后端批准。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建/触发任务" />}
      actions={<Button icon={<Play size={16} />} disabled={!controlAvailable || !rows.length} onClick={() => void runFirstJob()}>触发首个任务</Button>}
      metrics={[
        metric("Jobs", rows.length, "info"),
        metric("Enabled", rows.filter((job) => Boolean(job.enabled)).length, "success"),
        metric("Manual", rows.filter((job) => String(job.schedule || "").includes("manual")).length, "warning"),
        metric("Gate", controlAvailable ? "open" : "control required", controlAvailable ? "success" : "gated")
      ]}
    >
      <Panel title="任务列表">
        <DataTable
          items={rows}
          columns={[
            { key: "name", header: "任务" },
            { key: "enabled", header: "启用" },
            { key: "schedule", header: "计划" },
            { key: "toolset", header: "Toolset" }
          ]}
        />
      </Panel>
      <Panel title="Job Actions">
        <div className="page-actions">
          <Button disabled={!controlAvailable} onClick={() => void createSampleJob()}>Create sample job</Button>
          <Button disabled={!controlAvailable} onClick={() => void disableSampleJob()}>Disable sample job</Button>
          <Button disabled={!controlAvailable} onClick={() => void deleteSampleJob()}>Delete sample job</Button>
        </div>
      </Panel>
      <JsonPanel data={{ jobs: jobs.data, last_result: result }} title="自动化证据" />
    </PageShell>
  );
}

function WorkflowsPage(_props: PageProps) {
  const steps = [
    { name: "Data", detail: "数据源配置、数据库状态、新鲜度和同步计划。", to: "/data-sync", tone: "info" as const },
    { name: "Radar", detail: "股票候选、摘要和受控运行/投递意图。", to: "/stock-radar", tone: "success" as const },
    { name: "Market", detail: "市场温度、行业冷热和缓存验证。", to: "/market-temperature", tone: "warning" as const },
    { name: "Quant", detail: "Preset、研究运行、报告和限制说明。", to: "/quant-research", tone: "neutral" as const },
    { name: "Manager", detail: "经理台只读查询和受控意图。", to: "/financial-manager", tone: "gated" as const },
    { name: "Gateway", detail: "投递预览、目录、消息和 Webhooks。", to: "/gateway-webhooks", tone: "neutral" as const }
  ];
  return (
    <PageShell
      title="V1 工作流"
      description="展示第一版金融研究与自动化的端到端路径：Data -> Radar -> Market -> Quant -> Manager -> Gateway/Automation。"
      metrics={[
        metric("流程节点", steps.length, "info"),
        metric("副作用动作", "Intent/Approval", "gated"),
        metric("实盘交易", "不开放", "success"),
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
      title="设置、安全与门禁"
      description="设置 Agent HTTP base、API token、control token、mock/live 模式和用户上下文；secret 在页面与证据中脱敏。"
      badge={<StatusBadge tone={controlAvailable ? "success" : "gated"}>{controlAvailable ? "Control token 已输入" : "Control token 缺失"}</StatusBadge>}
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
            { area: "Desktop boundary", rule: "仅 Agent HTTP", status: "enforced" },
            { area: "Secrets", rule: "页面/JSON 脱敏", status: "enforced" },
            { area: "Side effects", rule: "Intent/Approval/control token", status: controlAvailable ? "ready" : "gated" },
            { area: "Live trading", rule: "V1 不开放", status: "blocked" }
          ]}
          columns={[
            { key: "area", header: "区域" },
            { key: "rule", header: "规则" },
            { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }
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
      title="Readiness 健康诊断与运维"
      description="检查 Agent、Hermes、capabilities parity、金融 readiness 和 next actions；建议不会跳向 V1 不展示入口。"
      metrics={[
        metric("Agent", healthData.status || "-", statusTone(healthData.status)),
        metric("Tools", dataObject(dataObject(healthData.tools, {}), {}).count || "-", "info"),
        metric("Financial", financialData.production_ready ? "ready" : "not ready", financialData.production_ready ? "success" : "warning"),
        metric("Parity", dataObject(dataObject(parity.data, {}), {}).parity_ratio || "-", "info")
      ]}
    >
      <div className="grid-3">
        <Panel title="Required Gates">
          <DataTable items={requiredGates} columns={[{ key: "name", header: "Gate" }, { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }]} />
        </Panel>
        <Panel title="Optional Gates">
          <DataTable items={optionalGates} columns={[{ key: "name", header: "Gate" }, { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }]} />
        </Panel>
        <Panel title="Next Actions">
          <DataTable items={nextActions} columns={[{ key: "name", header: "建议" }]} />
        </Panel>
      </div>
      <JsonPanel data={{ health: health.data, hermes: hermes.data, financial: financial.data, capabilities: capabilities.data, parity: parity.data }} title="Readiness 证据" />
    </PageShell>
  );
}

function LocalUserMemoryPage({ api, settings, controlAvailable }: PageProps) {
  const profile = useAsyncResource(() => api.localProfile(), [api]);
  const activity = useAsyncResource(() => api.userActivity(settings?.userId || "local-user"), [api, settings?.userId]);
  const policy = useAsyncResource(() => api.userDataPolicy(settings?.userId || "local-user"), [api, settings?.userId]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const profileData = dataObject(profile.data, {});
  const activityRows = firstArray(dataObject(activity.data, {}), ["data", "activity", "events"]);
  const userId = settings?.userId || "local-user";

  async function exportUserData() {
    setActionResult(await api.userExport(userId));
  }

  async function previewDeleteUserData() {
    setActionResult(await api.userDelete(userId, { dry_run: true, reason: "desktop V1 dry-run preview" }));
  }

  async function savePolicy() {
    setActionResult(await api.userDataPolicySave(userId, { retention_days: 90, allow_learning: false, updated_from: "desktop_v1" }));
    await policy.reload();
  }

  return (
    <PageShell
      title="记忆与个人能力"
      description="展示本地画像、活动摘要、数据策略、导出/删除预览和治理状态；个人数据操作通过 Agent route。"
      metrics={[
        metric("User", profileData.user_id || userId, "info"),
        metric("活动", activityRows.length, "success"),
        metric("Policy", policy.data ? "loaded" : "pending", policy.data ? "success" : "warning"),
        metric("Secrets", "Redacted", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="本地画像">
          <JsonPanel data={profile.data} title="Profile" />
        </Panel>
        <Panel title="活动与策略">
          <JsonPanel data={{ activity: activity.data, policy: policy.data }} title="Activity / Policy" />
        </Panel>
      </div>
      <Panel title="User Data Actions">
        <div className="page-actions">
          <Button disabled={!controlAvailable} onClick={() => void exportUserData()}>Export data</Button>
          <Button disabled={!controlAvailable} onClick={() => void previewDeleteUserData()}>Preview delete dry-run</Button>
          <Button disabled={!controlAvailable} onClick={() => void savePolicy()}>Save safe policy</Button>
        </div>
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
  const learningData = dataObject(learning.data, {});
  const reviewRows = list(review.data);
  const envRows = list(envs.data);
  const runRows = list(runs.data);

  async function applyFirstProposal() {
    const first = reviewRows[0];
    const proposalId = String(first?.id || first?.proposal_id || "");
    if (!proposalId) return;
    setActionResult(await api.learningApply({ proposal_id: proposalId }));
    await review.reload();
  }

  async function startFirstEnvironment() {
    const first = envRows[0];
    const environment = String(first?.id || first?.environment || first?.name || "");
    if (!environment) return;
    setActionResult(await api.rlRunCreate({ environment, config: { dry_run: true, source: "desktop_v1" } }));
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
    await runs.reload();
  }

  return (
    <PageShell
      title="Learning / RL / MoA 学习能力"
      description="展示学习循环、review proposals、RL environments/runs 和运行结果入口；应用变更受 full/control 门禁。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="应用学习建议/RL 运行" />}
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
          <Button disabled={!controlAvailable || !reviewRows.length} onClick={() => void applyFirstProposal()}>Apply first proposal</Button>
          <Button disabled={!controlAvailable || !envRows.length} onClick={() => void startFirstEnvironment()}>Start first environment</Button>
          <Button disabled={!controlAvailable || !runRows.length} onClick={() => void runAction("stop")}>Stop first run</Button>
          <Button disabled={!controlAvailable || !runRows.length} onClick={() => void runAction("results")}>Load results</Button>
          <Button disabled={!controlAvailable || !runRows.length} onClick={() => void runAction("logs")}>Load logs</Button>
        </div>
        {actionResult ? <JsonPanel data={actionResult} title="Learning/RL action result" /> : null}
      </Panel>
      <JsonPanel data={{ learning: learning.data, review: review.data, envs: envs.data, runs: runs.data }} title="学习能力证据" />
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
      title="Native 文件、代码、终端、浏览器能力"
      description="V1 仅展示本机能力诊断、后端门禁和会话状态，不让前端直接执行本机操作。"
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
        <p>前端只展示 Agent 返回的诊断状态。本机文件、终端、浏览器、进程等动作必须由 Agent `agent_*` 工具和后端策略控制。</p>
      </Panel>
    </PageShell>
  );
}
