'use client';

import { useState, useMemo } from 'react';
import { fmt } from '@/lib/api';

type ColumnDef = {
  key: string;
  label?: string;
  align?: 'left' | 'right' | 'center';
  render?: (value: unknown, row: Record<string, unknown>) => React.ReactNode;
  sortable?: boolean;
  width?: number | string;
};

type SortState = { key: string; dir: 'asc' | 'desc' } | null;

export function DataTable({
  rows,
  columns,
  maxHeight = 400,
  pageSize,
  className = '',
  emptyText = '暂无数据',
  onExport,
}: {
  rows: Record<string, unknown>[];
  columns?: ColumnDef[];
  maxHeight?: number;
  pageSize?: number;
  className?: string;
  emptyText?: string;
  onExport?: () => void;
}) {
  const [sort, setSort] = useState<SortState>(null);
  const [page, setPage] = useState(0);

  const cols: ColumnDef[] = useMemo(() => {
    if (columns) return columns;
    if (!rows.length) return [];
    return Object.keys(rows[0]).map((key) => ({ key, label: key, sortable: true }));
  }, [columns, rows]);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return sort.dir === 'asc' ? av - bv : bv - av;
      return sort.dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [rows, sort]);

  const paged = useMemo(() => {
    if (!pageSize) return sorted;
    return sorted.slice(page * pageSize, (page + 1) * pageSize);
  }, [sorted, page, pageSize]);

  const totalPages = pageSize ? Math.ceil(rows.length / pageSize) : 1;

  function toggleSort(key: string) {
    setSort((prev) => {
      if (prev?.key === key) return prev.dir === 'asc' ? { key, dir: 'desc' } : null;
      return { key, dir: 'asc' };
    });
  }

  if (!rows.length) return <p className="text-text-secondary text-sm mt-2">{emptyText}</p>;

  return (
    <div className={`mt-2 ${className}`}>
      {onExport ? (
        <div className="flex justify-end mb-1">
          <button onClick={onExport} className="text-xs text-primary cursor-pointer hover:underline">导出 CSV</button>
        </div>
      ) : null}
      <div className="overflow-auto border border-border rounded-lg" style={{ maxHeight }}>
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-surface-alt">
            <tr>
              {cols.map((c) => (
                <th
                  key={c.key}
                  className={`px-2 py-1.5 font-semibold border-b border-border whitespace-nowrap ${c.sortable !== false ? 'cursor-pointer select-none hover:bg-gray-200' : ''} text-${c.align ?? 'left'}`}
                  style={c.width ? { width: c.width } : undefined}
                  onClick={() => c.sortable !== false && toggleSort(c.key)}
                >
                  {c.label ?? c.key}
                  {sort?.key === c.key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr key={i} className="hover:bg-surface">
                {cols.map((c) => (
                  <td key={c.key} className={`px-2 py-1 border-b border-border-light text-${c.align ?? 'left'}`}>
                    {c.render ? c.render(row[c.key], row) : fmt(row[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageSize && totalPages > 1 ? (
        <div className="flex items-center justify-between mt-2 text-xs text-text-secondary">
          <span>共 {rows.length} 条，第 {page + 1}/{totalPages} 页</span>
          <div className="flex gap-1">
            <button disabled={page === 0} onClick={() => setPage(page - 1)} className="px-2 py-0.5 border border-border rounded disabled:opacity-40 cursor-pointer">上一页</button>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)} className="px-2 py-0.5 border border-border rounded disabled:opacity-40 cursor-pointer">下一页</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
