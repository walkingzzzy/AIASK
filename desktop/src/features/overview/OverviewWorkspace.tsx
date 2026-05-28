import { Activity, BarChart3, Bot, CalendarClock, Database, Factory, FlaskConical, Layers3, RefreshCw, ServerCog } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, DesktopDataStatus, DesktopSettingsStatus, FactorFactoryStatus, HealthDetailed } from "../../types";

function factoryEnvelopeStatus(value: unknown): string {
  const envelope = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  if (envelope.success === true) return "ready";
  if ((envelope.data as Record<string, unknown> | undefined)?.gated) return "gated";
  if (envelope.error_code) return "unconfigured";
  return "not_loaded";
}

export function OverviewWorkspace({
  endpoint,
  apiToken,
  controlToken,
  health,
  autoRefresh = true
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  health: HealthDetailed | null;
  autoRefresh?: boolean;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [data, setData] = useState<DesktopDataStatus | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityWorkbenchPayload | null>(null);
  const [factor, setFactor] = useState<FactorFactoryStatus | null>(null);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [settingsPayload, dataPayload, capabilitiesPayload, factorPayload, jobsPayload] = await Promise.all([
        api.settingsStatus(),
        api.dataStatus(),
        api.capabilities(),
        api.factorFactoryStatus(20),
        api.jobsList()
      ]);
      setSettings(settingsPayload);
      setData(dataPayload);
      setCapabilities(capabilitiesPayload);
      setFactor(factorPayload);
      setJobs(jobsPayload.data || []);
      setMessage("OVERVIEW_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!autoRefresh) return;
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken, autoRefresh]);

  const mcp = capabilities?.mcp;
  const skills = capabilities?.skills?.skills || [];
  const plugins = Array.isArray(capabilities?.plugins) ? capabilities?.plugins : [];
  const strategyFactory = capabilities?.strategy_factory;
  const control = capabilities?.summary.control;
  const profile = settings?.profile;

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>总览</span>
          <h1>统一指挥台</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{endpoint}</span>
              <h2>{profile?.profile_name || "本地操作者"}</h2>
              <p>这里把 Agent、模型提供方、数据库、MCP、技能、自动化和三类工厂汇总成一个操作视图。</p>
            </div>
            <div className="status-cluster">
              <StatusBadge status={health?.status || "not_loaded"} label={health?.status || "离线"} />
              <StatusBadge status={control?.authorized ? "ready" : "gated"} label={control?.authorized ? "控制已授权" : "控制受限"} />
            </div>
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="智能体" value={health?.status || "离线"} status={health?.status || "not_loaded"} />
            <MetricCard label="LLM" value={settings?.llm.ai_status?.provider || "-"} status={settings?.llm.ai_status?.configured ? "ready" : "unconfigured"} />
            <MetricCard label="数据库" value={data?.database?.writable === false ? "blocked" : data?.status || "-"} status={data?.status} />
            <MetricCard label="任务" value={jobs.length} status={jobs.length ? "ready" : "not_loaded"} />
          </div>

          <section className="capability-grid three">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>Agent 运行时</span>
                  <h3>端点与用户作用域</h3>
                </div>
                <Bot size={18} />
              </div>
              <div className="kv-grid">
                <span>用户</span>
                <strong>{profile?.user_id || "local"}</strong>
                <span>模式</span>
                <strong>{compact(settings?.agent?.toolset)}</strong>
                <span>工具</span>
                <strong>{health?.tools?.count ?? "-"}</strong>
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>MCP 与技能</span>
                  <h3>扩展能力面</h3>
                </div>
                <ServerCog size={18} />
              </div>
              <div className="kv-grid">
                <span>MCP</span>
                <strong>{mcp?.discovery_status || "-"}</strong>
                <span>技能</span>
                <strong>{Array.isArray(skills) ? skills.length : 0}</strong>
                <span>插件</span>
                <strong>{plugins?.length || 0}</strong>
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>数据质量</span>
                  <h3>新鲜度闸门</h3>
                </div>
                <Database size={18} />
              </div>
              <div className="kv-grid">
                <span>代码</span>
                <strong>{data?.codes?.length || 0}</strong>
                <span>缺失</span>
                <strong>{data?.missing_count ?? "-"}</strong>
                <span>过期</span>
                <strong>{data?.stale_count ?? "-"}</strong>
              </div>
            </article>
          </section>

          <section className="capability-grid three">
            <article className="capability-card">
              <div className="card-head">
                <div>
                  <span>策略工厂</span>
                  <h3>生成与评审</h3>
                </div>
                <Factory size={18} />
              </div>
              <StatusBadge status={factoryEnvelopeStatus(strategyFactory?.status)} />
              <p className="muted">最近运行和评审快照可在策略工厂页面查看。</p>
            </article>
            <article className="capability-card">
              <div className="card-head">
                <div>
                  <span>因子工厂</span>
                  <h3>挖掘与池健康</h3>
                </div>
                <BarChart3 size={18} />
              </div>
              <StatusBadge status={factor?.status || "not_loaded"} />
              <p className="muted">当前桌面快照中有 {factor?.active_factors?.length || 0} 个活跃因子。</p>
            </article>
            <article className="capability-card">
              <div className="card-head">
                <div>
                  <span>孵化工厂</span>
                  <h3>前向验证</h3>
                </div>
                <FlaskConical size={18} />
              </div>
              <StatusBadge status={factoryEnvelopeStatus(capabilities?.strategy_factory?.review_snapshot)} label="评审已关联" />
              <p className="muted">生命周期事件和命中率报告可在孵化工厂页面查看。</p>
            </article>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>自动化</span>
                  <h3>计划任务</h3>
                </div>
                <CalendarClock size={18} />
              </div>
              <div className="mini-list">
                {jobs.slice(0, 5).map((job) => (
                  <article key={String(job.job_id || job.id)}>
                    <strong>{String(job.name || job.job_id)}</strong>
                    <span>{String(job.schedule || job.interval_seconds || "手动")}</span>
                    <StatusBadge status={job.enabled ? "ready" : "disabled"} label={job.enabled ? "已启用" : "已停用"} />
                  </article>
                ))}
                {!jobs.length && <p className="muted">尚未配置自动化任务。</p>}
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>已安装技能</span>
                  <h3>操作手册</h3>
                </div>
                <Layers3 size={18} />
              </div>
              <div className="mini-list">
                {(Array.isArray(skills) ? skills : []).slice(0, 6).map((skill) => (
                  <article key={String(skill.name)}>
                    <strong>{String(skill.name)}</strong>
                    <span>{String(skill.description || skill.path || "暂无描述")}</span>
                  </article>
                ))}
                {!Array.isArray(skills) || !skills.length ? <p className="muted">技能列表需要控制权限后才能查看。</p> : null}
              </div>
            </article>
          </section>

          <details className="raw-details">
            <summary>原始总览快照</summary>
            <JsonPanel value={{ settings, data, capabilities, factor, jobs }} />
          </details>
        </div>
      </div>
    </section>
  );
}
