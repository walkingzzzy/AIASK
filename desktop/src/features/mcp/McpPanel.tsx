import { useEffect, useMemo, useState } from "react";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload } from "../../types";
import { JsonPanel, StatusBadge, compact, shortText } from "../../components/shared";

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
  return typeof value === "string" ? value : "Action completed.";
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
  return (
    <div className={`notice ${success ? "ok" : "warn"}`}>
      <strong>{String(record.error_code || record.object || status)}</strong>
      <span>{shortText(detail, 220)}</span>
      {!!missingAuthEnvVars.length && <span>Set env vars: {missingAuthEnvVars.join(", ")}</span>}
      {record.error_code === "MCP_DISCOVERY_AUTH_REQUIRED" && !missingAuthEnvVars.length && (
        <span>Check the MCP server authorization configuration in the Agent process.</span>
      )}
      <div className="kv-grid">
        <span>Success</span>
        <strong>{String(record.success ?? "-")}</strong>
        <span>Configured</span>
        <strong>{compact(data?.configured)}</strong>
        <span>Server</span>
        <strong>{compact(data?.server || record.server)}</strong>
        <span>Auth env</span>
        <strong>{authEnvVars.length ? authEnvVars.join(", ") : "-"}</strong>
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

  if (!mcp) return <p className="muted">Refresh capabilities to load MCP state.</p>;
  const registrationStatus = mcp.registration_status || (mcp.servers.length ? "registered" : "not_registered");
  const discoveryStatus = mcp.discovery_status || registrationStatus;
  const registrationReady = registrationStatus === "registered";
  const authEnvVars = Array.isArray(mcp.auth_env_vars) ? mcp.auth_env_vars : [];
  const missingAuthEnvVars = Array.isArray(mcp.missing_auth_env_vars) ? mcp.missing_auth_env_vars : [];
  const discoveredCounts = mcp.discovered_counts || {};
  const discoverySummary = `${discoveredCounts.tools ?? mcp.tools.length} tools / ${discoveredCounts.resources ?? mcp.resources.length} resources / ${discoveredCounts.prompts ?? mcp.prompts.length} prompts`;
  const reviewItems = [
    { label: "Registration", value: registrationStatus, status: statusFor(registrationStatus) },
    { label: "Discovery", value: discoveryStatus, status: statusFor(discoveryStatus) },
    { label: "Auth", value: mcp.auth_configured === undefined ? "-" : mcp.auth_configured ? "configured" : "missing", status: mcp.auth_configured ? "implemented" : "unconfigured" },
    { label: "Discovered", value: discoverySummary, status: (discoveredCounts.tools ?? mcp.tools.length) ? "implemented" : "not_loaded" }
  ];

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>MCP</span>
          <h2>Connector review queue</h2>
          <p>
            {mcp.gated
              ? mcp.reason || "Control token required for tools/resources/prompts."
              : registrationReady
                ? "Full MCP runtime data loaded."
                : "MCP service may be running, but it is not registered with the AIASK aggregator."}
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
              `Configure AIASK_AGENT_MCP_CONFIG or ${mcp.config_path || "~/.aiask-agent/mcp_servers.json"} so Desktop can aggregate this MCP service.`}
          </span>
        </div>
      )}

      {registrationReady && !!missingAuthEnvVars.length && (
        <div className="notice warn">
          <strong>MCP auth env missing in backend process</strong>
          <span>AIASK is registered to this MCP server, but the running backend has not read these environment variables: {missingAuthEnvVars.join(", ")}</span>
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
          <span>Registration</span>
          <strong>{registrationStatus}</strong>
          <span>Discovery</span>
          <strong>{discoveryStatus}</strong>
          <span>Config path</span>
          <strong>{mcp.config_path || "-"}</strong>
          <span>Config exists</span>
          <strong>{String(mcp.config_exists ?? "-")}</strong>
          <span>Detected port</span>
          <strong>{mcp.detected_service_port || "-"}</strong>
          <span>Suggested URL</span>
          <strong>{mcp.suggested_registration_url || "-"}</strong>
          <span>Auth configured</span>
          <strong>{mcp.auth_configured === undefined ? "-" : String(mcp.auth_configured)}</strong>
          <span>Auth env</span>
          <strong>{authEnvVars.length ? authEnvVars.join(", ") : "-"}</strong>
          <span>Missing auth env</span>
          <strong>{missingAuthEnvVars.length ? missingAuthEnvVars.join(", ") : "-"}</strong>
          <span>Discovered</span>
          <strong>{discoverySummary}</strong>
        </div>
        <div className="inline-form">
          <input value={serverName} onChange={(event) => setServerName(event.target.value)} placeholder="MCP server name" />
          <button aria-label="Register local MCP server" disabled={busy || !controlToken.trim() || registrationReady} onClick={() => run("register")} title="Register local MCP server" type="button">Register local MCP</button>
          <button aria-label="Discover or refresh MCP server" disabled={busy || !controlToken.trim() || !(serverName || defaultServer).trim()} onClick={() => run("discover")} title="Discover or refresh MCP server" type="button">Discover/Refresh server</button>
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{mcp.servers.length} configured</span>
              <h3>Servers</h3>
            </div>
          </div>
          <div className="mini-list">
            {mcp.servers.map((server) => (
              <article key={String(server.name)}>
                <strong>{server.name}</strong>
                <span>{server.transport || "-"} / {server.domain || "general"}</span>
                <StatusBadge status={server.configured === false ? "unconfigured" : "implemented"} />
              </article>
            ))}
            {!mcp.servers.length && <p className="muted">No MCP servers configured.</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{mcp.tools.length} discovered</span>
              <h3>Dynamic Tools</h3>
            </div>
          </div>
          <div className="mini-list">
            {mcp.tools.map((tool) => (
              <article key={`${tool.server || ""}:${tool.name}`}>
                <strong>{tool.wrapped_name || tool.name}</strong>
                <span>{tool.server || "-"} / {tool.name}</span>
                <p>{tool.description || "No description."}</p>
              </article>
            ))}
            {!mcp.tools.length && <p className="muted">{mcp.gated ? "Unlock with control token to inspect MCP tools." : "No MCP tools discovered."}</p>}
          </div>
        </div>
      </section>

      <section className="capability-grid three">
        <div className="capability-section">
          <h3>Resources</h3>
          <div className="inline-form">
            <input value={resourceUri} onChange={(event) => setResourceUri(event.target.value)} placeholder="resource uri" />
            <button aria-label="Read MCP resource" disabled={busy || !controlToken.trim() || !resourceUri.trim() || !(serverName || defaultServer).trim()} onClick={() => run("resource")} title="Read MCP resource" type="button">Read</button>
          </div>
          <p className="muted">{mcp.resources.length} resources available</p>
        </div>
        <div className="capability-section">
          <h3>Prompts</h3>
          <div className="inline-form">
            <input value={promptName} onChange={(event) => setPromptName(event.target.value)} placeholder="prompt name" />
            <button aria-label="Get MCP prompt" disabled={busy || !controlToken.trim() || !promptName.trim() || !(serverName || defaultServer).trim()} onClick={() => run("prompt")} title="Get MCP prompt" type="button">Get</button>
          </div>
          <p className="muted">{mcp.prompts.length} prompts available</p>
        </div>
        <div className="capability-section">
          <h3>OAuth</h3>
          <div className="inline-form">
            <input value={oauthServer} onChange={(event) => setOauthServer(event.target.value)} placeholder="OAuth server name" />
            <button aria-label="Start MCP OAuth flow" disabled={busy || !controlToken.trim() || !oauthServer.trim()} onClick={() => run("oauth")} title="Start MCP OAuth flow" type="button">Start</button>
          </div>
          <p className="muted">{mcp.oauth.length} OAuth entries</p>
        </div>
      </section>

      {result !== null && <ActionResult result={result} />}
      <details className="raw-details" onToggle={(event) => setRawOpen(event.currentTarget.open)}>
        <summary>Raw action result</summary>
        {rawOpen && <JsonPanel value={result || { status: "no_action" }} />}
      </details>
    </div>
  );
}
