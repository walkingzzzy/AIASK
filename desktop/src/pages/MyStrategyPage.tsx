import { Edit2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { DraggableDataTable } from "../components/DraggableDataTable";
import { StatusLight } from "../components/StatusLight";
import { Button, EmptyState, PageShell, Panel } from "../components/ui";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { list, metric, valueOf } from "./pageUtils";
import type { PageProps } from "./pageUtils";

export function MyStrategyPage({ api, controlAvailable }: PageProps) {
  const strategies = useAsyncResource(() => api.userStrategies(), [api]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    type: "momentum",
    stocks: "",
    description: ""
  });

  // 按 sort_order 排序;后端 reorder 接口接收完整 ordered_ids,按数组下标写 sort_order
  const orderedStrategies = useMemo(() => {
    const items = list(strategies.data);
    return [...items].sort((a, b) => {
      const sa = Number(a.sort_order ?? 0);
      const sb = Number(b.sort_order ?? 0);
      if (sa !== sb) return sa - sb;
      return String(a.id || "").localeCompare(String(b.id || ""));
    });
  }, [strategies.data]);

  const strategyRows = orderedStrategies.map((item) => {
    const performance = item.performance as { return?: number; sharpe?: number } | undefined;
    return {
      id: String(item.id || ""),
      name: valueOf(item, ["name"], "Untitled strategy"),
      type: valueOf(item, ["type"], "custom"),
      stocks_count: Array.isArray(item.stocks) ? item.stocks.length : 0,
      return: performance?.return ? `${(performance.return * 100).toFixed(2)}%` : "-",
      sharpe: performance?.sharpe ? performance.sharpe.toFixed(2) : "-",
      status: valueOf(item, ["status"], "active")
    };
  });

  async function handleReorder(nextIds: string[]) {
    // 乐观更新:直接调后端;失败则 reload 回滚
    try {
      await api.strategyReorder(nextIds);
      await strategies.reload();
    } catch (error) {
      console.error("reorder strategies failed:", error);
      await strategies.reload();
    }
  }

  async function handleSubmit() {
    const payload = {
      name: form.name.trim(),
      type: form.type,
      stocks: form.stocks
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      description: form.description.trim() || undefined
    };

    try {
      if (editingId) {
        await api.strategyUpdate(editingId, payload);
      } else {
        await api.strategyCreate(payload);
      }
      await strategies.reload();
      setShowForm(false);
      setEditingId(null);
      setForm({ name: "", type: "momentum", stocks: "", description: "" });
    } catch (error) {
      console.error("Save strategy failed:", error);
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this strategy?")) return;
    try {
      await api.strategyDelete(id);
      await strategies.reload();
    } catch (error) {
      console.error("Delete strategy failed:", error);
    }
  }

  function startEdit(strategyId: string) {
    const raw = list(strategies.data).find((item) => String(item.id || "") === strategyId);
    if (!raw) return;

    setEditingId(strategyId);
    setForm({
      name: valueOf(raw, ["name"], ""),
      type: valueOf(raw, ["type"], "momentum"),
      stocks: Array.isArray(raw.stocks) ? raw.stocks.join(",") : "",
      description: valueOf(raw, ["description"], "")
    });
    setShowForm(true);
  }

  return (
    <PageShell
      title="My Strategy"
      description="Manage personal investment strategies and holdings."
      actions={
        <Button
          data-testid="new-strategy-button"
          onClick={() => setShowForm((current) => !current)}
          tone="success"
          icon={<Plus size={16} />}
          disabled={!controlAvailable}
        >
          {showForm ? "Cancel" : "New Strategy"}
        </Button>
      }
      metrics={[
        metric("Strategies", strategyRows.length, "info"),
        metric("Active", strategyRows.filter((row) => row.status === "active").length, "success"),
        metric("Average Return", strategyRows.length ? "Tracked" : "-", "neutral"),
        metric("Sharpe", strategyRows.length ? "Tracked" : "-", "neutral")
      ]}
    >
      {showForm ? (
        <Panel title={editingId ? "Edit Strategy" : "Create Strategy"}>
          <div className="form-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <label className="field">
              <span>Name *</span>
              <input data-testid="strategy-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Value Portfolio" />
            </label>

            <label className="field">
              <span>Type</span>
              <select data-testid="strategy-type" value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}>
                <option value="momentum">momentum</option>
                <option value="value">value</option>
                <option value="growth">growth</option>
                <option value="dividend">dividend</option>
                <option value="custom">custom</option>
              </select>
            </label>

            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>Stocks</span>
              <input
                data-testid="strategy-stocks"
                value={form.stocks}
                onChange={(event) => setForm({ ...form, stocks: event.target.value })}
                placeholder="600519,000858,300750"
              />
            </label>

            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>Description</span>
              <textarea
                data-testid="strategy-description"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                rows={3}
                placeholder="Strategy thesis and rules"
              />
            </label>
          </div>

          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
            <Button data-testid="strategy-submit" onClick={() => void handleSubmit()} tone="success" disabled={!form.name.trim() || !controlAvailable}>
              {editingId ? "Update" : "Create"}
            </Button>
            <Button
              onClick={() => {
                setShowForm(false);
                setEditingId(null);
                setForm({ name: "", type: "momentum", stocks: "", description: "" });
              }}
              tone="neutral"
            >
              Cancel
            </Button>
          </div>
        </Panel>
      ) : null}

      <Panel title="Strategy List">
        {strategyRows.length === 0 ? (
          <EmptyState title="No strategies yet" detail="Create your first strategy from the top-right action." />
        ) : (
          <DraggableDataTable
            items={strategyRows}
            getRowId={(item) => String(item.id || "")}
            onReorder={handleReorder}
            dragEnabled={controlAvailable}
            columns={[
              { key: "name", header: "Name" },
              { key: "type", header: "Type" },
              { key: "stocks_count", header: "Stocks" },
              { key: "return", header: "Return" },
              { key: "sharpe", header: "Sharpe" },
              {
                key: "status",
                header: "Status",
                render: (item) => <StatusLight status={item.status === "active" ? "connected" : "disconnected"} label={item.status} />
              },
              {
                key: "id",
                header: "Actions",
                render: (item) => (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button onClick={() => startEdit(item.id)} tone="neutral" icon={<Edit2 size={14} />} disabled={!controlAvailable}>
                      Edit
                    </Button>
                    <Button onClick={() => void handleDelete(item.id)} tone="danger" icon={<Trash2 size={14} />} disabled={!controlAvailable}>
                      Delete
                    </Button>
                  </div>
                )
              }
            ]}
          />
        )}
      </Panel>
    </PageShell>
  );
}
