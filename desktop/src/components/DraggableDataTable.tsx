import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

import { EmptyState } from "./ui";
import { useDragReorder } from "./DraggableList";
import type { TableColumn, UnknownRecord } from "../types";

/**
 * DraggableDataTable - 支持原生 HTML5 拖拽排序的表格,可选行多选。
 *
 * 设计动机:策略列表、股票池列表、会话列表都需要拖拽排序,其中会话列表
 * 还需要批量归档。把拖拽状态机与可选的 checkbox 选择合并到一张表,
 * 避免在 SessionsRunsPage 同时挂 BatchDataTable + 另一套拖拽。
 *
 * - 拖拽:onReorder(nextIds) 回调,调用方负责调 API 或本地持久化
 * - 选择(可选):传 selectedIds/onSelectionChange/batchActions 即启用首列 checkbox
 * - enabled=false 时退化为普通只读表格(mock 模式 / 过滤态)
 *
 * 强制显式 getRowId:拖拽和多选都依赖稳定 key。
 */
export interface DraggableDataTableProps<T extends UnknownRecord = UnknownRecord> {
  items: T[];
  columns: TableColumn<T>[];
  empty?: string;
  getRowId: (item: T) => string;
  /** 拖拽排序回调;不传则不可拖拽 */
  onReorder?: (nextIds: string[]) => void | Promise<void>;
  /** 拖拽开关:过滤态/只读态置 false */
  dragEnabled?: boolean;
  /** 可选:行多选(会话批量归档场景) */
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  batchActions?: ReactNode;
}

export function DraggableDataTable<T extends UnknownRecord = UnknownRecord>({
  items,
  columns,
  empty = "No data",
  getRowId,
  onReorder,
  dragEnabled = false,
  selectedIds,
  onSelectionChange,
  batchActions
}: DraggableDataTableProps<T>) {
  const selectable = Boolean(selectedIds && onSelectionChange);
  const headerCheckboxRef = useRef<HTMLInputElement>(null);
  const ids = items.map((item) => getRowId(item));

  const { rowProps, isDragging, isDragOver } = useDragReorder<unknown>({
    ids,
    onReorder: onReorder || ((): void => undefined),
    enabled: dragEnabled && Boolean(onReorder)
  });

  const allSelected = selectable && items.length > 0 && ids.every((id) => selectedIds!.has(id));
  const someSelected = selectable && ids.some((id) => selectedIds!.has(id)) && !allSelected;
  const selectedCount = selectable ? ids.filter((id) => selectedIds!.has(id)).length : 0;

  useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  if (!items.length) {
    return <EmptyState title={empty} detail="There are no records for the current state." />;
  }

  function toggleOne(id: string) {
    if (!selectedIds || !onSelectionChange) return;
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange(next);
  }

  function toggleAll() {
    if (!selectedIds || !onSelectionChange) return;
    if (allSelected) {
      const next = new Set(selectedIds);
      ids.forEach((id) => next.delete(id));
      onSelectionChange(next);
    } else {
      const next = new Set(selectedIds);
      ids.forEach((id) => next.add(id));
      onSelectionChange(next);
    }
  }

  const dragColumnWidth = dragEnabled ? "1.75rem" : undefined;

  return (
    <div className="draggable-table-wrap" data-testid="draggable-table">
      {selectable && selectedCount > 0 && batchActions ? (
        <div className="batch-actions-bar" data-testid="batch-actions-bar">
          <span className="batch-count">已选 {selectedCount} 项</span>
          <div className="batch-actions-buttons">{batchActions}</div>
        </div>
      ) : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {selectable ? (
                <th style={{ width: "2.5rem" }}>
                  <input
                    ref={headerCheckboxRef}
                    type="checkbox"
                    data-testid="batch-select-all"
                    checked={allSelected}
                    onChange={toggleAll}
                    aria-label="全选"
                  />
                </th>
              ) : null}
              {dragEnabled ? <th style={{ width: dragColumnWidth }} /> : null}
              {columns.map((column) => (
                <th key={String(column.key)} style={column.width ? { width: column.width } : undefined}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => {
              const id = getRowId(item);
              const dragOn = dragEnabled && Boolean(onReorder);
              const className = [
                isDragging(index) ? "drag-row-source" : "",
                isDragOver(index) ? "drag-row-over" : "",
                dragOn ? "drag-row" : ""
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <tr key={id || index} className={className} {...(dragOn ? rowProps(index) : {})}>
                  {selectable ? (
                    <td>
                      <input
                        type="checkbox"
                        data-testid={`batch-select-row-${id}`}
                        checked={selectedIds!.has(id)}
                        onChange={() => toggleOne(id)}
                        aria-label={`选择 ${id}`}
                      />
                    </td>
                  ) : null}
                  {dragEnabled ? (
                    <td className="drag-handle-cell" title={dragOn ? "拖拽排序" : undefined}>
                      {dragOn ? "⣿" : ""}
                    </td>
                  ) : null}
                  {columns.map((column) => (
                    <td key={String(column.key)}>
                      {column.render ? column.render(item) : String(item[column.key as keyof T] ?? "")}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
