import { Plus, X } from "lucide-react";
import { useState } from "react";

import { Button } from "./ui";

interface SkillAddPayload {
  name: string;
  type: string;
  path: string;
  config?: Record<string, unknown>;
}

interface SkillAddDialogProps {
  onAdd: (data: SkillAddPayload) => Promise<void>;
  onClose: () => void;
}

export function SkillAddDialog({ onAdd, onClose }: SkillAddDialogProps) {
  const [form, setForm] = useState({
    name: "",
    type: "local",
    path: ""
  });
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    if (!form.name.trim() || !form.path.trim()) return;

    setBusy(true);
    try {
      await onAdd({
        name: form.name.trim(),
        type: form.type,
        path: form.path.trim()
      });
      onClose();
    } catch (error) {
      console.error("Add skill failed:", error);
      alert(`Add skill failed: ${error}`);
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
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="dialog-content"
        style={{
          background: "white",
          borderRadius: "0.5rem",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
          width: "90%",
          maxWidth: "560px",
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
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>Add Skill</h2>
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
                Name <span style={{ color: "#ef4444" }}>*</span>
              </span>
              <input
                data-testid="skill-name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="stock-analysis"
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
                Type
              </span>
              <select
                data-testid="skill-type"
                value={form.type}
                onChange={(event) => setForm({ ...form, type: event.target.value })}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem"
                }}
              >
                <option value="local">local</option>
                <option value="remote">remote</option>
              </select>
            </label>

            <label className="field">
              <span style={{ fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem", display: "block" }}>
                Path / URL <span style={{ color: "#ef4444" }}>*</span>
              </span>
              <input
                data-testid="skill-path"
                value={form.path}
                onChange={(event) => setForm({ ...form, path: event.target.value })}
                placeholder={form.type === "remote" ? "https://example.com/skill" : "C:/path/to/SKILL.md"}
                style={{
                  width: "100%",
                  padding: "0.5rem",
                  border: "1px solid #d1d5db",
                  borderRadius: "0.375rem"
                }}
              />
              <small style={{ fontSize: "0.75rem", color: "#6b7280" }}>
                Use a local file path for `local`, or a URL for `remote`.
              </small>
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
            Cancel
          </Button>
          <Button
            data-testid="skill-submit"
            onClick={() => void handleSubmit()}
            tone="success"
            disabled={!form.name.trim() || !form.path.trim() || busy}
            busy={busy}
          >
            Add Skill
          </Button>
        </div>
      </div>
    </div>
  );
}

interface SkillAddButtonProps {
  onAdd: (data: SkillAddPayload) => Promise<void>;
}

export function SkillAddButton({ onAdd }: SkillAddButtonProps) {
  const [showDialog, setShowDialog] = useState(false);

  return (
    <>
      <Button data-testid="add-skill-button" onClick={() => setShowDialog(true)} tone="success" icon={<Plus size={16} />}>
        Add Skill
      </Button>
      {showDialog ? <SkillAddDialog onAdd={onAdd} onClose={() => setShowDialog(false)} /> : null}
    </>
  );
}
