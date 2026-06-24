/**
 * VirtualTable - 大表格虚拟化组件
 * 使用 @tanstack/react-virtual 实现高性能渲染
 */

import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import type { UnknownRecord } from "../types";

export interface VirtualTableColumn {
  key: string;
  label: string;
  width?: number;
  render?: (value: unknown, row: UnknownRecord) => React.ReactNode;
}

export interface VirtualTableProps {
  data: UnknownRecord[];
  columns: VirtualTableColumn[];
  rowHeight?: number;
  maxHeight?: number;
  onRowClick?: (row: UnknownRecord) => void;
  emptyMessage?: string;
}

/**
 * 虚拟化表格 - 适用于 1000+ 行数据
 *
 * @example
 * <VirtualTable
 *   data={tools}
 *   columns={[
 *     { key: 'name', label: '工具名称' },
 *     { key: 'category', label: '分类' },
 *     { key: 'status', label: '状态', render: (v) => <StatusBadge>{v}</StatusBadge> }
 *   ]}
 *   rowHeight={56}
 *   maxHeight={600}
 *   onRowClick={(row) => setSelected(row)}
 * />
 */
export function VirtualTable({
  data,
  columns,
  rowHeight = 48,
  maxHeight = 600,
  onRowClick,
  emptyMessage = "无数据"
}: VirtualTableProps) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 5
  });

  if (data.length === 0) {
    return (
      <div className="virtual-table-empty" style={{ height: maxHeight }}>
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="virtual-table-container">
      {/* 表头 */}
      <div className="virtual-table-header">
        {columns.map((col) => (
          <div
            key={col.key}
            className="virtual-table-header-cell"
            style={{ width: col.width ? `${col.width}px` : undefined }}
          >
            {col.label}
          </div>
        ))}
      </div>

      {/* 虚拟化滚动区域 */}
      <div
        ref={parentRef}
        className="virtual-table-body"
        style={{
          height: `${maxHeight}px`,
          overflow: "auto"
        }}
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: "100%",
            position: "relative"
          }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const row = data[virtualRow.index];
            return (
              <div
                key={virtualRow.key}
                className={onRowClick ? "virtual-table-row clickable" : "virtual-table-row"}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`
                }}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => {
                  const value = row[col.key];
                  return (
                    <div
                      key={col.key}
                      className="virtual-table-cell"
                      style={{ width: col.width ? `${col.width}px` : undefined }}
                    >
                      {col.render ? col.render(value, row) : String(value ?? "")}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      {/* 底部信息 */}
      <div className="virtual-table-footer">
        共 {data.length.toLocaleString()} 行（虚拟化渲染）
      </div>
    </div>
  );
}

/**
 * 虚拟化列表 - 适用于简单列表场景
 */
export interface VirtualListProps<T = UnknownRecord> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  itemHeight?: number;
  maxHeight?: number;
  emptyMessage?: string;
}

export function VirtualList<T = UnknownRecord>({
  items,
  renderItem,
  itemHeight = 64,
  maxHeight = 600,
  emptyMessage = "列表为空"
}: VirtualListProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => itemHeight,
    overscan: 3
  });

  if (items.length === 0) {
    return (
      <div className="virtual-list-empty" style={{ height: maxHeight }}>
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className="virtual-list"
      style={{
        height: `${maxHeight}px`,
        overflow: "auto"
      }}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative"
        }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => (
          <div
            key={virtualItem.key}
            className="virtual-list-item"
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: `${virtualItem.size}px`,
              transform: `translateY(${virtualItem.start}px)`
            }}
          >
            {renderItem(items[virtualItem.index], virtualItem.index)}
          </div>
        ))}
      </div>
    </div>
  );
}
