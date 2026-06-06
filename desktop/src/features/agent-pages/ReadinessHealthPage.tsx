import { Activity, AlertTriangle, RefreshCw } from "lucide-react";
import { useEffect, useMemo } from "react";
import { DiagnosticsPanel } from "../../components/DiagnosticsPanel";
import { JsonPanel, MetricCard, StatusBadge } from "../../components/shared";
import { ReadinessDiagnostic } from "../../components/ReadinessDiagnostic";
import { useCapabilityWorkbench } from "../../hooks/useCapabilityWorkbench";
import type { FullModeConsoleData, HealthDetailed, HermesStatus, MainView } from "../../types";
import "../../components/AgentEnhancements.css";

interface DiagnosticResult {
  category: string;
  status: "healthy" | "warning" | "error";
  title: string;
  message: string;
  fix_suggestions: string[];
  related_page?: string;
}

function readinessStatus(value: unknown): string {
  if (!value || typeof value !== "object") return "not_loaded";
  const record = value as Record<string, unknown>;
  return String(record.status || record.live_status || record.object || "ready");
}

export function ReadinessHealthPage({
  endpoint,
  apiToken,
  controlToken,
  fullConsole,
  health,
  hermesStatus,
  onOpenView,
  onRefreshHermes,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  fullConsole: FullModeConsoleData;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  onOpenView: (view: MainView) => void;
  onRefreshHermes: () => void;
}) {
  const { payload, message, busy, refresh } = useCapabilityWorkbench(endpoint, apiToken, controlToken);

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  const financial = payload?.financial_system;
  const providerStatus = readinessStatus(payload?.providers || payload?.ai || fullConsole.providers);
  const mcpStatus = String(payload?.mcp?.discovery_status || payload?.mcp?.registration_status || "not_loaded");
  const gatewayStatus = readinessStatus(fullConsole.gatewayStatus);
  const pluginStatus = fullConsole.plugins?.length ? "ready" : controlToken.trim() ? "not_loaded" : "gated";
  const modeTokenStatus = controlToken.trim() ? "ready" : "gated";

  // 生成诊断结果
  const diagnosticResults = useMemo((): DiagnosticResult[] => {
    const results: DiagnosticResult[] = [];

    // AI Provider 检查
    if (providerStatus !== "ready" && providerStatus !== "ok") {
      results.push({
        category: "AI Provider",
        status: "error",
        title: "AI Provider 连接异常",
        message: `当前状态: ${providerStatus}。无法调用 AI 模型。`,
        fix_suggestions: [
          "检查 API 端点配置",
          "验证 API Token 是否有效",
          "确认后端服务正在运行",
          "查看后端日志了解详细错误"
        ],
        related_page: "Settings / Connection"
      });
    }

    // MCP 授权检查
    if (payload?.mcp?.missing_auth_env_vars?.length) {
      results.push({
        category: "MCP",
        status: "warning",
        title: "MCP 服务需要重新认证",
        message: `以下服务缺少认证: ${payload.mcp.missing_auth_env_vars.join(", ")}`,
        fix_suggestions: [
          "前往 MCP / Connectors 页面",
          "找到未认证的服务",
          "点击 OAuth 认证按钮",
          "完成授权流程"
        ],
        related_page: "MCP / Connectors"
      });
    }

    // Control Token 检查
    if (!controlToken.trim()) {
      results.push({
        category: "Control Token",
        status: "warning",
        title: "Control Token 未配置",
        message: "部分管理功能需要 Control Token 才能使用。",
        fix_suggestions: [
          "前往 Settings 页面",
          "填写 Control Token",
          "保存配置"
        ],
        related_page: "Settings"
      });
    }

    // Gateway 检查
    if (gatewayStatus !== "ready" && gatewayStatus !== "ok") {
      results.push({
        category: "Gateway",
        status: "error",
        title: "Gateway 连接失败",
        message: `当前状态: ${gatewayStatus}。消息投递可能受影响。`,
        fix_suggestions: [
          "检查 Gateway 服务状态",
          "验证网络连接",
          "查看 Gateway 错误日志"
        ],
        related_page: "Gateway"
      });
    }

    // Financial System 检查
    if (financial?.required_gates?.some(gate => gate.status !== "ready")) {
      const failedGates = financial.required_gates.filter(gate => gate.status !== "ready");
      results.push({
        category: "Financial System",
        status: "warning",
        title: "金融系统门控未就绪",
        message: `${failedGates.length} 个门控需要配置: ${failedGates.map(g => g.name).join(", ")}`,
        fix_suggestions: failedGates.map(g => `配置 ${g.name}: ${g.detail || "查看文档"}`),
        related_page: "Financial Manager"
      });
    }

    return results;
  }, [payload, controlToken, providerStatus, mcpStatus, gatewayStatus, pluginStatus, financial]);

  function handleNavigate(page?: string) {
    if (!page) return;
    onOpenView(pageToView(page));
  }

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>运维与连接</span>
          <h1>Readiness / Health</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message || "ready"} />
          <button className="small-button" disabled={busy} onClick={() => refresh()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>Readiness</span>
              <h2>10-20 秒定位主要问题层</h2>
              <p>优先看 AI provider、gateway、plugins、MCP、financial system、mode-token 六个面，快速判断是配置、授权还是后端离线问题。</p>
            </div>
            <Activity size={22} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="AI Provider" value={providerStatus} status={providerStatus} />
            <MetricCard label="Gateway" value={gatewayStatus} status={gatewayStatus} />
            <MetricCard label="Plugins" value={pluginStatus} status={pluginStatus} />
            <MetricCard label="MCP" value={mcpStatus} status={mcpStatus} />
            <MetricCard label="Financial" value={financial?.status || "not_loaded"} status={financial?.status} />
            <MetricCard label="Mode / Token" value={modeTokenStatus === "ready" ? "ready" : "gated"} status={modeTokenStatus} />
          </div>

          {/* 健康诊断详情 */}
          {diagnosticResults.length > 0 && (
            <ReadinessDiagnostic
              results={diagnosticResults}
              onNavigate={handleNavigate}
            />
          )}

          {!controlToken.trim() && (
            <div className="notice warn">
              <AlertTriangle size={14} />
              <span>当前缺少 control token，Sessions、Gateway、插件、MCP 管理和 full mode 运维数据会被锁定。</span>
            </div>
          )}

          <div className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>系统摘要</span>
                  <h3>快速定位</h3>
                </div>
              </div>
              <div className="kv-grid">
                <span>Agent</span>
                <strong>{health?.status || "not_loaded"}</strong>
                <span>Toolset</span>
                <strong>{health?.tools?.toolset || hermesStatus?.evaluated_toolset || "finance_safe"}</strong>
                <span>Full mode</span>
                <strong>{health?.hermes?.full_mode_active ? "active" : health?.hermes?.full_mode_enabled ? "enabled" : "off"}</strong>
                <span>Control token</span>
                <strong>{health?.control?.token_configured ? "configured" : "missing"}</strong>
                <span>MCP auth missing</span>
                <strong>{payload?.mcp?.missing_auth_env_vars?.join(", ") || "-"}</strong>
                <span>Financial gates</span>
                <strong>{financial?.required_gates?.length || 0}</strong>
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>问题提示</span>
                  <h3>高优先级缺口</h3>
                </div>
              </div>
              <div className="mini-list">
                {!health?.status || health.status === "ok" || health.status === "healthy" ? null : (
                  <article>
                    <strong>Agent 连接异常</strong>
                    <p>先检查 endpoint、后端进程和健康检查。</p>
                  </article>
                )}
                {payload?.mcp?.missing_auth_env_vars?.length ? (
                  <article>
                    <strong>MCP 授权缺失</strong>
                    <p>{payload.mcp.missing_auth_env_vars.join(", ")}</p>
                  </article>
                ) : null}
                {!controlToken.trim() ? (
                  <article>
                    <strong>Control token 未填写</strong>
                    <p>full mode 管理面与审批流无法完整工作。</p>
                  </article>
                ) : null}
                {financial?.required_gates?.filter((item) => item.status !== "ready").map((item) => (
                  <article key={item.name}>
                    <strong>{item.name}</strong>
                    <p>{item.detail}</p>
                  </article>
                ))}
              </div>
            </section>
          </div>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>深度诊断</span>
                <h3>Hermes / Full console</h3>
              </div>
              <button className="small-button" disabled={busy} onClick={onRefreshHermes} type="button">
                <RefreshCw size={14} />
                刷新 full console
              </button>
            </div>
            <DiagnosticsPanel
              busy={busy}
              controlToken={controlToken}
              fullConsole={fullConsole}
              health={health}
              hermesStatus={hermesStatus}
              message={message}
              onRefresh={onRefreshHermes}
              parity={health?.hermes?.parity}
            />
          </section>

          <details className="raw-details">
            <summary>原始 readiness payload</summary>
            <JsonPanel value={{ payload, health, hermesStatus }} />
          </details>
        </div>
      </div>
    </section>
  );
}

function pageToView(page: string): MainView {
  const normalized = page.toLowerCase();
  if (normalized.includes("mcp") || normalized.includes("connector")) return "mcp-connectors";
  if (normalized.includes("gateway")) return "gateway";
  if (normalized.includes("tool") || normalized.includes("approval") || normalized.includes("intent")) return "tools-intents-approvals";
  if (normalized.includes("financial") || normalized.includes("finance")) return "financial-manager";
  if (normalized.includes("plugin") || normalized.includes("skill")) return "plugins-skills";
  if (normalized.includes("setting") || normalized.includes("connection") || normalized.includes("control token")) return "settings";
  return "readiness-health";
}
