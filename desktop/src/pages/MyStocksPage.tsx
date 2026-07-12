import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { DraggableDataTable } from "../components/DraggableDataTable";
import { SearchBar } from "../components/SearchAndFilter";
import { Button, EmptyState, JsonPanel, PageShell, Panel } from "../components/ui";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { list, metric, valueOf } from "./pageUtils";
import type { PageProps } from "./pageUtils";

export function MyStocksPage({ api, controlAvailable }: PageProps) {
  const pools = useAsyncResource(() => api.userStockPools(), [api]);
  const [showPoolForm, setShowPoolForm] = useState(false);
  const [showStockForm, setShowStockForm] = useState(false);
  const [selectedPoolId, setSelectedPoolId] = useState<string | null>(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [selectedStockCodes, setSelectedStockCodes] = useState<Set<string>>(new Set());
  const [batchResult, setBatchResult] = useState<unknown>(null);
  const [poolForm, setPoolForm] = useState({ name: "", description: "" });
  const [stockForm, setStockForm] = useState({ code: "", name: "", tags: "", notes: "" });

  // 按 sort_order 排序股票池
  const orderedPools = useMemo(() => {
    const items = list(pools.data);
    return [...items].sort((a, b) => {
      const sa = Number(a.sort_order ?? 0);
      const sb = Number(b.sort_order ?? 0);
      if (sa !== sb) return sa - sb;
      return String(a.id || "").localeCompare(String(b.id || ""));
    });
  }, [pools.data]);

  const poolRows = orderedPools.map((item) => ({
    id: String(item.id || ""),
    name: valueOf(item, ["name"], "未命名股票池"),
    stocks_count: Array.isArray(item.stocks) ? item.stocks.length : 0,
    created_at: valueOf(item, ["created_at"], "-")
  }));

  async function handlePoolReorder(nextIds: string[]) {
    try {
      await api.stockPoolReorder(nextIds);
      await pools.reload();
    } catch (error) {
      console.error("reorder stock pools failed:", error);
      await pools.reload();
    }
  }

  const selectedPool = selectedPoolId ? list(pools.data).find((item) => String(item.id || "") === selectedPoolId) : null;
  const allStocks = selectedPool && Array.isArray(selectedPool.stocks) ? selectedPool.stocks : [];
  const stockRows = allStocks
    .filter((stock) => {
      if (!searchKeyword) return true;
      const keyword = searchKeyword.toLowerCase();
      return String(stock.code || "").toLowerCase().includes(keyword) || String(stock.name || "").toLowerCase().includes(keyword);
    })
    .map((stock) => ({
      code: String(stock.code || ""),
      name: String(stock.name || stock.code || ""),
      tags: Array.isArray(stock.tags) ? stock.tags.join(", ") : "-",
      note: String(stock.note || stock.notes || "-"),
      added_at: String(stock.added_at || "-")
    }));

  const selectedVisibleStockCodes = stockRows.map((stock) => stock.code).filter((code) => selectedStockCodes.has(code));

  async function handleCreatePool() {
    try {
      await api.stockPoolCreate({
        name: poolForm.name,
        description: poolForm.description || undefined
      });
      await pools.reload();
      setShowPoolForm(false);
      setPoolForm({ name: "", description: "" });
    } catch (error) {
      console.error("Create stock pool failed:", error);
    }
  }

  async function handleDeletePool(id: string) {
    if (!window.confirm("确认删除这个股票池？")) return;
    try {
      await api.stockPoolDelete(id);
      await pools.reload();
      if (selectedPoolId === id) setSelectedPoolId(null);
    } catch (error) {
      console.error("Delete stock pool failed:", error);
    }
  }

  async function handleAddStock() {
    if (!selectedPoolId) return;
    try {
      await api.stockPoolAddStock(selectedPoolId, {
        code: stockForm.code.trim(),
        name: stockForm.name.trim() || stockForm.code.trim(),
        tags: stockForm.tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        note: stockForm.notes.trim() || undefined
      });
      await pools.reload();
      setShowStockForm(false);
      setStockForm({ code: "", name: "", tags: "", notes: "" });
    } catch (error) {
      console.error("Add stock failed:", error);
    }
  }

  async function handleRemoveStock(code: string) {
    if (!selectedPoolId) return;
    if (!window.confirm(`确认从这个股票池移除 ${code}？`)) return;

    try {
      await api.stockPoolRemoveStock(selectedPoolId, code);
      await pools.reload();
    } catch (error) {
      console.error("Remove stock failed:", error);
    }
  }

  async function handleBatchRemoveStocks() {
    if (!selectedPoolId || !selectedVisibleStockCodes.length) return;
    if (!window.confirm(`确认从这个股票池移除已选择的 ${selectedVisibleStockCodes.length} 只股票？`)) return;

    try {
      const result = await api.stockPoolBatchRemove(selectedPoolId, selectedVisibleStockCodes);
      setBatchResult(result);
      setSelectedStockCodes(new Set());
      await pools.reload();
    } catch (error) {
      console.error("Batch remove stocks failed:", error);
      setBatchResult({ error: "batch_remove_failed", detail: error instanceof Error ? error.message : String(error) });
    }
  }

  return (
    <PageShell
      title="我的股票"
      description="管理个人股票池、标签和备注。"
      actions={
        <Button
          data-testid="new-pool-button"
          onClick={() => setShowPoolForm((current) => !current)}
          tone="success"
          icon={<Plus size={16} />}
          disabled={!controlAvailable}
        >
          {showPoolForm ? "取消" : "新建股票池"}
        </Button>
      }
      metrics={[
        metric("股票池", poolRows.length, "info"),
        metric(
          "股票总数",
          poolRows.reduce((sum, row) => sum + row.stocks_count, 0),
          "success"
        ),
        metric("当前股票池", selectedPool ? valueOf(selectedPool as Record<string, unknown>, ["name"]) : "未选择", selectedPool ? "info" : "neutral")
      ]}
    >
      <div className="grid-2">
        <div className="stack">
          {showPoolForm ? (
            <Panel title="创建股票池">
              <div className="form-grid">
                <label className="field">
                  <span>名称 *</span>
                  <input
                    data-testid="pool-name"
                    value={poolForm.name}
                    onChange={(event) => setPoolForm({ ...poolForm, name: event.target.value })}
                    placeholder="核心持仓"
                  />
                </label>
                <label className="field">
                  <span>说明</span>
                  <textarea value={poolForm.description} onChange={(event) => setPoolForm({ ...poolForm, description: event.target.value })} rows={2} />
                </label>
              </div>
              <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
                <Button data-testid="pool-submit" onClick={() => void handleCreatePool()} tone="success" disabled={!poolForm.name.trim()}>
                  创建
                </Button>
                <Button onClick={() => setShowPoolForm(false)} tone="neutral">
                  取消
                </Button>
              </div>
            </Panel>
          ) : null}

          <Panel title="股票池">
            {poolRows.length === 0 ? (
              <EmptyState title="暂无股票池" detail="点击右上角操作创建第一个股票池。" />
            ) : (
              <DraggableDataTable
                items={poolRows}
                getRowId={(item) => String(item.id || "")}
                onReorder={handlePoolReorder}
                dragEnabled={controlAvailable}
                columns={[
                  { key: "name", header: "名称" },
                  { key: "stocks_count", header: "股票数" },
                  {
                    key: "id",
                    header: "操作",
                    render: (item) => (
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <Button onClick={() => setSelectedPoolId(item.id)} tone={selectedPoolId === item.id ? "info" : "neutral"}>
                          {selectedPoolId === item.id ? "已选择" : "打开"}
                        </Button>
                        <Button onClick={() => void handleDeletePool(item.id)} tone="danger" icon={<Trash2 size={14} />} disabled={!controlAvailable}>
                          删除
                        </Button>
                      </div>
                    )
                  }
                ]}
              />
            )}
          </Panel>
        </div>

        <div className="stack">
          {selectedPoolId ? (
            <>
              {showStockForm ? (
                <Panel title="添加股票">
                  <div className="form-grid">
                    <label className="field">
                      <span>代码 *</span>
                      <input
                        data-testid="stock-code"
                        value={stockForm.code}
                        onChange={(event) => setStockForm({ ...stockForm, code: event.target.value })}
                        placeholder="600519"
                      />
                    </label>
                    <label className="field">
                      <span>名称</span>
                      <input value={stockForm.name} onChange={(event) => setStockForm({ ...stockForm, name: event.target.value })} placeholder="贵州茅台" />
                    </label>
                    <label className="field">
                      <span>标签</span>
                      <input value={stockForm.tags} onChange={(event) => setStockForm({ ...stockForm, tags: event.target.value })} placeholder="核心、白酒" />
                    </label>
                    <label className="field">
                      <span>备注</span>
                      <textarea value={stockForm.notes} onChange={(event) => setStockForm({ ...stockForm, notes: event.target.value })} rows={2} />
                    </label>
                  </div>
                  <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
                    <Button data-testid="stock-submit" onClick={() => void handleAddStock()} tone="success" disabled={!stockForm.code.trim()}>
                      添加
                    </Button>
                    <Button onClick={() => setShowStockForm(false)} tone="neutral">
                      取消
                    </Button>
                  </div>
                </Panel>
              ) : null}

              <Panel
                title={`股票 - ${selectedPool ? valueOf(selectedPool as Record<string, unknown>, ["name"]) : "未知"}`}
                action={
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <SearchBar value={searchKeyword} onChange={setSearchKeyword} placeholder="搜索股票..." />
                    <Button onClick={() => setShowStockForm((current) => !current)} tone="success" icon={<Plus size={16} />} disabled={!controlAvailable}>
                      {showStockForm ? "取消" : "添加"}
                    </Button>
                  </div>
                }
              >
                {stockRows.length === 0 ? (
                  <EmptyState title="暂无股票" detail="点击右上角操作向这个股票池添加股票。" />
                ) : (
                  <DraggableDataTable
                    items={stockRows}
                    getRowId={(item) => String(item.code || "")}
                    selectedIds={selectedStockCodes}
                    onSelectionChange={setSelectedStockCodes}
                    batchActions={
                      <Button
                        data-testid="stock-pool-batch-remove"
                        tone="danger"
                        icon={<Trash2 size={14} />}
                        disabled={!controlAvailable || !selectedVisibleStockCodes.length}
                        onClick={() => void handleBatchRemoveStocks()}
                      >
                        移除已选
                      </Button>
                    }
                    columns={[
                      { key: "code", header: "代码" },
                      { key: "name", header: "名称" },
                      { key: "tags", header: "标签" },
                      { key: "note", header: "备注" },
                      {
                        key: "code",
                        header: "操作",
                        render: (item) => (
                          <Button onClick={() => void handleRemoveStock(item.code)} tone="danger" icon={<Trash2 size={14} />} disabled={!controlAvailable}>
                            移除
                          </Button>
                        )
                      }
                    ]}
                  />
                )}
              </Panel>
              {batchResult ? <JsonPanel data={batchResult} title="批量移除结果" /> : null}
            </>
          ) : (
            <EmptyState title="请先选择股票池" detail="请在左侧选择或创建一个股票池。" />
          )}
        </div>
      </div>
    </PageShell>
  );
}
