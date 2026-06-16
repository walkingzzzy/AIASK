import { Loader2, Search } from "lucide-react";
import type { ReactNode } from "react";

export interface PageShellProps {
  title: string;
  children?: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  searchValue?: string;
  searchPlaceholder?: string;
  onSearchChange?: (value: string) => void;
  searchDisabled?: boolean;
  filters?: ReactNode;
  actions?: ReactNode;
  loading?: boolean;
  loadingText?: string;
  empty?: boolean;
  emptyTitle?: string;
  emptyDescription?: ReactNode;
  emptyAction?: ReactNode;
  contentPadding?: boolean;
  fullHeight?: boolean;
}

export function PageShell({
  title,
  children,
  eyebrow,
  description,
  searchValue,
  searchPlaceholder = "搜索...",
  onSearchChange,
  searchDisabled = false,
  filters,
  actions,
  loading = false,
  loadingText = "加载中...",
  empty = false,
  emptyTitle = "暂无数据",
  emptyDescription,
  emptyAction,
  contentPadding = true,
  fullHeight = true
}: PageShellProps) {
  return (
    <section className={`page-shell ${fullHeight ? "full-height" : ""}`} aria-label={title}>
      <header className="page-shell-header">
        <div className="page-shell-heading">
          {eyebrow && <span className="page-shell-eyebrow">{eyebrow}</span>}
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </div>
        {(onSearchChange || actions) && (
          <div className="page-shell-header-actions">
            {onSearchChange && (
              <label className="page-shell-search">
                <Search size={14} />
                <input
                  disabled={searchDisabled}
                  onChange={(event) => onSearchChange(event.target.value)}
                  placeholder={searchPlaceholder}
                  type="search"
                  value={searchValue || ""}
                />
              </label>
            )}
            {actions && <div className="page-shell-actions">{actions}</div>}
          </div>
        )}
      </header>

      {filters && <div className="page-shell-filters">{filters}</div>}

      <main className={`page-shell-content ${contentPadding ? "with-padding" : ""}`}>
        {loading ? (
          <div className="page-shell-state" role="status">
            <Loader2 className="spin" size={22} />
            <span>{loadingText}</span>
          </div>
        ) : empty ? (
          <div className="page-shell-state empty">
            <h2>{emptyTitle}</h2>
            {emptyDescription && <p>{emptyDescription}</p>}
            {emptyAction}
          </div>
        ) : (
          children
        )}
      </main>
    </section>
  );
}

export function PageShellGrid({ children, min = 220 }: { children: ReactNode; min?: number }) {
  return <div className="page-shell-grid" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))` }}>{children}</div>;
}

export function PageShellList({ children }: { children: ReactNode }) {
  return <div className="page-shell-list">{children}</div>;
}
