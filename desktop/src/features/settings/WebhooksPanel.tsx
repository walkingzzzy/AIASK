import { RefreshCw, Trash2, Webhook } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, confirmAction } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { WebhookSubscription } from "../../types";

export function WebhooksPanel({ apiToken, controlToken, endpoint }: { apiToken: string; controlToken: string; endpoint: string }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [items, setItems] = useState<WebhookSubscription[]>([]);
  const [name, setName] = useState("codex-mcp-test-webhook");
  const [events, setEvents] = useState("MCP UI smoke test");
  const [prompt, setPrompt] = useState("收到事件 {event}: {payload}");
  const [selectedId, setSelectedId] = useState("");
  const [triggerEvent, setTriggerEvent] = useState("MCP UI smoke test");
  const [triggerPayload, setTriggerPayload] = useState("{\"source\":\"desktop\"}");
  const [result, setResult] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.webhooksList();
      setItems(payload.data || []);
      setSelectedId((current) => current || payload.data?.[0]?.webhook_id || "");
      setMessage("WEBHOOKS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = await api.webhookCreate({
        name,
        events: events.split(",").map((item) => item.trim()).filter(Boolean),
        prompt,
        deliver: "desktop_inbox"
      });
      setResult(payload);
      setMessage("WEBHOOK_CREATED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function remove(webhookId: string) {
    if (!confirmAction("删除 Webhook 订阅", `Webhook: ${webhookId}`)) return;
    setBusy(true);
    try {
      setResult(await api.webhookDelete(webhookId));
      setMessage("WEBHOOK_DELETED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function triggerIntent() {
    setBusy(true);
    try {
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(triggerPayload || "{}");
      } catch {
        payload = { raw: triggerPayload };
      }
      const envelope = await api.webhookTriggerIntent(selectedId, { event: triggerEvent, payload });
      setResult(envelope);
      setMessage(envelope.success ? "WEBHOOK_TRIGGER_INTENT_CREATED" : envelope.error || "WEBHOOK_TRIGGER_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <Webhook size={20} />
          <span>Webhook</span>
          <h2>订阅与受控触发</h2>
          <p>订阅管理是真实写入；触发动作默认只创建审批意图，确认后才执行。</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      <section className="capability-grid two">
        <form className="capability-section" onSubmit={create}>
          <div className="section-header"><h3>创建订阅</h3></div>
          <label className="field-row"><span>名称</span><input value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label className="field-row"><span>事件</span><input value={events} onChange={(event) => setEvents(event.target.value)} /></label>
          <label className="field-row"><span>提示词模板</span><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label>
          <button className="primary-button" disabled={busy || !name.trim() || !prompt.trim()} type="submit">创建 Webhook</button>
        </form>

        <section className="capability-section">
          <div className="section-header">
            <h3>触发预览</h3>
            <StatusBadge status="gated" label="需审批" />
          </div>
          <label className="field-row">
            <span>Webhook</span>
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              <option value="">请选择</option>
              {items.map((item) => <option key={item.webhook_id} value={item.webhook_id}>{item.name}</option>)}
            </select>
          </label>
          <label className="field-row"><span>事件名</span><input value={triggerEvent} onChange={(event) => setTriggerEvent(event.target.value)} /></label>
          <label className="field-row"><span>Payload JSON</span><textarea value={triggerPayload} onChange={(event) => setTriggerPayload(event.target.value)} /></label>
          <button className="primary-button" disabled={busy || !selectedId} onClick={triggerIntent} type="button">创建触发审批</button>
        </section>
      </section>

      <section className="capability-section">
        <div className="section-header"><h3>订阅列表</h3><StatusBadge status={items.length ? "ready" : "not_loaded"} label={`${items.length} 个`} /></div>
        <div className="mini-list">
          {items.map((item) => (
            <article className="job-row" key={item.webhook_id}>
              <div>
                <strong>{item.name}</strong>
                <span>{compact(item.events?.join(", ") || "all")} | {item.enabled ? "已启用" : "已停用"}</span>
              </div>
              <button className="small-button danger" disabled={busy} onClick={() => remove(item.webhook_id)} type="button">
                <Trash2 size={13} />
                删除
              </button>
            </article>
          ))}
          {!items.length && <p className="muted">暂无 Webhook 订阅。</p>}
        </div>
      </section>

      <details className="raw-details">
        <summary>最近结果</summary>
        <JsonPanel value={result || { status: "no_action" }} />
      </details>
    </div>
  );
}
