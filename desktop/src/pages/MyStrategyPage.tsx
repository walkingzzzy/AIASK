import { Edit2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { DraggableDataTable } from "../components/DraggableDataTable";
import { StatusLight } from "../components/StatusLight";
import { Button, EmptyState, PageShell, Panel } from "../components/ui";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { list, metric, valueOf } from "./pageUtils";
import type { PageProps } from "./pageUtils";

function strategyTypeLabel(value: string) {
  const labels: Record<string, string> = {
    momentum: "动量",
    value: "价值",
    growth: "成长",
    dividend: "红利",
    custom: "自定义"
  };
  return labels[value] || value;
}

function strategyStatusLabel(value: string) {
  const labels: Record<string, string> = {
    active: "启用中",
    disabled: "已停用",
    archived: "已归档"
  };
  return labels[value] || value;
}

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
      name: valueOf(item, ["name"], "未命名策略"),
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
    if (!window.confirm("确认删除这个策略？")) return;
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
      title="我的策略"
      description="管理个人投资策略、关联股票和跟踪表现。"
      actions={
        <Button
          data-testid="new-strategy-button"
          onClick={() => setShowForm((current) => !current)}
          tone="success"
          icon={<Plus size={16} />}
          disabled={!controlAvailable}
        >
          {showForm ? "取消" : "新建策略"}
        </Button>
      }
      metrics={[
        metric("策略", strategyRows.length, "info"),
        metric("启用中", strategyRows.filter((row) => row.status === "active").length, "success"),
        metric("平均收益", strategyRows.length ? "已跟踪" : "-", "neutral"),
        metric("夏普", strategyRows.length ? "已跟踪" : "-", "neutral")
      ]}
    >
      {showForm ? (
        <Panel title={editingId ? "编辑策略" : "创建策略"}>
          <div className="form-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <label className="field">
              <span>名称 *</span>
              <input data-testid="strategy-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="价值组合" />
            </label>

            <label className="field">
              <span>类型</span>
              <select data-testid="strategy-type" value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}>
                <option value="momentum">动量</option>
                <option value="value">价值</option>
                <option value="growth">成长</option>
                <option value="dividend">红利</option>
                <option value="custom">自定义</option>
              </select>
            </label>

            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>股票</span>
              <input
                data-testid="strategy-stocks"
                value={form.stocks}
                onChange={(event) => setForm({ ...form, stocks: event.target.value })}
                placeholder="600519,000858,300750"
              />
            </label>

            <label className="field" style={{ gridColumn: "1 / -1" }}>
              <span>说明</span>
              <textarea
                data-testid="strategy-description"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                rows={3}
                placeholder="策略逻辑和执行规则"
              />
            </label>
          </div>

          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
            <Button data-testid="strategy-submit" onClick={() => void handleSubmit()} tone="success" disabled={!form.name.trim() || !controlAvailable}>
              {editingId ? "更新" : "创建"}
            </Button>
            <Button
              onClick={() => {
                setShowForm(false);
                setEditingId(null);
                setForm({ name: "", type: "momentum", stocks: "", description: "" });
              }}
              tone="neutral"
            >
              取消
            </Button>
          </div>
        </Panel>
      ) : null}

      <Panel title="策略列表">
        {strategyRows.length === 0 ? (
          <EmptyState title="暂无策略" detail="点击右上角操作创建第一个策略。" />
        ) : (
          <DraggableDataTable
            items={strategyRows}
            getRowId={(item) => String(item.id || "")}
            onReorder={handleReorder}
            dragEnabled={controlAvailable}
            columns={[
              { key: "name", header: "名称" },
              { key: "type", header: "类型", render: (item) => strategyTypeLabel(String(item.type || "")) },
              { key: "stocks_count", header: "股票数" },
              { key: "return", header: "收益" },
              { key: "sharpe", header: "Sharpe" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusLight status={item.status === "active" ? "connected" : "disconnected"} label={strategyStatusLabel(String(item.status || ""))} />
              },
              {
                key: "id",
                header: "操作",
                render: (item) => (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button onClick={() => startEdit(item.id)} tone="neutral" icon={<Edit2 size={14} />} disabled={!controlAvailable}>
                      编辑
                    </Button>
                    <Button onClick={() => void handleDelete(item.id)} tone="danger" icon={<Trash2 size={14} />} disabled={!controlAvailable}>
                      删除
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
