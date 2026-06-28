import { ChevronDown, ChevronUp, Filter, Search, X } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { Button } from "./ui";

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

function isActiveFilterValue(value: FilterValue | undefined) {
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value.trim() !== "";
  if (value && typeof value === "object") return Boolean(value.from || value.to);
  return false;
}

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
  const activeCount = filters.filter((filter) => isActiveFilterValue(values[filter.id])).length;
  const hasActiveFilters = activeCount > 0;

  function updateFilter(id: string, value: FilterValue) {
    onChange({ ...values, [id]: value });
  }

  return (
    <div className="filter-bar" data-testid="filter-bar">
      <div className="filter-bar-header">
        <div className="filter-bar-title">
          <Filter size={16} />
          <span>筛选条件</span>
          {hasActiveFilters ? <span className="filter-count">{activeCount} 个筛选</span> : null}
        </div>
        <div className="filter-bar-actions">
          {hasActiveFilters ? (
            <Button data-testid="filter-clear-all" icon={<X size={14} />} onClick={onClear}>
              清空
            </Button>
          ) : null}
          {filters.length > 3 ? (
            <Button
              data-testid="filter-expand-toggle"
              icon={expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? "收起" : "展开"}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="filter-controls">
        {visibleFilters.map((filter) => (
          <FilterControl key={filter.id} filter={filter} value={values[filter.id]} onChange={(value) => updateFilter(filter.id, value)} />
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
              data-testid={`filter-${filter.id}`}
              type="text"
              value={String(value || "")}
              placeholder={filter.placeholder || "搜索..."}
              onChange={(event) => onChange(event.target.value)}
            />
          </div>
        </div>
      );
    case "select":
      return (
        <div className="filter-control filter-select">
          <label>{filter.label}</label>
          <select data-testid={`filter-${filter.id}`} value={String(value || "")} onChange={(event) => onChange(event.target.value)}>
            <option value="">全部</option>
            {filter.options?.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      );
    case "multiselect": {
      const selected = Array.isArray(value) ? value : [];
      return (
        <div className="filter-control filter-multiselect">
          <label>{filter.label}</label>
          <div className="multiselect-options">
            {filter.options?.map((option) => (
              <label key={option.value} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selected.includes(option.value)}
                  onChange={(event) => {
                    const next = event.target.checked ? [...selected, option.value] : selected.filter((item) => item !== option.value);
                    onChange(next);
                  }}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </div>
      );
    }
    case "daterange": {
      const range = (value as { from?: string; to?: string }) || {};
      return (
        <div className="filter-control filter-daterange">
          <label>{filter.label}</label>
          <div className="daterange-inputs">
            <input data-testid={`filter-${filter.id}-from`} type="date" value={range.from || ""} onChange={(event) => onChange({ ...range, from: event.target.value })} />
            <span>至</span>
            <input data-testid={`filter-${filter.id}-to`} type="date" value={range.to || ""} onChange={(event) => onChange({ ...range, to: event.target.value })} />
          </div>
        </div>
      );
    }
    case "toggle":
      return (
        <div className="filter-control filter-toggle">
          <label className="checkbox-label">
            <input data-testid={`filter-${filter.id}`} type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
            <span>{filter.label}</span>
          </label>
        </div>
      );
    default:
      return null;
  }
}

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
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`quick-filter-chip ${selected === option.value ? "active" : ""}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined ? <span className="count">{option.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

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
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && onSearch) {
            onSearch();
          }
        }}
      />
      {value ? (
        <button className="clear-search" type="button" onClick={() => onChange("")} aria-label="清除搜索">
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}

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
  const activeFilters = filters.filter((filter) => isActiveFilterValue(values[filter.id]));

  if (activeFilters.length === 0) return null;

  function getFilterLabel(filter: FilterConfig): ReactNode {
    const value = values[filter.id];
    if (Array.isArray(value)) {
      return `${filter.label}: ${value.length} 项`;
    }
    if (typeof value === "boolean") {
      return filter.label;
    }
    if (value && typeof value === "object") {
      const range = value as { from?: string; to?: string };
      return `${filter.label}: ${range.from || "..."} ~ ${range.to || "..."}`;
    }
    if (filter.type === "select") {
      const option = filter.options?.find((item) => item.value === value);
      return `${filter.label}: ${option?.label || value}`;
    }
    return `${filter.label}: ${value}`;
  }

  return (
    <div className="active-filters">
      <span className="active-filters-label">已应用筛选</span>
      <div className="active-filter-tags">
        {activeFilters.map((filter) => (
          <button key={filter.id} type="button" className="active-filter-tag" onClick={() => onRemove(filter.id)}>
            {getFilterLabel(filter)}
            <X size={12} />
          </button>
        ))}
      </div>
      <Button data-testid="active-filters-clear" icon={<X size={14} />} onClick={onClear}>
        清空全部
      </Button>
    </div>
  );
}
