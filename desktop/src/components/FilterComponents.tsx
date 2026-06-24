import { ChevronDown, ChevronUp, Filter, Search, X } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { Button } from "./ui";

/**
 * 高级筛选组件
 * 对应方案 4.2 节 FilterBar 要求
 */

export interface FilterConfig {
  id: string;
  label: string;
  type: "search" | "select" | "multiselect" | "daterange" | "toggle";
  options?: { value: string; label: string }[];
  placeholder?: string;
}

export interface FilterValues {
  [key: string]: string | string[] | boolean | { from?: string; to?: string };
}

type FilterValue = FilterValues[string];

export function FilterBar({
  filters,
  values,
  onChange,
  onClear
}: {
  filters: FilterConfig[];
  values: FilterValues;
  onChange: (values: FilterValues) => void;
  onClear: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visibleFilters = expanded ? filters : filters.slice(0, 3);
  const hasActiveFilters = Object.values(values).some((v) =>
    Array.isArray(v) ? v.length > 0 : typeof v === "boolean" ? v : v && (typeof v === "string" ? v !== "" : true)
  );

  function updateFilter(id: string, value: FilterValue) {
    onChange({ ...values, [id]: value });
  }

  function clearAll() {
    onClear();
  }

  return (
    <div className="filter-bar">
      <div className="filter-bar-header">
        <div className="filter-bar-title">
          <Filter size={16} />
          <span>筛选条件</span>
          {hasActiveFilters ? <span className="filter-count">{Object.keys(values).length} 个筛选</span> : null}
        </div>
        <div className="filter-bar-actions">
          {hasActiveFilters ? (
            <Button icon={<X size={14} />} onClick={clearAll}>
              清空
            </Button>
          ) : null}
          {filters.length > 3 ? (
            <Button icon={expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />} onClick={() => setExpanded(!expanded)}>
              {expanded ? "收起" : "展开"}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="filter-controls">
        {visibleFilters.map((filter) => (
          <FilterControl key={filter.id} filter={filter} value={values[filter.id]} onChange={(v) => updateFilter(filter.id, v)} />
        ))}
      </div>
    </div>
  );
}

function FilterControl({ filter, value, onChange }: { filter: FilterConfig; value: FilterValue | undefined; onChange: (value: FilterValue) => void }) {
  switch (filter.type) {
    case "search":
      return (
        <div className="filter-control filter-search">
          <label>{filter.label}</label>
          <div className="search-input">
            <Search size={14} />
            <input
              type="text"
              value={String(value || "")}
              placeholder={filter.placeholder || "搜索..."}
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
        </div>
      );

    case "select":
      return (
        <div className="filter-control filter-select">
          <label>{filter.label}</label>
          <select value={String(value || "")} onChange={(e) => onChange(e.target.value)}>
            <option value="">全部</option>
            {filter.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      );

    case "multiselect":
      const selected = Array.isArray(value) ? value : [];
      return (
        <div className="filter-control filter-multiselect">
          <label>{filter.label}</label>
          <div className="multiselect-options">
            {filter.options?.map((opt) => (
              <label key={opt.value} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selected.includes(opt.value)}
                  onChange={(e) => {
                    const newSelected = e.target.checked ? [...selected, opt.value] : selected.filter((v) => v !== opt.value);
                    onChange(newSelected);
                  }}
                />
                <span>{opt.label}</span>
              </label>
            ))}
          </div>
        </div>
      );

    case "daterange":
      const range = (value as { from?: string; to?: string }) || {};
      return (
        <div className="filter-control filter-daterange">
          <label>{filter.label}</label>
          <div className="daterange-inputs">
            <input
              type="date"
              value={range.from || ""}
              placeholder="开始日期"
              onChange={(e) => onChange({ ...range, from: e.target.value })}
            />
            <span>至</span>
            <input
              type="date"
              value={range.to || ""}
              placeholder="结束日期"
              onChange={(e) => onChange({ ...range, to: e.target.value })}
            />
          </div>
        </div>
      );

    case "toggle":
      return (
        <div className="filter-control filter-toggle">
          <label className="checkbox-label">
            <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
            <span>{filter.label}</span>
          </label>
        </div>
      );

    default:
      return null;
  }
}

/**
 * 快速筛选标签
 */
export function QuickFilters({
  options,
  selected,
  onChange
}: {
  options: { value: string; label: string; count?: number }[];
  selected: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="quick-filters">
      {options.map((opt) => (
        <button
          key={opt.value}
          className={`quick-filter-chip ${selected === opt.value ? "active" : ""}`}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
          {opt.count !== undefined ? <span className="count">{opt.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

/**
 * 搜索框（独立使用）
 */
export function SearchBox({
  value,
  onChange,
  onSearch,
  placeholder = "搜索..."
}: {
  value: string;
  onChange: (value: string) => void;
  onSearch?: () => void;
  placeholder?: string;
}) {
  return (
    <div className="search-box">
      <Search size={16} />
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && onSearch) {
            onSearch();
          }
        }}
      />
      {value ? (
        <button className="clear-search" onClick={() => onChange("")} aria-label="清除搜索">
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}

/**
 * 活动筛选标签显示
 */
export function ActiveFilters({
  filters,
  values,
  onRemove,
  onClear
}: {
  filters: FilterConfig[];
  values: FilterValues;
  onRemove: (id: string) => void;
  onClear: () => void;
}) {
  const activeFilters = filters.filter((f) => {
    const value = values[f.id];
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "boolean") return value;
    if (typeof value === "object" && value !== null) {
      const range = value as { from?: string; to?: string };
      return range.from || range.to;
    }
    return value && value !== "";
  });

  if (activeFilters.length === 0) return null;

  function getFilterLabel(filter: FilterConfig): string {
    const value = values[filter.id];
    if (Array.isArray(value)) {
      return `${filter.label}: ${value.length} 项`;
    }
    if (typeof value === "boolean") {
      return filter.label;
    }
    if (typeof value === "object" && value !== null) {
      const range = value as { from?: string; to?: string };
      return `${filter.label}: ${range.from || "..."} ~ ${range.to || "..."}`;
    }
    if (filter.type === "select") {
      const option = filter.options?.find((opt) => opt.value === value);
      return `${filter.label}: ${option?.label || value}`;
    }
    return `${filter.label}: ${value}`;
  }

  return (
    <div className="active-filters">
      <span className="active-filters-label">已应用筛选:</span>
      <div className="active-filter-tags">
        {activeFilters.map((filter) => (
          <button key={filter.id} className="active-filter-tag" onClick={() => onRemove(filter.id)}>
            {getFilterLabel(filter)}
            <X size={12} />
          </button>
        ))}
      </div>
      <Button icon={<X size={14} />} onClick={onClear}>
        清空全部
      </Button>
    </div>
  );
}
