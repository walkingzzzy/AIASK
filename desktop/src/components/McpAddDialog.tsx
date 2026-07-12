import { Plus, X } from "lucide-react";
import { useState } from "react";
import { Button } from "./ui";

interface McpAddDialogProps {
  onAdd: (data: { name: string; command: string; args?: string[]; env?: Record<string, string> }) => Promise<void>;
  onClose: () => void;
}

export function McpAddDialog({ onAdd, onClose }: McpAddDialogProps) {
  const [form, setForm] = useState({
    name: "",
    command: "",
    args: "",
    env: ""
  });
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    if (!form.name.trim() || !form.command.trim()) return;

    setBusy(true);
    try {
      const args = form.args ? form.args.split(",").map(s => s.trim()).filter(Boolean) : undefined;
      const env = form.env ? JSON.parse(form.env) : undefined;

      await onAdd({
        name: form.name,
        command: form.command,
        args,
        env
      });
      onClose();
    } catch (error) {
      console.error("添加 MCP 服务失败:", error);
      alert(`添加失败：${error}`);
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
            <Plus size={20} />
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>添加 MCP 服务</h2>
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
                服务名称 <span style={{ color: "#ef4444" }}>*</span>
              </span>
              <input
                data-testid="mcp-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="例如：stock-data"
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
                命令 <span style={{ color: "#ef4444" }}>*</span>
              </span>
              <input
                data-testid="mcp-command"
                value={form.command}
                onChange={(e) => setForm({ ...form, command: e.target.value })}
                placeholder="例如：node"
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
                参数（用逗号分隔，可选）
              </span>
              <input
                data-testid="mcp-args"
                value={form.args}
                onChange={(e) => setForm({ ...form, args: e.target.value })}
                placeholder="例如：./server.js, --port=3000"
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem"
                }}
              />
              <small style={{ fontSize: "0.75rem", color: "#6b7280" }}>多个参数请用逗号分隔。</small>
            </label>

            <label className="field">
              <span style={{ fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem", display: "block" }}>
                环境变量（JSON 格式，可选）
              </span>
              <textarea
                data-testid="mcp-env"
                value={form.env}
                onChange={(e) => setForm({ ...form, env: e.target.value })}
                placeholder='{"API_KEY": "your-key", "DEBUG": "true"}'
                rows={3}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem",
                  resize: "vertical",
                  fontFamily: "monospace"
                }}
              />
              <small style={{ fontSize: "0.75rem", color: "#6b7280" }}>请填写 JSON 格式的键值对，敏感信息会在页面中隐藏。</small>
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
            data-testid="mcp-submit"
            onClick={() => void handleSubmit()}
            tone="success"
            disabled={!form.name.trim() || !form.command.trim() || busy}
            busy={busy}
          >
            添加服务
          </Button>
        </div>
      </div>
    </div>
  );
}

interface McpAddButtonProps {
  onAdd: (data: { name: string; command: string; args?: string[]; env?: Record<string, string> }) => Promise<void>;
}

export function McpAddButton({ onAdd }: McpAddButtonProps) {
  const [showDialog, setShowDialog] = useState(false);

  return (
    <>
      <Button
        data-testid="add-mcp-button"
        onClick={() => setShowDialog(true)}
        tone="success"
        icon={<Plus size={16} />}
      >
        添加 MCP 服务
      </Button>
      {showDialog && (
        <McpAddDialog
          onAdd={onAdd}
          onClose={() => setShowDialog(false)}
        />
      )}
    </>
  );
}
