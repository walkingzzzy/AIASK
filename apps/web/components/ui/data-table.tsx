'use client';

import { useState, useMemo } from 'react';
import { fmt } from '@/lib/api';
import { EmptyState } from '@/components/status-state';

type ColumnDef = {
  key: string;
  label?: string;
  align?: 'left' | 'right' | 'center';
  render?: (value: unknown, row: Record<string, unknown>) => React.ReactNode;
  sortable?: boolean;
  width?: number | string;
};

type SortState = { key: string; dir: 'asc' | 'desc' } | null;

type MobileCardRender = (row: Record<string, unknown>, index: number) => React.ReactNode;

export function DataTable({
  rows,
  columns,
  maxHeight = 400,
  pageSize,
  className = '',
  emptyText = '暂无数据',
  onExport,
  searchable,
  onRowClick,
  stickyFirstCol,
  mobileCardRender,
}: {
  rows: Record<string, unknown>[];
  columns?: ColumnDef[];
  maxHeight?: number;
  pageSize?: number;
  className?: string;
  emptyText?: string;
  onExport?: () => void;
  searchable?: boolean;
  onRowClick?: (row: Record<string, unknown>) => void;
  stickyFirstCol?: boolean;
  mobileCardRender?: MobileCardRender;
}) {
  const [sort, setSort] = useState<SortState>(null);
  const [page, setPage] = useState(0);
  const [filterText, setFilterText] = useState('');

  const cols: ColumnDef[] = useMemo(() => {
    if (columns) return columns;
    if (!rows.length) return [];
    return Object.keys(rows[0]).map((key) => ({ key, label: key, sortable: true }));
  }, [columns, rows]);

  const filtered = useMemo(() => {
    if (!filterText.trim()) return rows;
    const lower = filterText.toLowerCase();
    return rows.filter((row) =>
      cols.some((c) => {
        const v = row[c.key];
        return v != null && String(v).toLowerCase().includes(lower);
      }),
    );
  }, [rows, filterText, cols]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    return [...filtered].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return sort.dir === 'asc' ? av - bv : bv - av;
      return sort.dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [filtered, sort]);

  const paged = useMemo(() => {
    if (!pageSize) return sorted;
    return sorted.slice(page * pageSize, (page + 1) * pageSize);
  }, [sorted, page, pageSize]);

  const totalPages = pageSize ? Math.ceil(filtered.length / pageSize) : 1;

  function toggleSort(key: string) {
    setSort((prev) => {
      if (prev?.key === key) return prev.dir === 'asc' ? { key, dir: 'desc' } : null;
      return { key, dir: 'asc' };
    });
  }

  if (!rows.length) return <EmptyState text={emptyText} />;

  return (
    <div className={`mt-2 ${className}`}>
      {searchable ? (
        <div className="mb-2">
          <input
            type="text"
            value={filterText}
            onChange={(e) => { setFilterText(e.target.value); setPage(0); }}
            placeholder="搜索筛选..."
            aria-label="表格搜索筛选"
            className="w-full max-w-[280px] px-2 py-1 border border-border rounded text-sm"
          />
        </div>
      ) : null}
      {onExport ? (
        <div className="flex justify-end mb-1">
          <button onClick={onExport} className="text-xs text-primary cursor-pointer hover:underline">导出 CSV</button>
        </div>
      ) : null}
      {mobileCardRender ? (
        <div className="grid gap-3 md:hidden">
          {paged.map((row, i) => (
            <div
              key={i}
              className={`glass rounded-xl border border-glass-border p-3 ${onRowClick ? 'cursor-pointer' : ''}`}
              onClick={() => onRowClick?.(row)}
            >
              {mobileCardRender(row, i)}
            </div>
          ))}
        </div>
      ) : null}
      <div className={`${mobileCardRender ? 'hidden md:block ' : ''}overflow-auto glass rounded-xl`} style={{ maxHeight }}>
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0" style={{ background: 'var(--color-glass-strong)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}>
            <tr>
              {cols.map((c, ci) => (
                <th
                  key={c.key}
                  className={`px-2 py-1.5 font-semibold border-b border-glass-border whitespace-nowrap ${c.sortable !== false ? 'cursor-pointer select-none hover:bg-white/10' : ''} text-${c.align ?? 'left'}${stickyFirstCol && ci === 0 ? ' sticky left-0 z-[1]' : ''}`}
                  style={{ ...(c.width ? { width: c.width } : {}), ...(stickyFirstCol && ci === 0 ? { background: 'var(--color-glass-strong)' } : {}) }}
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
              <tr key={i} className={`hover:bg-white/10 transition-colors${onRowClick ? ' cursor-pointer' : ''}`} onClick={() => onRowClick?.(row)}>
                {cols.map((c, ci) => (
                  <td key={c.key} className={`px-2 py-1 border-b border-glass-border text-${c.align ?? 'left'}${stickyFirstCol && ci === 0 ? ' sticky left-0 z-[1]' : ''}`}
                    style={stickyFirstCol && ci === 0 ? { background: 'var(--color-glass-strong)' } : undefined}>
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
          <span>共 {filtered.length} 条，第 {page + 1}/{totalPages} 页</span>
          <div className="flex gap-1">
            <button disabled={page === 0} onClick={() => setPage(page - 1)} className="px-2 py-0.5 border border-border rounded disabled:opacity-40 cursor-pointer">上一页</button>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)} className="px-2 py-0.5 border border-border rounded disabled:opacity-40 cursor-pointer">下一页</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
