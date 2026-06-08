import { Cable, FolderSync, MessageSquareWarning, RefreshCw, RotateCcw, Send } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { GatewayRetryPanel } from "../../components/GatewayRetryPanel";
import { JsonPanel, MetricCard, StatusBadge, compact, confirmAction, shortText } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  GatewayDaemonStatus,
  GatewayMessage as ApiGatewayMessage,
  GatewayPlatform,
} from "../../types";
import "../../components/AgentEnhancements.css";

interface RetryableGatewayMessage {
  message_id: string;
  status: "pending" | "sent" | "failed" | "retrying" | "error";
  content: string;
  error_message?: string;
  retry_count: number;
  created_at: string;
  last_retry_at?: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function gatewayStatusText(value: unknown): string {
  const record = asRecord(value);
  const nested = asRecord(record.data);
  return String(record.status || nested.status || record.object || "not_loaded");
}

function platformName(platform: GatewayPlatform, index: number): string {
  return String(platform.platform || platform.name || `platform-${index + 1}`);
}

function normalizeGatewayMessage(message: ApiGatewayMessage): RetryableGatewayMessage {
  const rawStatus = String(message.status || "pending").toLowerCase();
  const status: RetryableGatewayMessage["status"] =
    rawStatus === "sent" || rawStatus === "delivered"
      ? "sent"
      : rawStatus === "retrying"
        ? "retrying"
        : rawStatus === "error"
          ? "error"
          : rawStatus === "failed"
            ? "failed"
            : "pending";
  const id = String(message.message_id || message.id || message.created_at || "gateway-message");
  return {
    message_id: id,
    status,
    content: String(message.content || message.message || message.target || id),
    error_message: message.error_message || message.error || message.failure_reason || message.error_code || undefined,
    retry_count: Number(message.retry_count || 0),
    created_at: String(message.created_at || message.updated_at || "-"),
    last_retry_at: message.last_retry_at ? String(message.last_retry_at) : undefined,
  };
}

export function GatewayPage({
  endpoint,
  apiToken,
  controlToken,
  userId,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [gatewayStatus, setGatewayStatus] = useState<unknown>(null);
  const [daemonStatus, setDaemonStatus] = useState<GatewayDaemonStatus | null>(null);
  const [platforms, setPlatforms] = useState<GatewayPlatform[]>([]);
  const [platformHealth, setPlatformHealth] = useState<Record<string, unknown>>({});
  const [messages, setMessages] = useState<ApiGatewayMessage[]>([]);
  const [directory, setDirectory] = useState<Array<Record<string, unknown>>>([]);
  const [sendPlatform, setSendPlatform] = useState("local");
  const [sendTarget, setSendTarget] = useState("");
  const [sendMessage, setSendMessage] = useState("AIASK gateway delivery preview");
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [messageStatus, setMessageStatus] = useState("NOT_LOADED");

  const retryMessages = useMemo(() => messages.map(normalizeGatewayMessage), [messages]);
  const failedCount = retryMessages.filter((item) => ["failed", "error", "retrying", "pending"].includes(item.status)).length;
  const statusText = gatewayStatusText(gatewayStatus);
  const daemonRunning = Boolean(daemonStatus?.data?.running);
  const daemonEnabled = Boolean(daemonStatus?.data?.enabled);

  async function loadGatewayState() {
    setLoading(true);
    try {
      const [statusPayload, daemonPayload, platformPayload, messagePayload, directoryPayload] = await Promise.all([
        api.gatewayStatus(),
        api.gatewayDaemonStatus(),
        api.gatewayPlatforms(),
        api.gatewayMessages(undefined, 100),
        api.gatewayDirectory(undefined, undefined, 100),
      ]);
      setGatewayStatus(statusPayload);
      setDaemonStatus(daemonPayload);
      setPlatforms(platformPayload.data || []);
      setMessages(messagePayload.data || []);
      setDirectory(directoryPayload.data || []);
      setMessageStatus("GATEWAY_LOADED");
    } catch (error) {
      setMessageStatus(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }

  async function refreshDirectory() {
    if (!confirmAction("刷新 Gateway 目录", "将通过 Agent 请求重新同步目录。")) return;
    setLoading(true);
    try {
      const payload = await api.gatewayDirectoryRefresh();
      setResult(payload);
      const directoryPayload = await api.gatewayDirectory(undefined, undefined, 100);
      setDirectory(directoryPayload.data || []);
      setMessageStatus("GATEWAY_DIRECTORY_REFRESHED");
    } catch (error) {
      setMessageStatus(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }

  async function checkPlatformHealth(name: string) {
    setLoading(true);
    try {
      const payload = await api.gatewayPlatformHealth(name);
      setPlatformHealth((current) => ({ ...current, [name]: payload }));
      setResult(payload);
      setMessageStatus("GATEWAY_PLATFORM_HEALTH_OK");
    } catch (error) {
      setMessageStatus(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }

  async function retryMessage(messageId: string) {
    setMessageStatus("GATEWAY_RETRY_RUNNING");
    try {
      const payload = await api.gatewayMessageRetry(messageId);
      setResult(payload);
      setMessageStatus("GATEWAY_RETRY_OK");
      await loadGatewayState();
    } catch (error) {
      setMessageStatus(formatApiError(error));
    }
  }

  async function batchRetryMessages(messageIds: string[]) {
    setMessageStatus("GATEWAY_BATCH_RETRY_RUNNING");
    try {
      const payloads = await Promise.all(messageIds.map((id) => api.gatewayMessageRetry(id)));
      setResult(payloads);
      setMessageStatus("GATEWAY_BATCH_RETRY_OK");
      await loadGatewayState();
    } catch (error) {
      setMessageStatus(formatApiError(error));
    }
  }

  async function createSendIntent(event: FormEvent) {
    event.preventDefault();
    if (!confirmAction("创建 Gateway 发送审批", `Platform: ${sendPlatform}\nTarget: ${sendTarget}`)) return;
    setLoading(true);
    setMessageStatus("GATEWAY_INTENT_CREATING");
    try {
      const payload = await api.gatewaySendIntent({
        platform: sendPlatform,
        target: sendTarget,
        message: sendMessage,
        user_id: userId,
      });
      setResult(payload);
      setMessageStatus(payload.success ? "GATEWAY_INTENT_CREATED" : payload.error || "GATEWAY_INTENT_FAILED");
    } catch (error) {
      setMessageStatus(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadGatewayState().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controlToken, endpoint]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>运维与连接</span>
          <h1>Gateway</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label={controlToken.trim() ? "control ready" : "control token required"} />
          <StatusBadge status={messageStatus.startsWith("GATEWAY_") ? "ready" : messageStatus} label={messageStatus} />
          <button className="small-button" disabled={loading} onClick={loadGatewayState} type="button">
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>Platform Gateway</span>
              <h2>平台健康、守护进程、目录、消息与重试</h2>
              <p>消息发送只创建 ActionIntent，投递仍等待审批确认。</p>
            </div>
            <Cable size={22} />
          </div>

          {!controlToken.trim() && (
            <div className="notice warn">Gateway 管理详情需要 Control token；发送预览不会绕过 ActionIntent 审批链路。</div>
          )}

          <div className="diagnostics-summary wide">
            <MetricCard label="Gateway" value={statusText} status={statusText} />
            <MetricCard label="Daemon" value={daemonRunning ? "running" : daemonStatus ? "stopped" : "not_loaded"} status={daemonRunning ? "ready" : daemonStatus ? "disabled" : "not_loaded"} />
            <MetricCard label="Platforms" value={platforms.length} status={platforms.length ? "ready" : "not_loaded"} />
            <MetricCard label="Messages" value={messages.length} status={messages.length ? "ready" : "not_loaded"} />
            <MetricCard label="Failed Retry" value={failedCount} status={failedCount ? "failed" : "ready"} />
            <MetricCard label="Directory" value={directory.length} status={directory.length ? "ready" : "not_loaded"} />
          </div>

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{daemonEnabled ? "enabled" : "disabled"}</span>
                  <h3>Daemon status</h3>
                </div>
                <StatusBadge status={daemonRunning ? "ready" : "disabled"} label={daemonRunning ? "running" : "stopped"} />
              </div>
              <div className="kv-grid">
                <span>Enabled</span>
                <strong>{String(daemonStatus?.data?.enabled ?? "unknown")}</strong>
                <span>Running</span>
                <strong>{String(daemonStatus?.data?.running ?? "unknown")}</strong>
                <span>Listeners</span>
                <strong>{Object.keys(daemonStatus?.data?.listeners || {}).length}</strong>
                <span>Status</span>
                <strong>{statusText}</strong>
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{platforms.length} platforms</span>
                  <h3>Platform health</h3>
                </div>
              </div>
              <div className="mini-list">
                {platforms.map((platform, index) => {
                  const name = platformName(platform, index);
                  const health = asRecord(platformHealth[name]);
                  const healthData = asRecord(health.data);
                  return (
                    <article className="job-row" key={name}>
                      <div>
                        <strong>{name}</strong>
                        <span>{compact(platform.status || (platform.enabled ? "enabled" : "unknown"))}</span>
                        {platform.missing_env?.length ? <p>missing: {platform.missing_env.join(", ")}</p> : null}
                        {platformHealth[name] ? <p>health: {compact(healthData.status || health.status || health.object)}</p> : null}
                      </div>
                      <button className="small-button" disabled={loading || !controlToken.trim()} onClick={() => checkPlatformHealth(name)} type="button">
                        健康
                      </button>
                    </article>
                  );
                })}
                {!platforms.length && <p className="muted">暂无平台状态。</p>}
              </div>
            </div>

            <form className="capability-section" onSubmit={createSendIntent}>
              <div className="section-header">
                <div>
                  <span>intent only</span>
                  <h3>Message send preview</h3>
                </div>
                <StatusBadge status="gated" label="approval required" />
              </div>
              <label className="field-row">
                <span>平台</span>
                <input value={sendPlatform} onChange={(event) => setSendPlatform(event.target.value)} />
              </label>
              <label className="field-row">
                <span>目标</span>
                <input value={sendTarget} onChange={(event) => setSendTarget(event.target.value)} placeholder="channel/user/room" />
              </label>
              <label className="field-row">
                <span>消息</span>
                <textarea value={sendMessage} onChange={(event) => setSendMessage(event.target.value)} />
              </label>
              <button className="primary-button" disabled={loading || !sendTarget.trim() || !sendMessage.trim()} type="submit">
                <Send size={14} />
                创建发送审批
              </button>
            </form>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{directory.length} entries</span>
                  <h3>Directory refresh</h3>
                </div>
                <button className="small-button" disabled={loading || !controlToken.trim()} onClick={refreshDirectory} type="button">
                  <FolderSync size={13} />
                  刷新目录
                </button>
              </div>
              <div className="mini-list">
                {directory.slice(0, 8).map((item, index) => (
                  <article key={`${item.platform || "directory"}:${item.id || index}`}>
                    <strong>{compact(item.display_name || item.id || item.name || `entry-${index + 1}`)}</strong>
                    <span>{compact(item.platform || "-")} / {compact(item.kind || "-")}</span>
                  </article>
                ))}
                {!directory.length && <p className="muted">暂无目录项。</p>}
              </div>
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{messages.length} messages</span>
                <h3>Messages</h3>
              </div>
              <MessageSquareWarning size={18} />
            </div>
            <div className="data-table">
              <div className="table-head">
                <span>message</span>
                <span>platform</span>
                <span>status</span>
                <span>error</span>
              </div>
              {messages.slice(0, 10).map((message, index) => {
                const normalized = normalizeGatewayMessage(message);
                return (
                  <div className="table-row" key={normalized.message_id || index}>
                    <strong>{normalized.message_id}</strong>
                    <span>{message.platform || "-"}</span>
                    <span>{normalized.status}</span>
                    <span>{shortText(String(normalized.error_message || message.target || "-"), 64)}</span>
                  </div>
                );
              })}
              {!messages.length && <div className="table-empty">No gateway messages loaded.</div>}
            </div>
          </section>

          {controlToken.trim() && (
            <GatewayRetryPanel
              messages={retryMessages}
              onRetry={retryMessage}
              onBatchRetry={batchRetryMessages}
            />
          )}

          <details className="raw-details">
            <summary>Gateway raw payloads</summary>
            <JsonPanel value={{ gatewayStatus, daemonStatus, platforms, platformHealth, messages, directory, result }} />
          </details>

          <div className="notice info compact">
            <RotateCcw size={13} />
            <span>Failed retry calls `/v1/gateway/messages/:id/retry`; message send preview creates `gateway.send_message` ActionIntent only.</span>
          </div>
        </div>
      </div>
    </section>
  );
}
