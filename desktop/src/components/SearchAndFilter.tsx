import { Filter, Search, X } from "lucide-react";
import { useState } from "react";

import { Button } from "./ui";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  onClear?: () => void;
}

export function SearchBar({ value, onChange, placeholder = "搜索...", onClear }: SearchBarProps) {
  return (
    <div
      className="search-bar"
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        width: "100%"
      }}
    >
      <Search
        size={18}
        style={{
          position: "absolute",
          left: "0.75rem",
          color: "#9ca3af"
        }}
      />
      <input
        data-testid="search-input"
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        style={{
          width: "100%",
          padding: "0.5rem 2.5rem 0.5rem 2.5rem",
          border: "1px solid #d1d5db",
          borderRadius: "0.375rem",
          fontSize: "0.875rem"
        }}
      />
      {value ? (
        <button
          type="button"
          onClick={() => {
            onChange("");
            onClear?.();
          }}
          style={{
            position: "absolute",
            right: "0.75rem",
            border: "none",
            background: "transparent",
            cursor: "pointer",
            padding: "0.25rem",
            display: "flex",
            alignItems: "center",
            color: "#6b7280"
          }}
        >
          <X size={16} />
        </button>
      ) : null}
    </div>
  );
}

interface FilterOption {
  label: string;
  value: string;
}

interface FilterPanelProps {
  filters: {
    label: string;
    key: string;
    options: FilterOption[];
    value: string;
  }[];
  onChange: (key: string, value: string) => void;
  onReset?: () => void;
}

export function FilterPanel({ filters, onChange, onReset }: FilterPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const hasActiveFilters = filters.some((filter) => filter.value !== "all" && filter.value !== "");

  return (
    <div className="filter-panel" style={{ position: "relative" }}>
      <Button
        data-testid="filter-button"
        onClick={() => setIsOpen((current) => !current)}
        tone={hasActiveFilters ? "info" : "neutral"}
        icon={<Filter size={16} />}
      >
        筛选 {hasActiveFilters && `(${filters.filter((filter) => filter.value !== "all" && filter.value !== "").length})`}
      </Button>

      {isOpen ? (
        <>
          <div
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 40
            }}
            onClick={() => setIsOpen(false)}
          />
          <div
            className="filter-dropdown"
            style={{
              position: "absolute",
              top: "100%",
              right: 0,
              marginTop: "0.5rem",
              background: "white",
              border: "1px solid #e5e7eb",
              borderRadius: "0.375rem",
              boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
              zIndex: 50,
              minWidth: "280px",
              padding: "1rem"
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {filters.map((filter) => (
                <label key={filter.key} className="field">
                  <span style={{ fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.25rem", display: "block" }}>{filter.label}</span>
                  <select
                    data-testid={`filter-${filter.key}`}
                    value={filter.value}
                    onChange={(event) => onChange(filter.key, event.target.value)}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      border: "1px solid #d1d5db",
                      borderRadius: "0.375rem",
                      fontSize: "0.875rem"
                    }}
                  >
                    {filter.options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}

              {hasActiveFilters && onReset ? (
                <Button data-testid="filter-reset" onClick={onReset} tone="neutral" style={{ width: "100%" }}>
                  重置筛选
                </Button>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
