import { RefreshCw, XCircle, Clock, AlertTriangle } from "lucide-react";
import { useState } from "react";
import { StatusBadge } from "./shared";

interface GatewayMessage {
  message_id: string;
  status: "pending" | "sent" | "failed" | "retrying" | "error";
  content: string;
  error_message?: string;
  retry_count: number;
  created_at: string;
  last_retry_at?: string;
}

interface GatewayRetryPanelProps {
  messages: GatewayMessage[];
  onRetry: (messageId: string) => Promise<void>;
  onBatchRetry: (messageIds: string[]) => Promise<void>;
}

export function GatewayRetryPanel({ messages, onRetry, onBatchRetry }: GatewayRetryPanelProps) {
  const [selectedMessages, setSelectedMessages] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  const failedMessages = messages.filter((msg) => ["failed", "error", "retrying", "pending"].includes(msg.status));

  async function handleRetry(messageId: string) {
    setBusy(true);
    try {
      await onRetry(messageId);
    } finally {
      setBusy(false);
    }
  }

  async function handleBatchRetry() {
    if (selectedMessages.size === 0) return;
    setBusy(true);
    try {
      await onBatchRetry(Array.from(selectedMessages));
      setSelectedMessages(new Set());
    } finally {
      setBusy(false);
    }
  }

  function toggleSelection(messageId: string) {
    const newSelection = new Set(selectedMessages);
    if (newSelection.has(messageId)) {
      newSelection.delete(messageId);
    } else {
      newSelection.add(messageId);
    }
    setSelectedMessages(newSelection);
  }

  return (
    <div className="gateway-retry-panel">
      <div className="panel-header">
        <h4>失败消息 ({failedMessages.length})</h4>
        {selectedMessages.size > 0 && (
          <button
            className="small-button"
            disabled={busy}
            onClick={handleBatchRetry}
            type="button"
          >
            <RefreshCw size={13} className={busy ? "spin" : ""} />
            批量重试 ({selectedMessages.size})
          </button>
        )}
      </div>

      {failedMessages.length === 0 ? (
        <p className="muted">暂无失败消息。</p>
      ) : (
        <div className="message-list">
          {failedMessages.map((msg) => (
            <div key={msg.message_id} className="message-card">
              <div className="message-card-header">
                <input
                  type="checkbox"
                  checked={selectedMessages.has(msg.message_id)}
                  onChange={() => toggleSelection(msg.message_id)}
                />
                <strong>{msg.message_id}</strong>
                <StatusBadge status={msg.status} label={msg.status} />
              </div>

              <div className="message-content">
                <p>{msg.content.slice(0, 200)}</p>
              </div>

              {msg.error_message && (
                <div className="message-error">
                  <XCircle size={13} />
                  <span>{msg.error_message}</span>
                </div>
              )}

              <div className="message-meta">
                <span><Clock size={12} /> 创建: {msg.created_at}</span>
                <span><AlertTriangle size={12} /> 重试次数: {msg.retry_count}</span>
                {msg.last_retry_at && <span>最后重试: {msg.last_retry_at}</span>}
              </div>

              <button
                className="small-button"
                disabled={busy}
                onClick={() => handleRetry(msg.message_id)}
                type="button"
              >
                <RefreshCw size={13} />
                重试
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
