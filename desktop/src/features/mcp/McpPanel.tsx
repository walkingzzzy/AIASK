import { useEffect, useMemo, useState } from "react";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload } from "../../types";
import { JsonPanel, StatusBadge, compact, localizeBlockedReason, shortText } from "../../components/shared";
import { McpOAuthStatus } from "../../components/McpOAuthStatus";
import "../../components/AgentEnhancements.css";

function statusFor(value?: string): string {
  if (!value) return "not_loaded";
  if (["registered", "discovered", "configured"].includes(value)) return "implemented";
  if (["auth_missing", "not_registered"].includes(value)) return "unconfigured";
  return value;
}

function resultRecord(result: unknown): Record<string, unknown> | null {
  return result && typeof result === "object" && !Array.isArray(result) ? result as Record<string, unknown> : null;
}

function resultDetail(record: Record<string, unknown>, data: Record<string, unknown> | null): string {
  const nestedResult = resultRecord(data?.result);
  const candidates = [
    nestedResult?.text,
    data?.detail,
    data?.prompt,
    data?.status,
    record.detail,
    record.error
  ];
  const value = candidates.find((item) => typeof item === "string" && item.trim());
  return typeof value === "string" ? value : "操作已完成。";
}

function nestedArray(record: Record<string, unknown> | null, key: string): unknown[] {
  const direct = record?.[key];
  if (Array.isArray(direct)) return direct;
  const discovered = resultRecord(record?.discovered);
  const nested = discovered?.[key];
  return Array.isArray(nested) ? nested : [];
}

function ActionResult({ result }: { result: unknown }) {
  const record = resultRecord(result);
  if (!record) return null;
  const data = resultRecord(record.data);
  const success = record.success === true;
  const status = success ? "success" : "error";
  const detail = resultDetail(record, data);
  const missingAuthEnvVars = Array.isArray(data?.missing_auth_env_vars) ? data.missing_auth_env_vars.map(String) : [];
  const authEnvVars = Array.isArray(data?.auth_env_vars) ? data.auth_env_vars.map(String) : [];
  const warnings = nestedArray(data, "warnings");
  const unsupportedMethods = nestedArray(data, "unsupported_methods").map(String).filter(Boolean);
  return (
    <div className={`notice ${success ? "ok" : "warn"}`}>
      <strong>{String(record.error_code || record.object || status)}</strong>
      <span>{shortText(detail, 220)}</span>
      {!!missingAuthEnvVars.length && <span>请设置环境变量：{missingAuthEnvVars.join(", ")}</span>}
      {record.error_code === "MCP_DISCOVERY_AUTH_REQUIRED" && !missingAuthEnvVars.length && (
        <span>请检查 Agent 进程中的 MCP 服务授权配置。</span>
      )}
      {!!unsupportedMethods.length && <span>工具已发现，但这些 MCP 接口未实现：{unsupportedMethods.join(", ")}</span>}
      {!!warnings.length && !unsupportedMethods.length && <span>发现过程有非致命告警：{warnings.map((item) => compact(item)).join("; ")}</span>}
      <div className="kv-grid">
        <span>成功</span>
        <strong>{String(record.success ?? "-")}</strong>
        <span>已配置</span>
        <strong>{compact(data?.configured)}</strong>
        <span>服务</span>
        <strong>{compact(data?.server || record.server)}</strong>
        <span>Auth env</span>
        <strong>{authEnvVars.length ? authEnvVars.join(", ") : "-"}</strong>
        <span>Unsupported methods</span>
        <strong>{unsupportedMethods.length ? unsupportedMethods.join(", ") : "-"}</strong>
      </div>
    </div>
  );
}

export function McpPanel({
  payload,
  endpoint,
  apiToken,
  controlToken,
  onRefresh
}: {
  payload: CapabilityWorkbenchPayload | null;
  endpoint: string;
  apiToken: string;
  controlToken: string;
  onRefresh?: () => Promise<CapabilityWorkbenchPayload | null>;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const mcp = payload?.mcp;
  const defaultServer = String(mcp?.servers?.[0]?.name || "akshare-local");
  const [serverName, setServerName] = useState(defaultServer);
  const [resourceUri, setResourceUri] = useState("");
  const [promptName, setPromptName] = useState("");
  const [oauthServer, setOauthServer] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [rawOpen, setRawOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!mcp) return;
    const firstServer = String(mcp.servers?.[0]?.name || "akshare-local");
    const firstResource = mcp.resources?.[0] && typeof mcp.resources[0] === "object" ? String((mcp.resources[0] as Record<string, unknown>).uri || "") : "";
    const firstPrompt = mcp.prompts?.[0] && typeof mcp.prompts[0] === "object" ? String((mcp.prompts[0] as Record<string, unknown>).name || "") : "";
    const firstOauth = mcp.oauth?.[0] && typeof mcp.oauth[0] === "object" ? String((mcp.oauth[0] as Record<string, unknown>).server || firstServer) : firstServer;
    setServerName((current) => current || firstServer);
    setResourceUri((current) => current || firstResource);
    setPromptName((current) => current || firstPrompt);
    setOauthServer((current) => current || firstOauth);
  }, [mcp]);

  async function run(action: "register" | "discover" | "resource" | "prompt" | "oauth") {
    setBusy(true);
    setRawOpen(false);
    try {
      const selectedServer = (serverName || defaultServer).trim();
      if (action === "register") {
        setResult(await api.mcpRegisterLocal({ name: selectedServer, url: mcp?.suggested_registration_url || undefined }));
        await onRefresh?.();
      }
      if (action === "discover") {
        setResult(await api.mcpDiscover(selectedServer));
        await onRefresh?.();
      }
      if (action === "resource") setResult(await api.mcpResourceRead(resourceUri, selectedServer));
      if (action === "prompt") setResult(await api.mcpPromptGet(promptName, {}, selectedServer));
      if (action === "oauth") setResult(await api.mcpOauthStart(oauthServer || selectedServer));
    } catch (error) {
      setResult({ success: false, error: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  }

  async function handleReauthorize(server: string) {
    setBusy(true);
    try {
      setResult(await api.mcpOauthStart(server));
      await onRefresh?.();
    } catch (error) {
      setResult({ success: false, error: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  }

  // 构造 OAuth 服务器状态数据
  const oauthServers = useMemo(() => {
    if (!mcp?.oauth || !Array.isArray(mcp.oauth)) return [];

    return mcp.oauth.map((item: any) => {
      const server = String(item.server || item.name || "");
      const authenticated = item.authenticated === true || item.status === "authenticated";
      const expired = item.expired === true || item.status === "expired";

      let status: "authenticated" | "expired" | "missing" | "error";
      if (item.error) {
        status = "error";
      } else if (authenticated) {
        status = "authenticated";
      } else if (expired) {
        status = "expired";
      } else {
        status = "missing";
      }

      return {
        server,
        status,
        expires_at: item.expires_at,
        last_auth_at: item.last_auth_at || item.authenticated_at,
        error_message: item.error
      };
    });
  }, [mcp?.oauth]);

  if (!mcp) return <p className="muted">请刷新能力中心以加载 MCP 状态。</p>;
  const registrationStatus = mcp.registration_status || (mcp.servers.length ? "registered" : "not_registered");
  const discoveryStatus = mcp.discovery_status || registrationStatus;
  const registrationReady = registrationStatus === "registered";
  const authEnvVars = Array.isArray(mcp.auth_env_vars) ? mcp.auth_env_vars : [];
  const missingAuthEnvVars = Array.isArray(mcp.missing_auth_env_vars) ? mcp.missing_auth_env_vars : [];
  const discoveredCounts = mcp.discovered_counts || {};
  const discoverySummary = `${discoveredCounts.tools ?? mcp.tools.length} 个工具 / ${discoveredCounts.resources ?? mcp.resources.length} 个资源 / ${discoveredCounts.prompts ?? mcp.prompts.length} 个提示词`;
  const serverWarnings = mcp.servers.flatMap((server) => Array.isArray(server.warnings) ? server.warnings : []);
  const warnings = [...(Array.isArray(mcp.warnings) ? mcp.warnings : []), ...serverWarnings];
  const unsupportedMethods = [
    ...(Array.isArray(mcp.unsupported_methods) ? mcp.unsupported_methods : []),
    ...mcp.servers.flatMap((server) => Array.isArray(server.unsupported_methods) ? server.unsupported_methods : [])
  ].map(String).filter(Boolean);
  const uniqueUnsupportedMethods = Array.from(new Set(unsupportedMethods));
  const partialDiscovery = Boolean(
    mcp.partial_success ||
    warnings.length ||
    uniqueUnsupportedMethods.length ||
    mcp.servers.some((server) => server.partial_success)
  );
  const reviewItems = [
    { label: "Partial", value: partialDiscovery ? "yes" : "no", status: partialDiscovery ? "partial" : "implemented" },
    { label: "注册", value: registrationStatus, status: statusFor(registrationStatus) },
    { label: "发现", value: discoveryStatus, status: statusFor(discoveryStatus) },
    { label: "授权", value: mcp.auth_configured === undefined ? "-" : mcp.auth_configured ? "已配置" : "缺失", status: mcp.auth_configured ? "implemented" : "unconfigured" },
    { label: "已发现", value: discoverySummary, status: (discoveredCounts.tools ?? mcp.tools.length) ? "implemented" : "not_loaded" }
  ];

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>MCP</span>
          <h2>连接器评审队列</h2>
          <p>
            {mcp.gated
              ? localizeBlockedReason(mcp.reason) || "工具、资源和提示词操作需要控制令牌。"
              : registrationReady
                ? "完整 MCP 运行时数据已加载。"
                : "MCP 服务可能已经运行，但尚未注册到 AIASK 聚合器。"}
          </p>
        </div>
        <StatusBadge
          status={mcp.gated ? "gated" : discoveryStatus === "discovered" ? "implemented" : discoveryStatus === "auth_missing" ? "unconfigured" : registrationReady ? "partial" : "unconfigured"}
          label={mcp.gated ? "gated" : discoveryStatus === "discovered" ? "discovered" : discoveryStatus}
        />
      </div>

      {!registrationReady && (
        <div className="notice warn">
          <strong>{mcp.error_code || registrationStatus}</strong>
          <span>
            {mcp.detail ||
              `请配置 AIASK_AGENT_MCP_CONFIG 或 ${mcp.config_path || "~/.aiask-agent/mcp_servers.json"}，让 Desktop 能聚合此 MCP 服务。`}
          </span>
        </div>
      )}

      {registrationReady && !!missingAuthEnvVars.length && (
        <div className="notice warn">
          <strong>后端进程缺少 MCP 授权环境变量</strong>
          <span>AIASK 已注册此 MCP 服务，但当前运行的后端尚未读取这些环境变量：{missingAuthEnvVars.join(", ")}</span>
        </div>
      )}

      {registrationReady && partialDiscovery && (
        <div className="notice warn">
          <strong>Partial MCP discovery</strong>
          <span>
            {uniqueUnsupportedMethods.length
              ? `Tools discovered, unsupported MCP methods: ${uniqueUnsupportedMethods.join(", ")}`
              : `Tools discovered with non-fatal warnings: ${warnings.length}`}
          </span>
        </div>
      )}

      <div className="capability-section compact-section">
        <div className="connector-review-grid">
          {reviewItems.map((item) => (
            <article key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <StatusBadge status={item.status} />
            </article>
          ))}
        </div>
        <div className="kv-grid">
          <span>注册</span>
          <strong>{registrationStatus}</strong>
          <span>发现</span>
          <strong>{discoveryStatus}</strong>
          <span>配置路径</span>
          <strong>{mcp.config_path || "-"}</strong>
          <span>配置存在</span>
          <strong>{String(mcp.config_exists ?? "-")}</strong>
          <span>检测端口</span>
          <strong>{mcp.detected_service_port || "-"}</strong>
          <span>建议 URL</span>
          <strong>{mcp.suggested_registration_url || "-"}</strong>
          <span>授权已配置</span>
          <strong>{mcp.auth_configured === undefined ? "-" : String(mcp.auth_configured)}</strong>
          <span>Auth env</span>
          <strong>{authEnvVars.length ? authEnvVars.join(", ") : "-"}</strong>
          <span>缺失授权环境变量</span>
          <strong>{missingAuthEnvVars.length ? missingAuthEnvVars.join(", ") : "-"}</strong>
          <span>已发现</span>
          <strong>{discoverySummary}</strong>
          <span>Unsupported methods</span>
          <strong>{uniqueUnsupportedMethods.length ? uniqueUnsupportedMethods.join(", ") : "-"}</strong>
        </div>
        <div className="inline-form">
          <input value={serverName} onChange={(event) => setServerName(event.target.value)} placeholder="MCP 服务名称" />
          <button aria-label="注册本地 MCP 服务" disabled={busy || !controlToken.trim() || registrationReady} onClick={() => run("register")} title="注册本地 MCP 服务" type="button">注册本地 MCP</button>
          <button aria-label="发现或刷新 MCP 服务" disabled={busy || !controlToken.trim() || !(serverName || defaultServer).trim()} onClick={() => run("discover")} title="发现或刷新 MCP 服务" type="button">发现/刷新服务</button>
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{mcp.servers.length} 个已配置</span>
              <h3>服务</h3>
            </div>
          </div>
          <div className="mini-list">
            {mcp.servers.map((server) => (
              <article key={String(server.name)}>
                <strong>{server.name}</strong>
                <span>{server.transport || "-"} / {server.domain || "general"}</span>
                {Array.isArray(server.unsupported_methods) && !!server.unsupported_methods.length && (
                  <span>unsupported: {server.unsupported_methods.map(String).join(", ")}</span>
                )}
                <StatusBadge status={server.configured === false ? "unconfigured" : "implemented"} />
              </article>
            ))}
            {!mcp.servers.length && <p className="muted">尚未配置 MCP 服务。</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{mcp.tools.length} 个已发现</span>
              <h3>动态工具</h3>
            </div>
          </div>
          <div className="mini-list">
            {mcp.tools.map((tool) => (
              <article key={`${tool.server || ""}:${tool.name}`}>
                <strong>{tool.wrapped_name || tool.name}</strong>
                <span>{tool.server || "-"} / {tool.name}</span>
                <p>{tool.description || "暂无描述。"}</p>
              </article>
            ))}
            {!mcp.tools.length && <p className="muted">{mcp.gated ? "请使用控制令牌解锁 MCP 工具查看权限。" : "尚未发现 MCP 工具。"}</p>}
          </div>
        </div>
      </section>

      <section className="capability-grid three">
        <div className="capability-section">
          <h3>资源</h3>
          <div className="inline-form">
            <input value={resourceUri} onChange={(event) => setResourceUri(event.target.value)} placeholder="资源 URI" />
            <button aria-label="读取 MCP 资源" disabled={busy || !controlToken.trim() || !resourceUri.trim() || !(serverName || defaultServer).trim()} onClick={() => run("resource")} title="读取 MCP 资源" type="button">读取</button>
          </div>
          <p className="muted">可用资源 {mcp.resources.length} 个</p>
        </div>
        <div className="capability-section">
          <h3>提示词</h3>
          <div className="inline-form">
            <input value={promptName} onChange={(event) => setPromptName(event.target.value)} placeholder="提示词名称" />
            <button aria-label="获取 MCP 提示词" disabled={busy || !controlToken.trim() || !promptName.trim() || !(serverName || defaultServer).trim()} onClick={() => run("prompt")} title="获取 MCP 提示词" type="button">获取</button>
          </div>
          <p className="muted">可用提示词 {mcp.prompts.length} 个</p>
        </div>
        <div className="capability-section">
          <h3>OAuth</h3>
          <div className="inline-form">
            <input value={oauthServer} onChange={(event) => setOauthServer(event.target.value)} placeholder="OAuth 服务名称" />
            <button aria-label="启动 MCP OAuth 流程" disabled={busy || !controlToken.trim() || !oauthServer.trim()} onClick={() => run("oauth")} title="启动 MCP OAuth 流程" type="button">启动</button>
          </div>
          <p className="muted">OAuth 条目 {mcp.oauth.length} 个</p>
        </div>
      </section>

      {/* OAuth 状态详情面板 */}
      {oauthServers.length > 0 && (
        <McpOAuthStatus
          oauthServers={oauthServers}
          onReauthorize={handleReauthorize}
        />
      )}

      {result !== null && <ActionResult result={result} />}
      <details className="raw-details" onToggle={(event) => setRawOpen(event.currentTarget.open)}>
        <summary>原始操作结果</summary>
        {rawOpen && <JsonPanel value={result || { status: "no_action" }} />}
      </details>
    </div>
  );
}
