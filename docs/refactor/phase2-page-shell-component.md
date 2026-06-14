# Phase 2: 创建 PageShell 统一框架

## 一、改造目标

创建一个统一的 **PageShell** 组件，参考 Hermes Agent 的 `PageSearchShell`，为所有功能页提供一致的布局结构。

### 问题诊断

**当前状态：** 每个功能页各自实现布局
```typescript
// 40 个功能页，40 种布局方式
CapabilitiesWorkspace.tsx - 独立布局
SettingsWorkspace.tsx - 独立布局
ModelsWorkspace.tsx - 独立布局
...
```

**目标状态：** 所有页面使用统一框架
```typescript
// 所有页面继承相同的结构
<PageShell title="..." searchValue="..." filters={...}>
  {/* 具体内容 */}
</PageShell>
```

---

## 二、PageShell 组件设计

### 2.1 组件接口定义

```typescript
// desktop/src/components/PageShell.tsx

export interface PageShellProps {
  // 必需
  title: string;              // 页面标题
  children: ReactNode;        // 主内容区

  // 可选 - 搜索
  searchValue?: string;
  searchPlaceholder?: string;
  onSearchChange?: (value: string) => void;
  searchDisabled?: boolean;

  // 可选 - 筛选器（如 Tab、标签）
  filters?: ReactNode;

  // 可选 - 操作按钮
  actions?: ReactNode;        // 右上角操作按钮区域
  
  // 可选 - 加载状态
  loading?: boolean;
  loadingText?: string;

  // 可选 - 空状态
  empty?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;

  // 可选 - 布局选项
  contentPadding?: boolean;   // 内容区是否有内边距，默认 true
  fullHeight?: boolean;       // 内容区是否占满高度，默认 true
}
```

### 2.2 组件结构

```
┌─────────────────────────────────────────┐
│ Header                                   │
│ ┌─────────┬─────────────┬─────────────┐ │
│ │ Title   │  SearchBar  │  Actions    │ │
│ └─────────┴─────────────┴─────────────┘ │
├─────────────────────────────────────────┤
│ Filters (可选)                           │
│ ┌─────────────────────────────────────┐ │
│ │ Tab | Tab | Tab  或  标签筛选        │ │
│ └─────────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ Main Content                             │
│ ┌─────────────────────────────────────┐ │
│ │                                     │ │
│ │  {children}                         │ │
│ │                                     │ │
│ │                                     │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### 2.3 完整实现

```typescript
import { Loader2, Search } from "lucide-react";
import type { ReactNode } from "react";
import "./PageShell.css";

export interface PageShellProps {
  title: string;
  children: ReactNode;
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
  emptyDescription?: string;
  emptyAction?: ReactNode;
  contentPadding?: boolean;
  fullHeight?: boolean;
}

export function PageShell({
  title,
  children,
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
  fullHeight = true,
}: PageShellProps) {
  return (
    <section
      className={`page-shell ${fullHeight ? "full-height" : ""}`}
      aria-label={title}
    >
      {/* Header */}
      <header className="page-shell-header">
        <div className="page-shell-header-left">
          <h1 className="page-shell-title">{title}</h1>
        </div>

        <div className="page-shell-header-right">
          {/* Search Bar */}
          {onSearchChange && (
            <div className="page-shell-search">
              <Search size={14} />
              <input
                type="text"
                value={searchValue || ""}
                placeholder={searchPlaceholder}
                onChange={(e) => onSearchChange(e.target.value)}
                disabled={searchDisabled}
              />
            </div>
          )}

          {/* Actions */}
          {actions && <div className="page-shell-actions">{actions}</div>}
        </div>
      </header>

      {/* Filters */}
      {filters && <div className="page-shell-filters">{filters}</div>}

      {/* Main Content */}
      <main
        className={`page-shell-content ${contentPadding ? "with-padding" : ""}`}
      >
        {loading ? (
          <div className="page-shell-loading">
            <Loader2 className="spinner" size={24} />
            <span>{loadingText}</span>
          </div>
        ) : empty ? (
          <div className="page-shell-empty">
            <div className="page-shell-empty-content">
              <h3>{emptyTitle}</h3>
              {emptyDescription && <p>{emptyDescription}</p>}
              {emptyAction}
            </div>
          </div>
        ) : (
          children
        )}
      </main>
    </section>
  );
}

// 导出工具组件
export function PageShellGrid({ children, columns = 3 }: { children: ReactNode; columns?: number }) {
  return (
    <div className="page-shell-grid" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
      {children}
    </div>
  );
}

export function PageShellList({ children }: { children: ReactNode }) {
  return <div className="page-shell-list">{children}</div>;
}
```

### 2.4 样式实现

```css
/* desktop/src/components/PageShell.css */

.page-shell {
  display: flex;
  flex-direction: column;
  background: var(--background);
  overflow: hidden;
}

.page-shell.full-height {
  height: 100%;
}

/* Header */
.page-shell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
  gap: 1rem;
  flex-shrink: 0;
}

.page-shell-header-left {
  flex: 1;
  min-width: 0;
}

.page-shell-header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.page-shell-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
  color: var(--foreground);
}

/* Search */
.page-shell-search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: var(--input-background);
  border: 1px solid var(--border);
  border-radius: 0.375rem;
  min-width: 200px;
}

.page-shell-search svg {
  color: var(--muted-foreground);
  flex-shrink: 0;
}

.page-shell-search input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 0.875rem;
  color: var(--foreground);
}

.page-shell-search input::placeholder {
  color: var(--muted-foreground);
}

/* Actions */
.page-shell-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Filters */
.page-shell-filters {
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
  flex-shrink: 0;
}

/* Content */
.page-shell-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.page-shell-content.with-padding {
  padding: 1rem 1.5rem;
}

/* Loading State */
.page-shell-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 0.75rem;
  color: var(--muted-foreground);
}

.page-shell-loading .spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Empty State */
.page-shell-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
}

.page-shell-empty-content {
  text-align: center;
  max-width: 400px;
}

.page-shell-empty-content h3 {
  font-size: 1rem;
  font-weight: 500;
  margin: 0 0 0.5rem 0;
  color: var(--foreground);
}

.page-shell-empty-content p {
  font-size: 0.875rem;
  color: var(--muted-foreground);
  margin: 0 0 1rem 0;
}

/* Grid Layout */
.page-shell-grid {
  display: grid;
  gap: 1rem;
}

/* List Layout */
.page-shell-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

/* Responsive */
@media (max-width: 768px) {
  .page-shell-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .page-shell-header-right {
    width: 100%;
    flex-direction: column;
  }

  .page-shell-search {
    width: 100%;
  }
}
```

---

## 三、迁移指南

### 3.1 迁移前后对比

#### 示例1：SettingsWorkspace

**迁移前：**
```typescript
export function SettingsWorkspace() {
  return (
    <section className="settings-workspace">
      <header>
        <h1>设置</h1>
        <div className="search-box">
          <input placeholder="搜索设置..." />
        </div>
      </header>
      <main>
        {/* 内容 */}
      </main>
    </section>
  );
}
```

**迁移后：**
```typescript
import { PageShell } from "@/components/PageShell";

export function SettingsWorkspace() {
  const [search, setSearch] = useState("");

  return (
    <PageShell
      title="设置"
      searchValue={search}
      searchPlaceholder="搜索设置..."
      onSearchChange={setSearch}
    >
      {/* 内容 */}
    </PageShell>
  );
}
```

#### 示例2：带 Tab 筛选的页面

**迁移后：**
```typescript
export function IntegrationsWorkspace() {
  const [activeTab, setActiveTab] = useState("mcp");
  const [search, setSearch] = useState("");

  return (
    <PageShell
      title="集成中心"
      searchValue={search}
      onSearchChange={setSearch}
      filters={
        <div className="tab-filters">
          <button
            className={activeTab === "mcp" ? "active" : ""}
            onClick={() => setActiveTab("mcp")}
          >
            MCP 连接器
          </button>
          <button
            className={activeTab === "plugins" ? "active" : ""}
            onClick={() => setActiveTab("plugins")}
          >
            插件与技能
          </button>
        </div>
      }
      actions={
        <button onClick={() => console.log("refresh")}>
          刷新
        </button>
      }
    >
      {activeTab === "mcp" && <McpPanel />}
      {activeTab === "plugins" && <PluginsPanel />}
    </PageShell>
  );
}
```

#### 示例3：带加载和空状态

```typescript
export function ModelsWorkspace() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);

  return (
    <PageShell
      title="模型管理"
      loading={loading}
      loadingText="加载模型列表..."
      empty={!loading && models.length === 0}
      emptyTitle="暂无模型"
      emptyDescription="请先配置 MCP 连接器"
      emptyAction={
        <button onClick={() => navigate("/integrations")}>
          前往集成中心
        </button>
      }
    >
      <PageShellList>
        {models.map((model) => (
          <ModelCard key={model.id} model={model} />
        ))}
      </PageShellList>
    </PageShell>
  );
}
```

### 3.2 迁移优先级

| 优先级 | 页面 | 理由 |
|--------|------|------|
| P0 | SettingsWorkspace | 高频使用 |
| P0 | RunsEventsPage | 高频使用 |
| P0 | IntegrationsWorkspace (新建) | 核心功能 |
| P1 | ModelsWorkspace | 用户可见度高 |
| P1 | ReadinessHealthPage | 系统监控 |
| P1 | FinanceLabHome (新建) | 核心功能 |
| P2 | 其他金融页面 | 逐步迁移 |

### 3.3 迁移检查清单

每个页面迁移时检查：
- [ ] 删除自定义的 header 布局
- [ ] 使用 `PageShell` 的 `title` prop
- [ ] 如有搜索，使用 `searchValue` + `onSearchChange`
- [ ] 如有 Tab，使用 `filters` prop
- [ ] 如有操作按钮，使用 `actions` prop
- [ ] 测试加载状态和空状态
- [ ] 更新相关 CSS，移除冗余样式

---

## 四、实施步骤

### Step 1: 创建 PageShell 组件

```bash
# 创建组件文件
touch desktop/src/components/PageShell.tsx
touch desktop/src/components/PageShell.css
```

复制上面的完整实现代码。

### Step 2: 迁移第一个页面（SettingsWorkspace）

```bash
# 编辑文件
code desktop/src/features/settings/SettingsWorkspace.tsx
```

**修改步骤：**
1. 导入 `PageShell`
2. 删除自定义的 header 结构
3. 用 `<PageShell>` 包裹内容
4. 传入 `title`, `searchValue`, `onSearchChange` 等 props
5. 测试功能是否正常

### Step 3: 迁移其他高优先级页面

按照优先级列表逐一迁移：
- RunsEventsPage
- ModelsWorkspace
- ReadinessHealthPage

### Step 4: 创建新页面时使用 PageShell

所有新建的功能页（如 IntegrationsWorkspace、FinanceLabHome）直接使用 `PageShell`。

### Step 5: 逐步迁移剩余页面

在接下来的 2-3 周内，逐步迁移所有功能页。

---

## 五、测试计划

### 5.1 单元测试

```typescript
// desktop/src/components/PageShell.test.tsx

import { render, screen, fireEvent } from "@testing-library/react";
import { PageShell } from "./PageShell";

describe("PageShell", () => {
  it("renders title", () => {
    render(<PageShell title="测试页面">内容</PageShell>);
    expect(screen.getByText("测试页面")).toBeInTheDocument();
  });

  it("renders search bar when onSearchChange provided", () => {
    const handleSearch = jest.fn();
    render(
      <PageShell title="测试" onSearchChange={handleSearch}>
        内容
      </PageShell>
    );
    const input = screen.getByPlaceholderText("搜索...");
    fireEvent.change(input, { target: { value: "test" } });
    expect(handleSearch).toHaveBeenCalledWith("test");
  });

  it("shows loading state", () => {
    render(
      <PageShell title="测试" loading loadingText="加载中...">
        内容
      </PageShell>
    );
    expect(screen.getByText("加载中...")).toBeInTheDocument();
    expect(screen.queryByText("内容")).not.toBeInTheDocument();
  });

  it("shows empty state", () => {
    render(
      <PageShell title="测试" empty emptyTitle="暂无数据">
        内容
      </PageShell>
    );
    expect(screen.getByText("暂无数据")).toBeInTheDocument();
    expect(screen.queryByText("内容")).not.toBeInTheDocument();
  });
});
```

### 5.2 视觉回归测试

- [ ] 对比迁移前后的截图
- [ ] 确认布局一致性
- [ ] 检查响应式布局
- [ ] 检查深色模式

---

## 六、性能优化

### 6.1 懒加载优化

对于大型列表，使用虚拟滚动：

```typescript
import { useVirtualizer } from "@tanstack/react-virtual";

export function LargeListPage() {
  const items = useLargeDataset();
  const parentRef = useRef(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 60,
  });

  return (
    <PageShell title="大列表">
      <div ref={parentRef} style={{ height: "100%", overflow: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((virtualItem) => (
            <div key={virtualItem.key} style={virtualItem.style}>
              {items[virtualItem.index]}
            </div>
          ))}
        </div>
      </div>
    </PageShell>
  );
}
```

### 6.2 搜索防抖

```typescript
import { useMemo } from "react";
import { debounce } from "lodash";

export function SearchableList() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  const debouncedSetSearch = useMemo(
    () => debounce((value: string) => setDebouncedSearch(value), 300),
    []
  );

  const handleSearchChange = (value: string) => {
    setSearch(value);
    debouncedSetSearch(value);
  };

  return (
    <PageShell
      title="可搜索列表"
      searchValue={search}
      onSearchChange={handleSearchChange}
    >
      <FilteredList query={debouncedSearch} />
    </PageShell>
  );
}
```

---

## 七、文档更新

### 7.1 组件文档

创建 `docs/components/PageShell.md`，包含：
- 组件说明
- Props 文档
- 使用示例
- 最佳实践

### 7.2 迁移指南

创建 `docs/guides/migrate-to-page-shell.md`，包含：
- 为什么要迁移
- 如何迁移（分步骤）
- 常见问题
- 迁移检查清单
