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
type RowKey = string | number;
type RowKeyResolver = (row: Record<string, unknown>, index: number) => RowKey;

const COMMON_ROW_KEY_FIELDS = [
  'id',
  'key',
  'uuid',
  'slug',
  'code',
  'stock_code',
  'symbol',
  'strategy_id',
  'experiment_id',
  'alert_id',
  'task_run_id',
  'index_version',
] as const;

function serializeRowKeyPart(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value instanceof Date) return value.toISOString();
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function deriveRowKeyBase(
  row: Record<string, unknown>,
  rowIndex: number,
  cols: ColumnDef[],
  rowKey?: string | RowKeyResolver,
): string {
  if (typeof rowKey === 'function') {
    return String(rowKey(row, rowIndex));
  }
  if (typeof rowKey === 'string' && row[rowKey] != null) {
    return `${rowKey}:${serializeRowKeyPart(row[rowKey])}`;
  }
  for (const field of COMMON_ROW_KEY_FIELDS) {
    if (row[field] != null) {
      return `${field}:${serializeRowKeyPart(row[field])}`;
    }
  }
  const contentKey = cols
    .slice(0, 4)
    .map((col) => `${col.key}:${serializeRowKeyPart(row[col.key])}`)
    .join('|');
  return contentKey || `row:${rowIndex}`;
}

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
  rowKey,
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
  rowKey?: string | RowKeyResolver;
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

  const pagedRows = useMemo(() => {
    const counts = new Map<string, number>();
    return paged.map((row, rowIndex) => {
      const base = deriveRowKeyBase(row, rowIndex, cols, rowKey);
      const duplicateCount = counts.get(base) ?? 0;
      counts.set(base, duplicateCount + 1);
      return {
        row,
        rowIndex,
        key: duplicateCount === 0 ? base : `${base}__${duplicateCount}`,
      };
    });
  }, [cols, paged, rowKey]);

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
            className="w-full max-w-[320px] px-3 py-2 text-sm"
          />
        </div>
      ) : null}
      {onExport ? (
        <div className="flex justify-end mb-1">
          <button onClick={onExport} className="rounded-full border border-border px-3 py-1 text-xs text-text-secondary hover:text-primary">导出 CSV</button>
        </div>
      ) : null}
      {mobileCardRender ? (
        <div className="grid gap-3 md:hidden">
          {pagedRows.map(({ row, rowIndex, key }) => (
            <div
              key={key}
              className={`rounded-[18px] border border-border bg-surface p-4 shadow-sm ${onRowClick ? 'cursor-pointer' : ''}`}
              onClick={() => onRowClick?.(row)}
            >
              {mobileCardRender(row, rowIndex)}
            </div>
          ))}
        </div>
      ) : null}
      <div
        className={`${mobileCardRender ? 'hidden md:block ' : ''}overflow-auto rounded-[20px] border border-border bg-surface shadow-sm`}
        style={{ maxHeight }}
      >
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-surface-alt">
            <tr>
              {cols.map((c, ci) => (
                <th
                  key={c.key}
                  className={`border-b border-border px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted whitespace-nowrap ${c.sortable !== false ? 'cursor-pointer select-none hover:bg-primary/5' : ''} text-${c.align ?? 'left'}${stickyFirstCol && ci === 0 ? ' sticky left-0 z-[1]' : ''}`}
                  style={{ ...(c.width ? { width: c.width } : {}), ...(stickyFirstCol && ci === 0 ? { background: 'var(--color-surface-alt)' } : {}) }}
                  onClick={() => c.sortable !== false && toggleSort(c.key)}
                >
                  {c.label ?? c.key}
                  {sort?.key === c.key ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map(({ row, key }) => (
              <tr key={key} className={`transition-colors hover:bg-surface-alt/70${onRowClick ? ' cursor-pointer' : ''}`} onClick={() => onRowClick?.(row)}>
                {cols.map((c, ci) => (
                  <td
                    key={c.key}
                    className={`border-b border-border-light px-3 py-2 text-${c.align ?? 'left'} align-top text-text-secondary${stickyFirstCol && ci === 0 ? ' sticky left-0 z-[1]' : ''}`}
                    style={stickyFirstCol && ci === 0 ? { background: 'var(--color-surface)' } : undefined}
                  >
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
            <button disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-full border border-border px-3 py-1 disabled:opacity-40">上一页</button>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)} className="rounded-full border border-border px-3 py-1 disabled:opacity-40">下一页</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
