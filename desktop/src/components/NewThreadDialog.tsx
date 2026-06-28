import { MessageSquarePlus, X } from "lucide-react";
import { useState } from "react";
import { Button } from "./ui";

interface NewThreadDialogProps {
  onCreateThread: (data: { title: string; description?: string; initial_context?: string }) => Promise<void>;
  onClose: () => void;
}

export function NewThreadDialog({ onCreateThread, onClose }: NewThreadDialogProps) {
  const [form, setForm] = useState({
    title: "",
    description: "",
    initial_context: ""
  });
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    if (!form.title.trim()) return;

    setBusy(true);
    try {
      await onCreateThread({
        title: form.title,
        description: form.description || undefined,
        initial_context: form.initial_context || undefined
      });
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="dialog-overlay"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="dialog-content"
        style={{
          background: "white",
          borderRadius: "0.5rem",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
          width: "90%",
          maxWidth: "500px",
          maxHeight: "90vh",
          overflow: "auto"
        }}
      >
        <div
          className="dialog-header"
          style={{
            padding: "1rem 1.5rem",
            borderBottom: "1px solid #e5e7eb",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <MessageSquarePlus size={20} />
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>新建对话</h2>
          </div>
          <button
            onClick={onClose}
            style={{
              border: "none",
              background: "transparent",
              cursor: "pointer",
              padding: "0.25rem",
              display: "flex",
              alignItems: "center"
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div className="dialog-body" style={{ padding: "1.5rem" }}>
          <div className="form-grid" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <label className="field">
              <span style={{ fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem", display: "block" }}>
                对话标题 <span style={{ color: "#ef4444" }}>*</span>
              </span>
              <input
                data-testid="new-thread-title"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="例如：分析茅台股票"
                autoFocus
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem"
                }}
              />
            </label>

            <label className="field">
              <span style={{ fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem", display: "block" }}>
                描述（可选）
              </span>
              <input
                data-testid="new-thread-description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="简要说明对话目的"
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem"
                }}
              />
            </label>

            <label className="field">
              <span style={{ fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem", display: "block" }}>
                初始上下文（可选）
              </span>
              <textarea
                data-testid="new-thread-context"
                value={form.initial_context}
                onChange={(e) => setForm({ ...form, initial_context: e.target.value })}
                placeholder="提供背景信息或特殊要求"
                rows={3}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem",
                  resize: "vertical"
                }}
              />
            </label>
          </div>
        </div>

        <div
          className="dialog-footer"
          style={{
            padding: "1rem 1.5rem",
            borderTop: "1px solid #e5e7eb",
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.5rem"
          }}
        >
          <Button onClick={onClose} tone="neutral" disabled={busy}>
            取消
          </Button>
          <Button
            data-testid="new-thread-submit"
            onClick={() => void handleSubmit()}
            tone="success"
            disabled={!form.title.trim() || busy}
            busy={busy}
          >
            创建对话
          </Button>
        </div>
      </div>
    </div>
  );
}

interface NewThreadButtonProps {
  onCreateThread: (data: { title: string; description?: string; initial_context?: string }) => Promise<void>;
}

export function NewThreadButton({ onCreateThread }: NewThreadButtonProps) {
  const [showDialog, setShowDialog] = useState(false);

  return (
    <>
      <Button
        data-testid="new-thread-button"
        onClick={() => setShowDialog(true)}
        tone="success"
        icon={<MessageSquarePlus size={16} />}
      >
        新建对话
      </Button>
      {showDialog && (
        <NewThreadDialog
          onCreateThread={onCreateThread}
          onClose={() => setShowDialog(false)}
        />
      )}
    </>
  );
}
