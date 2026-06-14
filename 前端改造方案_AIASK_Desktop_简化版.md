# AIASK Desktop 前端改造方案

**版本**: v3.0-detailed  
**日期**: 2026-06-14  
**参考**: Hermes Agent Desktop UI/UX  
**详细方案**: 参见 `docs/refactor/` 目录下的分阶段实施文档

---

## 文档导航

- **本文档**：整体方案概览
- **详细实施方案**：
  - [Phase 1: 侧边栏精简](docs/refactor/phase1-sidebar-simplification.md) - 33个导航项 → 6个核心导航
  - [Phase 2: PageShell 组件](docs/refactor/phase2-page-shell-component.md) - 统一页面框架
  - [Phase 3: 路由系统](docs/refactor/phase3-route-system.md) - 真正的URL路由
  - [实施路线图](docs/refactor/implementation-roadmap.md) - 8周详细计划

---

## 一、现状分析与改造目标

### 1.1 当前架构问题（定量分析）

**复杂度过高**：
- ❌ **侧边栏导航项：33 个** (目标：6 个)
  - 主工作区：8 项
  - 高级金融：9 项
  - 高级运维：6 项
  - 旧入口/诊断：10 项
- ❌ **总视图数：40+ 个** (目标：6 个核心 + 子页面)
- ❌ **页面布局方式：40 种** (目标：1 种统一框架 PageShell)
- ❌ **URL 路由：无** (目标：真正的路由系统)
- ❌ **侧边栏代码：233 行** (目标：~120 行)

**用户体验问题**：
- 新用户学习曲线陡峭，难以快速找到核心功能
- 过多的入口分散用户注意力（信息过载）
- 无法通过 URL 分享当前页面
- 刷新页面会回到首页（状态丢失）

### 1.2 Hermes Agent 参考架构优势

**极简导航**：
- ✅ 核心导航只有 3-4 个入口
- ✅ 会话管理为主体，导航为辅助
- ✅ 统一的设置入口（顶栏齿轮图标）

**统一页面框架**：
- ✅ 所有功能页使用 `PageSearchShell` 统一框架
- ✅ 一致的布局：标题 + 搜索 + 筛选器 + 内容
- ✅ 统一的加载和空状态处理

**真正的路由**：
- ✅ URL 反映当前页面（`/skills`, `/settings/keys`）
- ✅ 支持浏览器前进/后退
- ✅ 刷新保持当前状态
- ✅ 可分享具体页面链接

---

## 二、改造目标与核心原则

### 2.1 核心原则

1. **极简化**: 33个导航 → 6个核心导航（减少 82%）
2. **统一化**: 40种页面布局 → 1个 PageShell 框架
3. **路由化**: 状态切换 → 真正的 URL 路由系统
4. **渐进式**: 3个 Phase，每个 Phase 独立测试

### 2.2 三大改造 Phase

#### Phase 1: 侧边栏精简（Week 1-2）
**目标**: 33个导航项 → 6个核心导航

**核心导航（6个）**：
1. 🏠 **工作台** (`workbench`) - 主工作面，保持不变
2. 📊 **运行与事件** (`runs-events`) - 核心功能，查看历史和审批
3. 🧩 **集成中心** (`integrations`) - **新建**，合并 MCP/工具/技能/网关
4. 💰 **金融实验室** (`finance-lab`) - 改造为主入口，下设9个子模块
5. 🛡️ **系统准备度** (`readiness-health`) - 系统状态监控
6. ⚙️ **设置** (`settings`) - 移到顶栏齿轮图标

**合并规则**：
- **集成中心** = MCP连接器 + 插件技能 + 工具审批 + 网关配置（4个Tab）
- **金融实验室** = 财务管理 + 市场温度 + 量化研究 + 策略工厂 + 因子工厂 + 孵化池 + 数据同步 + 工作流 + 工厂事件（9个子模块）
- **完全移除**：overview、agent、capabilities、coverage、diagnostics、event-console、skills、user、extensions-pilot（10个旧入口）

**详细方案**: 参见 [phase1-sidebar-simplification.md](docs/refactor/phase1-sidebar-simplification.md)

#### Phase 2: PageShell 统一框架（Week 3-4）
**目标**: 创建统一的页面框架组件

**PageShell 组件结构**：
```
┌─────────────────────────────────────────┐
│ Header: Title + SearchBar + Actions     │
├─────────────────────────────────────────┤
│ Filters: Tabs / Tags (可选)             │
├─────────────────────────────────────────┤
│ Main Content: {children}                 │
│ - 支持加载状态                            │
│ - 支持空状态                              │
│ - 支持网格/列表布局                       │
└─────────────────────────────────────────┘
```

**核心特性**：
- ✅ 统一的 header 布局（标题 + 搜索 + 操作按钮）
- ✅ 可选的筛选器区域（Tab、标签等）
- ✅ 内置加载状态和空状态
- ✅ 响应式设计

**迁移优先级**：
- P0: SettingsWorkspace, RunsEventsPage, IntegrationsWorkspace（新建）
- P1: ModelsWorkspace, ReadinessHealthPage, FinanceLabHome（新建）
- P2: 其他金融页面

**详细方案**: 参见 [phase2-page-shell-component.md](docs/refactor/phase2-page-shell-component.md)

#### Phase 3: 真正的路由系统（Week 5-6）
**目标**: 添加 React Router 6，实现真正的 URL 路由

**路由表设计**：
```typescript
/ → 工作台
/runs → 运行与事件
/integrations → 集成中心
  /integrations/mcp → MCP 连接器
  /integrations/plugins → 插件与技能
  /integrations/tools → 工具审批
  /integrations/gateway → 网关配置
/finance → 金融实验室
  /finance/manager → 财务管理
  /finance/market-temperature → 市场温度
  /finance/quant → 量化研究
  ... (其他金融子模块)
/readiness → 系统准备度
/settings → 设置
/thread/:threadId → 线程详情
```

**核心改动**：
- 使用 `<BrowserRouter>` 包裹应用
- 侧边栏导航从 `onClick` 改为 `<Link to="...">`
- 嵌套路由使用 `<Outlet>`
- 支持 URL 参数和查询字符串
- 添加面包屑导航

**详细方案**: 参见 [phase3-route-system.md](docs/refactor/phase3-route-system.md)

### 2.3 改造效果对比

| 指标 | 改造前 | 改造后 | 改进 |
|------|--------|--------|------|
| 侧边栏导航项 | 33 个 | 6 个 | ↓ 82% |
| 总视图数 | 40+ 个 | 6 个核心 + 子页面 | ↓ 85% |
| 页面布局方式 | 40 种 | 1 种（PageShell） | 统一 |
| URL 路由 | ❌ 无 | ✅ 有 | 新增 |
| 侧边栏代码行数 | 233 行 | ~120 行 | ↓ 50% |
| 页面开发时间 | 2-4 小时 | 30 分钟 | ↓ 75% |
| 学习成本 | 高（33个入口） | 低（6个入口） | ↓ 82% |

---

## 三、实施路线图

### 3.1 时间线（8周）

```
Week 1-2  ━━━━━━━━━━━━━━━━━━  Phase 1: 侧边栏精简
Week 3-4  ━━━━━━━━━━━━━━━━━━  Phase 2: PageShell 组件
Week 5-6  ━━━━━━━━━━━━━━━━━━  Phase 3: 路由系统
Week 7-8  ━━━━━━━━━━━━━━━━━━  Phase 4: 迁移和优化
```

### 3.2 Phase 1: 侧边栏精简（Week 1-2）

#### Day 1-2: 准备工作
```bash
# 1. 创建备份分支
git checkout -b backup/sidebar-before-refactor
git add . && git commit -m "backup: 侧边栏改造前完整快照"

# 2. 创建工作分支
git checkout -b refactor/phase1-sidebar-simplification

# 3. 分析依赖
grep -r "mainView.*==.*\"" desktop/src --include="*.tsx" > /tmp/mainview-usage.txt
```

#### Day 3-5: 核心代码修改
**修改文件**：
1. `desktop/src/views.ts` - 重写视图定义，只保留6个核心视图
2. `desktop/src/components/AppSidebar.tsx` - 简化侧边栏结构（233行 → ~120行）
3. `desktop/src/App.tsx` - 移除已删除视图的导入

**关键代码**：
```typescript
// desktop/src/views.ts
export const CORE_VIEWS = [
  'workbench',
  'runs-events',
  'integrations',      // 新建
  'finance-lab',       // 改造为主入口
  'readiness-health',
] as const;
```

#### Day 6-8: 创建新页面
**新建文件**：
1. `desktop/src/features/integrations/IntegrationsWorkspace.tsx` - 集成中心（4个Tab）
2. `desktop/src/features/finance-lab/FinanceLabHome.tsx` - 金融实验室主页（9个模块卡片）

#### Day 9-10: 测试
- [ ] 侧边栏只显示 6 个导航项
- [ ] 集成中心 4 个 Tab 正常切换
- [ ] 金融实验室显示 9 个模块卡片
- [ ] 旧导航项无法访问

**详细步骤**: 参见 [phase1-sidebar-simplification.md](docs/refactor/phase1-sidebar-simplification.md)

---

### 3.3 Phase 2: PageShell 组件（Week 3-4）

#### Day 1-2: 创建 PageShell 组件
```bash
touch desktop/src/components/PageShell.tsx
touch desktop/src/components/PageShell.css
touch desktop/src/components/PageShell.test.tsx
```

**组件接口**：
```typescript
interface PageShellProps {
  title: string;              // 页面标题
  children: ReactNode;        // 主内容
  searchValue?: string;       // 搜索值
  onSearchChange?: (value: string) => void;
  filters?: ReactNode;        // 筛选器（Tab、标签等）
  actions?: ReactNode;        // 操作按钮
  loading?: boolean;          // 加载状态
  empty?: boolean;            // 空状态
  emptyTitle?: string;
  emptyAction?: ReactNode;
}
```

#### Day 3-5: 迁移高优先级页面（3个）
1. SettingsWorkspace
2. RunsEventsPage
3. IntegrationsWorkspace（刚创建的）

**迁移步骤**（每个页面）：
```typescript
// 1. 导入 PageShell
import { PageShell } from '@/components/PageShell';

// 2. 删除自定义 header

// 3. 使用 PageShell 包裹
<PageShell
  title="页面标题"
  searchValue={search}
  onSearchChange={setSearch}
>
  {/* 原有内容 */}
</PageShell>
```

#### Day 6-8: 迁移中优先级页面（5个）
- ModelsWorkspace
- ReadinessHealthPage
- FinanceLabHome
- GatewayPage
- McpConnectorsPage

#### Day 9-10: 测试和文档
- 单元测试
- 组件文档
- 使用指南

**详细步骤**: 参见 [phase2-page-shell-component.md](docs/refactor/phase2-page-shell-component.md)

---

### 3.4 Phase 3: 路由系统（Week 5-6）

#### Day 1-2: 安装依赖和创建路由配置
```bash
npm install react-router-dom@^6.20.0
npm install --save-dev @types/react-router-dom
touch desktop/src/routes.ts
```

**路由配置**：
```typescript
// desktop/src/routes.ts
export const ROUTES = {
  HOME: '/',
  RUNS: '/runs',
  INTEGRATIONS: '/integrations',
  FINANCE_LAB: '/finance',
  READINESS: '/readiness',
  SETTINGS: '/settings',
  // 子路由
  INTEGRATIONS_MCP: '/integrations/mcp',
  FINANCE_MANAGER: '/finance/manager',
  // ...
} as const;
```

#### Day 3-5: 改造 App.tsx 和 AppSidebar
**App.tsx**：
```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom';

<BrowserRouter>
  <Routes>
    <Route path="/" element={<WorkbenchView />} />
    <Route path="/runs" element={<RunsEventsPage />} />
    <Route path="/integrations" element={<IntegrationsWorkspace />}>
      <Route path="mcp" element={<McpPanel />} />
      <Route path="plugins" element={<PluginsPanel />} />
    </Route>
    {/* 其他路由 */}
  </Routes>
</BrowserRouter>
```

**AppSidebar**：
```typescript
import { Link, useLocation } from 'react-router-dom';

// 从 onClick 改为 Link
<Link to="/runs" className={location.pathname === '/runs' ? 'active' : ''}>
  运行与事件
</Link>
```

#### Day 6-8: 实现嵌套路由
- 集成中心嵌套路由（4个Tab）
- 金融实验室嵌套路由（9个子模块）

#### Day 9-10: 测试
- [ ] 直接访问 URL 显示正确页面
- [ ] 浏览器前进/后退正常
- [ ] 刷新页面保持当前路由
- [ ] URL 参数正常

**详细步骤**: 参见 [phase3-route-system.md](docs/refactor/phase3-route-system.md)

---

### 3.5 Phase 4: 迁移和优化（Week 7-8）

#### Day 1-4: 迁移剩余页面
逐个迁移剩余的金融页面到 PageShell：
- QuantResearchWorkspace
- StrategyFactoryPanel
- FactorFactoryPanel
- IncubationFactoryPanel
- DataSyncWorkspace
- WorkflowsWorkspace
- FactoryEventTriggerPanel
- MarketTemperatureWorkspace
- FinancialManagerWorkspace

#### Day 5-6: 性能优化
1. **代码分割**：懒加载路由组件
2. **路由预加载**：鼠标悬停时预加载
3. **虚拟滚动**：大列表优化
4. **搜索防抖**：300ms 防抖

#### Day 7-8: 文档
1. 用户文档（功能位置迁移对照表）
2. 开发者文档（PageShell 使用指南）
3. 迁移指南（破坏性变更列表）

**详细步骤**: 参见 [implementation-roadmap.md](docs/refactor/implementation-roadmap.md)

---

## 四、关键技术细节

### 4.1 侧边栏简化后的结构

```typescript
// desktop/src/components/AppSidebar.tsx (简化后)

export function AppSidebar({ ... }) {
  return (
    <aside className="sidebar app-sidebar">
      {/* 1. 新建线程按钮 */}
      <button className="new-task-button" onClick={onNewTask}>
        <Plus size={16} />
        新建线程
      </button>

      {/* 2. 核心导航（6个，扁平化） */}
      <nav className="sidebar-nav" aria-label="Main navigation">
        <Link to="/" className={isActive('/') ? 'active' : ''}>
          <LayoutDashboard size={16} />
          工作台
        </Link>
        <Link to="/runs" className={isActive('/runs') ? 'active' : ''}>
          <Activity size={16} />
          运行与事件
        </Link>
        <Link to="/integrations" className={isActive('/integrations') ? 'active' : ''}>
          <Puzzle size={16} />
          集成中心
        </Link>
        <Link to="/finance" className={isActive('/finance') ? 'active' : ''}>
          <TrendingUp size={16} />
          金融实验室
        </Link>
        <Link to="/readiness" className={isActive('/readiness') ? 'active' : ''}>
          <Shield size={16} />
          系统准备度
        </Link>
      </nav>

      {/* 3. 搜索框 */}
      <div className="sidebar-search">
        <Search size={14} />
        <input placeholder="搜索线程..." />
      </div>

      {/* 4. 线程列表 */}
      <div className="thread-list">
        {threads.map(thread => (
          <ThreadItem key={thread.id} thread={thread} />
        ))}
      </div>

      {/* 5. 底部状态（简化版） */}
      <div className="sidebar-footer">
        <StatusBadge status={status} />
        <span>{tools.length} 工具</span>
      </div>
    </aside>
  );
}
```

**移除的元素**：
- ❌ `brand-row` 品牌栏（120-129行）
- ❌ `sidebar-project-card` 项目卡片（136-143行）
- ❌ `extension-slot-row` 扩展插槽（145-152行）
- ❌ `SidebarNavGroup` 分组组件（192-206行）

---

### 4.2 PageShell 统一框架

```typescript
// desktop/src/components/PageShell.tsx

export interface PageShellProps {
  title: string;
  children: ReactNode;
  searchValue?: string;
  searchPlaceholder?: string;
  onSearchChange?: (value: string) => void;
  filters?: ReactNode;        // Tab、标签等筛选器
  actions?: ReactNode;        // 右上角操作按钮
  loading?: boolean;          // 加载状态
  loadingText?: string;
  empty?: boolean;            // 空状态
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  contentPadding?: boolean;   // 内容区内边距
  fullHeight?: boolean;       // 占满高度
}

export function PageShell({ title, children, ... }: PageShellProps) {
  return (
    <section className="page-shell">
      {/* Header */}
      <header className="page-shell-header">
        <h1>{title}</h1>
        {onSearchChange && (
          <div className="page-shell-search">
            <Search size={14} />
            <input
              value={searchValue || ""}
              placeholder={searchPlaceholder}
              onChange={(e) => onSearchChange(e.target.value)}
            />
          </div>
        )}
        {actions && <div className="page-shell-actions">{actions}</div>}
      </header>

      {/* Filters */}
      {filters && <div className="page-shell-filters">{filters}</div>}

      {/* Main Content */}
      <main className="page-shell-content">
        {loading ? (
          <LoadingState text={loadingText} />
        ) : empty ? (
          <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
        ) : (
          children
        )}
      </main>
    </section>
  );
}
```

**使用示例**：
```typescript
// 带搜索和Tab的页面
export function IntegrationsWorkspace() {
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState("mcp");

  return (
    <PageShell
      title="集成中心"
      searchValue={search}
      onSearchChange={setSearch}
      filters={
        <TabGroup value={activeTab} onChange={setActiveTab}>
          <Tab value="mcp">MCP 连接器</Tab>
          <Tab value="plugins">插件与技能</Tab>
          <Tab value="tools">工具审批</Tab>
          <Tab value="gateway">网关配置</Tab>
        </TabGroup>
      }
    >
      <Outlet />
    </PageShell>
  );
}
```

---

### 4.3 路由系统实现

```typescript
// desktop/src/routes.ts
export const ROUTES = {
  HOME: '/',
  RUNS: '/runs',
  INTEGRATIONS: '/integrations',
  FINANCE_LAB: '/finance',
  READINESS: '/readiness',
  SETTINGS: '/settings',
  // 子路由
  INTEGRATIONS_MCP: '/integrations/mcp',
  INTEGRATIONS_PLUGINS: '/integrations/plugins',
  INTEGRATIONS_TOOLS: '/integrations/tools',
  INTEGRATIONS_GATEWAY: '/integrations/gateway',
  FINANCE_MANAGER: '/finance/manager',
  FINANCE_MARKET_TEMP: '/finance/market-temperature',
  // ...其他金融子路由
  THREAD: '/thread/:threadId',
} as const;

// desktop/src/App.tsx
export function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          {/* 主路由 */}
          <Route path={ROUTES.HOME} element={<WorkbenchView />} />
          <Route path={ROUTES.RUNS} element={<RunsEventsPage />} />
          <Route path={ROUTES.SETTINGS} element={<SettingsWorkspace />} />
          <Route path={ROUTES.READINESS} element={<ReadinessHealthPage />} />
          
          {/* 集成中心（嵌套路由） */}
          <Route path={ROUTES.INTEGRATIONS} element={<IntegrationsWorkspace />}>
            <Route index element={<Navigate to="mcp" replace />} />
            <Route path="mcp" element={<McpConnectorsPanel />} />
            <Route path="plugins" element={<PluginsSkillsPanel />} />
            <Route path="tools" element={<ToolsApprovalsPanel />} />
            <Route path="gateway" element={<GatewayPanel />} />
          </Route>
          
          {/* 金融实验室（嵌套路由） */}
          <Route path={ROUTES.FINANCE_LAB} element={<FinanceLabLayout />}>
            <Route index element={<FinanceLabHome />} />
            <Route path="manager" element={<FinancialManagerWorkspace />} />
            <Route path="market-temperature" element={<MarketTemperatureWorkspace />} />
            {/* 其他金融子路由 */}
          </Route>
          
          {/* 线程详情 */}
          <Route path={ROUTES.THREAD} element={<ThreadDetailView />} />
          
          {/* 404 */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
```

**URL 示例**：
```
http://localhost:3000/                        → 工作台
http://localhost:3000/runs                    → 运行与事件
http://localhost:3000/integrations/mcp        → 集成中心 → MCP连接器
http://localhost:3000/finance/market-temperature → 金融实验室 → 市场温度
http://localhost:3000/thread/abc123           → 线程详情
```

---

```
┌─────────────────────────────────┐
│  [AIASK]  Agent 工作台    [设置] │  ← 品牌 + 设置按钮
├─────────────────────────────────┤
│  [+] 新建对话              Ctrl+N │  ← 核心操作
├─────────────────────────────────┤
│  [🔍] 搜索会话...                │  ← 搜索框
└─────────────────────────────────┘
```

**改动点**：
- 简化品牌栏：移除项目卡片，项目信息移入设置
- 添加设置按钮：齿轮图标，点击打开设置面板
- 保留新建对话按钮：主要操作入口
- 保留搜索框：快速查找会话

#### 3.1.2 核心导航（5 个入口）

```
┌─────────────────────────────────┐
│  导航                             │
├─────────────────────────────────┤
│  🔍  搜索                         │  ← Search & History
│  🧩  插件                         │  ← Plugins & Skills
│  ⏰  自动化                       │  ← Automation & Scheduler
│  📊  金融工作台                   │  ← Finance Lab (核心)
│  ⚡  工作台                       │  ← Workbench (默认)
└─────────────────────────────────┘
```

**映射关系**：
- 搜索 → `runs-events` (运行/事件搜索)
- 插件 → `plugins-skills` (插件与技能)
- 自动化 → `automation` (自动化工作区)
- 金融工作台 → `finance-lab` (金融实验室)
- 工作台 → `workbench` (默认对话界面)

#### 3.1.3 会话列表

```
┌─────────────────────────────────┐
│  📌 已固定  [3]                   │  ← 可折叠
│    • 市场分析 - 600519            │
│    • 策略评审 - 因子挖掘          │
│    • 数据同步任务                 │
├─────────────────────────────────┤
│  💬 会话  [24/156]  [分组]        │  ← 可折叠、可分组
│    • 今日复盘分析                 │
│    • TDX行情策略                  │
│    • 增强AIASK MCP与Skills        │
│    ...                            │
│    [加载更多]                     │
└─────────────────────────────────┘
```

**保留功能**：
- 固定会话
- 按工作区分组
- 虚拟滚动（大列表优化）
- 拖拽排序

#### 3.1.4 底部状态栏（简化）

```
┌─────────────────────────────────┐
│  🟢 在线  |  156 工具  |  完整模式 │
└─────────────────────────────────┘
```

**移除**：项目详情卡片（迁移到设置 → 项目/上下文）

---

### 3.2 设置面板设计

#### 3.2.1 架构（参考 Hermes Settings）

采用 **Overlay 模式**（全屏弹窗，左侧导航 + 右侧内容）：

```
┌─────────────────────────────────────────────────────────────┐
│  [关闭]  设置                        [搜索设置...]           │
├───────────────┬─────────────────────────────────────────────┤
│               │                                              │
│ 基础设置      │                                              │
│  模型配置     │  当前显示的设置页面内容                      │
│  项目/上下文  │                                              │
│  外观         │                                              │
│               │                                              │
│ 金融配置      │                                              │
│  数据源       │                                              │
│  市场温度     │                                              │
│  策略工厂     │                                              │
│               │                                              │
│ 运维配置      │                                              │
│  Gateway      │                                              │
│  MCP连接器    │                                              │
│  API Keys     │                                              │
│               │                                              │
│ 关于          │                                              │
│  版本信息     │                                              │
│  [导出配置]   │                                              │
│  [导入配置]   │                                              │
│  [重置默认]   │                                              │
│               │                                              │
└───────────────┴─────────────────────────────────────────────┘
```

#### 3.2.2 设置分类整合

**一、基础设置**
- 模型配置 (`models`)
- 项目/上下文 (`projects-contexts`) ← 移入
- 外观 (新增，借鉴 Hermes AppearanceSettings)
- 用户画像 (`user` 部分内容)

**二、金融配置**
- 数据源 (StockDataSourcesPanel)
- 市场温度配置
- 策略工厂设置
- 因子工厂设置
- 孵化工厂设置

**三、运维配置**
- Gateway (`gateway`)
- MCP 连接器 (`mcp-connectors`)
- API Keys (新增，借鉴 Hermes KeysSettings)
- 准备度/健康 (`readiness-health` 部分)

**四、高级设置**
- 集成管理 (`integrations`)
- 工具审批 (`tools-intents-approvals`)
- 会话管理 (`sessions`) - 需要 Full Mode
- 扩展注册表 (`extensions-pilot`)

**五、关于**
- 版本信息
- 更新日志
- 配置导入/导出/重置

---

### 3.3 视图精简策略

#### 3.3.1 保留的核心视图（8 个）

| 视图 ID | 标签 | 访问方式 | 说明 |
|---------|------|----------|------|
| `workbench` | 工作台 | 侧边栏导航 | 默认对话界面 |
| `runs-events` | 搜索 | 侧边栏导航 | 运行/事件搜索 |
| `plugins-skills` | 插件 | 侧边栏导航 | 插件与技能管理 |
| `automation` | 自动化 | 侧边栏导航 | 自动化任务 |
| `finance-lab` | 金融工作台 | 侧边栏导航 | 金融任务模板入口 |
| `settings` | 设置 | 顶部设置按钮 | 统一设置面板 |
| `sessions` | 会话详情 | 程序内部调用 | 会话详情查看 |
| `tools-intents-approvals` | 审批 | 设置 → 高级 | 工具审批管理 |

#### 3.3.2 合并到设置的视图（15+ 个）

- `projects-contexts` → 设置 → 项目/上下文
- `models` → 设置 → 模型配置
- `gateway` → 设置 → Gateway
- `mcp-connectors` → 设置 → MCP 连接器
- `readiness-health` → 设置 → 准备度/健康
- `integrations` → 设置 → 集成管理
- `market-temperature` → 设置 → 金融配置 → 市场温度
- `data` → 设置 → 金融配置 → 数据源
- `strategy-factory` → 设置 → 金融配置 → 策略工厂
- `factor-factory` → 设置 → 金融配置 → 因子工厂
- `incubation` → 设置 → 金融配置 → 孵化工厂
- ... 其他金融/运维配置页面

#### 3.3.3 保留为高级入口的视图（可选）

通过 `finance-lab` 作为金融功能的统一入口：
- 金融经理台 (`financial-manager`)
- 量化研究 (`quant`)
- 工作流 (`workflows`)
- 工厂事件 (`factory-events`)

这些功能保留独立视图，但不在侧边栏直接显示，通过金融工作台的快捷卡片进入。

---

## 四、实现方案

### 4.1 组件改造清单

#### 4.1.1 AppSidebar.tsx 改造

**目标**：简化侧边栏结构

```typescript
// 新的侧边栏结构
<aside className="sidebar app-sidebar">
  {/* 1. 顶部：品牌 + 设置按钮 */}
  <div className="brand-row">
    <div className="brand-mark">...</div>
    <div>AIASK Agent 工作台</div>
    <IconButton onClick={() => onSelectView("settings")}>
      <Settings size={16} />
    </IconButton>
  </div>

  {/* 2. 新建对话按钮 */}
  <button className="new-task-button" onClick={onNewTask}>
    <Plus size={16} />
    新建对话
  </button>

  {/* 3. 搜索框 */}
  <div className="search-box">
    <Search size={14} />
    <input placeholder="搜索会话..." />
  </div>

  {/* 4. 核心导航（5 个） */}
  <nav className="core-navigation">
    <NavigationItem icon={Search} label="搜索" view="runs-events" />
    <NavigationItem icon={Puzzle} label="插件" view="plugins-skills" />
    <NavigationItem icon={CalendarClock} label="自动化" view="automation" />
    <NavigationItem icon={SearchCheck} label="金融工作台" view="finance-lab" />
    <NavigationItem icon={MessageSquare} label="工作台" view="workbench" />
  </nav>

  {/* 5. 会话列表 */}
  <SessionsList
    pinnedSessions={pinnedThreads}
    recentSessions={threads}
    onSelectThread={onSelectThread}
  />

  {/* 6. 底部状态栏（简化） */}
  <div className="sidebar-footer-simple">
    <StatusBadge status={status} />
    <span>{toolsCount} 工具</span>
    <span>{fullModeActive ? "完整模式" : "金融安全"}</span>
  </div>
</aside>
```

**移除**：
- `sidebar-project-card`（项目详情卡片）
- 多级折叠导航分组
- 复杂的 `VIEW_GROUPS` 渲染

#### 4.1.2 SettingsWorkspace.tsx 改造

**目标**：改为 Overlay 模式（参考 Hermes SettingsView）

```typescript
// 新的设置面板结构
export function SettingsWorkspace() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("model");
  
  return (
    <OverlayView onClose={() => onBackToApp()}>
      <OverlaySplitLayout>
        {/* 左侧导航 */}
        <OverlaySidebar>
          <SettingsNavSection title="基础设置">
            <SettingsNavItem icon={BrainCircuit} label="模型配置" />
            <SettingsNavItem icon={FolderGit2} label="项目/上下文" />
            <SettingsNavItem icon={Palette} label="外观" />
          </SettingsNavSection>
          
          <SettingsNavSection title="金融配置">
            <SettingsNavItem icon={Database} label="数据源" />
            <SettingsNavItem icon={Thermometer} label="市场温度" />
            <SettingsNavItem icon={Factory} label="策略工厂" />
          </SettingsNavSection>
          
          <SettingsNavSection title="运维配置">
            <SettingsNavItem icon={ServerCog} label="Gateway" />
            <SettingsNavItem icon={PlugZap} label="MCP 连接器" />
            <SettingsNavItem icon={KeyRound} label="API Keys" />
          </SettingsNavSection>
          
          {/* 底部操作按钮 */}
          <div className="settings-actions">
            <IconButton onClick={exportConfig} title="导出配置">
              <Download size={14} />
            </IconButton>
            <IconButton onClick={importConfig} title="导入配置">
              <Upload size={14} />
            </IconButton>
            <IconButton onClick={resetConfig} title="重置默认">
              <RefreshCw size={14} />
            </IconButton>
          </div>
        </OverlaySidebar>

        {/* 右侧内容 */}
        <OverlayMain>
          {renderSettingsPanel(activeTab)}
        </OverlayMain>
      </OverlaySplitLayout>
    </OverlayView>
  );
}
```

**关键改动**：
- 全屏 Overlay 弹窗，非内嵌页面
- 左右分栏布局（参考 Hermes）
- 设置分类清晰，导航在左侧
- 支持搜索设置项

#### 4.1.3 App.tsx 改造

**简化视图路由逻辑**：

```typescript
// 简化后的视图映射
const CORE_VIEWS = [
  "workbench",
  "runs-events", 
  "plugins-skills",
  "automation",
  "finance-lab",
  "settings"
];

// 视图渲染器只保留核心视图
const viewRenderers: Record<MainView, () => ReactNode> = {
  workbench: () => <WorkbenchView {...workbenchProps} />,
  "runs-events": () => <RunsEventsPage {...runsProps} />,
  "plugins-skills": () => <PluginsSkillsPage {...pluginsProps} />,
  automation: () => <AutomationWorkspace {...autoProps} />,
  "finance-lab": () => <FinanceLabPage {...financeProps} />,
  settings: () => <SettingsOverlay {...settingsProps} />,
};
```

**移除**：
- 复杂的 legacy 视图包装器
- 大量的条件渲染分支
- 不必要的视图懒加载（核心视图直接导入）

---

## 五、风险管理与回滚方案

### 5.1 主要风险与缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 用户找不到原有功能 | 高 | 中 | ✅ 提供迁移对照表<br>✅ 保留过渡期（1-2周） |
| 破坏现有功能 | 高 | 低 | ✅ 每个Phase独立测试<br>✅ 保持备份分支 |
| 性能退化 | 中 | 低 | ✅ 代码分割<br>✅ 虚拟滚动 |
| 路由冲突 | 中 | 中 | ✅ 统一路由配置<br>✅ 充分测试 |
| 第三方插件兼容性 | 中 | 低 | ✅ 保留扩展插槽<br>✅ 文档说明变更 |

### 5.2 回滚方案

#### 方案1: 回滚到备份分支
```bash
# 完全回滚
git checkout backup/sidebar-before-refactor
git branch -D refactor/phase1-sidebar-simplification

# 重新开始
git checkout -b refactor/phase1-sidebar-simplification
```

#### 方案2: 只回滚特定文件
```bash
# 回滚特定文件
git checkout backup/sidebar-before-refactor -- desktop/src/views.ts
git checkout backup/sidebar-before-refactor -- desktop/src/components/AppSidebar.tsx
```

#### 方案3: 功能开关（推荐）
```json
// 在 settings.json 中添加
{
  "ui": {
    "simplifiedMode": true,  // 新版简化模式
    "legacyMode": false      // 旧版完整模式（回退用）
  }
}
```

### 5.3 过渡方案

**在旧页面显示迁移提示**（过渡期使用）：
```typescript
// 旧的 tools 页面
export function LegacyToolsPage() {
  return (
    <div className="migration-notice">
      <h2>📢 此功能已迁移</h2>
      <p>工具审批功能现在在"集成中心"的"工具审批" Tab 中</p>
      <Link to="/integrations/tools">
        <button>前往新位置</button>
      </Link>
      <p className="small-text">此提示将在 2 周后移除</p>
    </div>
  );
}
```

---

## 六、测试计划

### 6.1 Phase 1 测试清单

#### 功能测试
- [ ] 侧边栏只显示 6 个导航项
- [ ] 点击"集成中心"显示 4 个 Tab
- [ ] 点击"金融实验室"显示 9 个模块卡片
- [ ] 旧导航项已移除（无法通过UI访问）
- [ ] 新建线程按钮正常
- [ ] 线程列表显示正常

#### UI测试
- [ ] 侧边栏高度适中，无滚动条
- [ ] 导航图标清晰，间距合理
- [ ] 深色模式下样式正常
- [ ] 响应式布局正常

### 6.2 Phase 2 测试清单

#### 单元测试
```typescript
describe('PageShell', () => {
  it('renders title', () => { ... });
  it('renders search when provided', () => { ... });
  it('shows loading state', () => { ... });
  it('shows empty state', () => { ... });
  it('renders filters', () => { ... });
  it('renders actions', () => { ... });
});
```

#### 迁移测试
- [ ] 每个迁移的页面布局一致
- [ ] 搜索功能正常
- [ ] 筛选器正常
- [ ] 加载状态正常
- [ ] 空状态正常

### 6.3 Phase 3 测试清单

#### 路由测试
- [ ] 直接访问 `/runs` 显示正确页面
- [ ] 浏览器前进/后退正常
- [ ] 刷新页面保持当前路由
- [ ] 嵌套路由 Tab 切换正常（如 `/integrations/mcp`）
- [ ] URL 参数正常（如 `/runs?search=test`）
- [ ] 404 页面正常
- [ ] 面包屑导航显示正确

#### 导航测试
- [ ] 侧边栏 Link 导航正常
- [ ] active 状态正确
- [ ] 嵌套路由的 Tab 导航正常
- [ ] 编程式导航正常（`navigate()`）

### 6.4 回归测试

**核心功能检查**：
- [ ] 工作台功能正常
- [ ] 运行事件查看正常
- [ ] MCP 连接器配置正常
- [ ] 金融模块可访问
- [ ] 设置保存正常
- [ ] 线程切换正常

---

## 七、成功指标

### 7.1 定量指标

| 指标 | 目标 | 测量方法 |
|------|------|----------|
| 侧边栏导航项 | 从 33 个减少到 6 个 | 代码统计 |
| 侧边栏代码行数 | 减少 50%+ | 代码统计 |
| 页面加载时间 | < 1s | Lighthouse |
| Lighthouse 分数 | > 90 | Lighthouse |
| 新页面开发时间 | 减少 75% | 开发者反馈 |

### 7.2 定性指标

**用户反馈**：
- [ ] 新用户能在 5 分钟内找到所有核心功能
- [ ] 老用户能在 1 周内适应新布局
- [ ] 90%+ 用户反馈"更易用"

**开发者反馈**：
- [ ] 新页面开发更快（使用 PageShell）
- [ ] 代码更易维护
- [ ] 结构更清晰

---

## 八、上线检查清单

### 8.1 代码质量
- [ ] 所有 ESLint 规则通过
- [ ] 所有 TypeScript 类型检查通过
- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 代码审查完成

### 8.2 功能完整性
- [ ] 所有页面都有对应的路由
- [ ] 所有导航链接正常工作
- [ ] 所有表单和操作正常
- [ ] 所有设置项可访问
- [ ] 无功能缺失

### 8.3 性能和体验
- [ ] 页面加载速度正常
- [ ] 无明显的卡顿
- [ ] 动画流畅
- [ ] 响应式布局正常
- [ ] 深色模式正常

### 8.4 文档和培训
- [ ] 用户迁移指南完成
- [ ] 开发者文档完成
- [ ] 功能位置对照表完成
- [ ] 视频教程完成（可选）

### 8.5 备份和回滚
- [ ] 备份分支已推送到远程
- [ ] 回滚方案已测试
- [ ] 功能开关可用
- [ ] 监控告警配置完成

---

**任务**：
1. 创建 Overlay 相关组件（OverlayView、OverlaySplitLayout）
2. 修改 AppSidebar.tsx，添加设置按钮，简化侧边栏结构
3. 更新 views.ts，定义核心导航和设置页面列表
4. 编写新的 CSS 样式文件

**验证点**：
- 侧边栏显示 5 个核心导航入口
- 点击设置按钮可打开全屏设置面板
- 会话列表功能不受影响

### 5.2 阶段二：设置面板整合（2-3 天）

**任务**：
1. 重构 SettingsWorkspace.tsx 为 Overlay 模式
2. 创建 SettingsNavSection 和 SettingsNavItem 组件
3. 整合现有设置页面：
   - 基础设置：模型、项目、外观、用户画像
   - 金融配置：数据源、市场温度、策略工厂等
   - 运维配置：Gateway、MCP、API Keys
4. 添加配置导入/导出/重置功能

**验证点**：
- 所有设置项可在设置面板中访问
- 设置面板支持搜索
- 配置导入/导出功能正常

### 5.3 阶段三：视图精简与路由优化（1-2 天）

**任务**：
1. 精简 App.tsx 中的视图渲染逻辑
2. 移除不再需要的 legacy 视图包装器
3. 更新 VIEW_REGISTRY 和 VIEW_GROUPS
4. 调整 FinanceLabPage 作为金融功能统一入口

**验证点**：
- 所有核心功能可正常访问
- 无冗余的视图渲染代码
- 金融工作台可访问所有金融子功能

### 5.4 阶段四：UI 细节打磨（1 天）

**任务**：
1. 调整样式细节，确保视觉一致性
2. 添加快捷键支持（Ctrl+K 搜索、Ctrl+, 设置等）
3. 添加过渡动画
4. 响应式适配

**验证点**：
- UI 符合设计规范
- 快捷键正常工作
- 动画流畅

---

## 九、总结

### 9.1 改造效果预期

**简化程度（定量）**：
- ✅ 侧边栏导航：33个 → 6个（**↓ 82%**）
- ✅ 总视图数：40+ 个 → 6个核心（**↓ 85%**）
- ✅ 页面布局方式：40种 → 1种（**统一**）
- ✅ 侧边栏代码：233行 → ~120行（**↓ 50%**）
- ✅ 新页面开发时间：2-4小时 → 30分钟（**↓ 75%**）

**用户体验提升（定性）**：
- ✅ 降低学习成本：新用户 5 分钟即可找到核心功能
- ✅ 提高效率：常用功能一键直达，无需多级导航
- ✅ 视觉清爽：界面简洁，信息层次清晰
- ✅ 更好的可发现性：URL 可分享，刷新保持状态

**开发效率提升**：
- ✅ 统一框架：所有页面使用 PageShell，开发更快
- ✅ 代码质量：结构清晰，易于维护
- ✅ 可扩展性：添加新功能更容易

### 9.2 开发工作量估算

| Phase | 任务 | 时间 |
|-------|------|------|
| Phase 1 | 侧边栏精简 | 2 周 |
| Phase 2 | PageShell 组件 | 2 周 |
| Phase 3 | 路由系统 | 2 周 |
| Phase 4 | 迁移和优化 | 2 周 |
| **总计** | | **8 周（1名全职开发者）** |

**关键里程碑**：
- Week 2: Phase 1 完成（侧边栏精简）
- Week 4: Phase 2 完成（PageShell 组件）
- Week 6: Phase 3 完成（路由系统）
- Week 8: 最终交付

### 9.3 关键成功因素

1. **保持核心功能完整** ✅
   - 精简入口但不删除功能
   - 通过合并和嵌套路由保留所有功能

2. **平滑迁移** ✅
   - 提供过渡期（1-2周）
   - 提供功能位置对照表
   - 支持回退到旧版

3. **参考最佳实践** ✅
   - 借鉴 Hermes Agent 的成熟方案
   - 使用业界标准（React Router 6）
   - 统一的设计模式（PageShell）

4. **充分测试** ✅
   - 每个 Phase 独立测试
   - 单元测试 + 集成测试 + 回归测试
   - 性能测试

5. **用户反馈** ✅
   - 早期收集用户意见
   - 快速迭代优化
   - 保持沟通渠道畅通

### 9.4 下一步行动

#### 立即开始
```bash
# 1. 创建备份分支
git checkout -b backup/sidebar-before-refactor
git add . && git commit -m "backup: 侧边栏改造前完整快照"
git push origin backup/sidebar-before-refactor

# 2. 创建工作分支
git checkout -b refactor/phase1-sidebar-simplification

# 3. 开始 Phase 1
# 参照 docs/refactor/phase1-sidebar-simplification.md
```

#### 每周同步
- **周一**：计划本周任务
- **周三**：中期检查
- **周五**：Review 本周成果

#### 保持沟通
- 遇到问题及时讨论
- 不确定时先小范围验证
- 定期更新进度

---

## 十、附录

### 10.1 功能位置迁移对照表

| 旧位置 | 新位置 | 访问方式 |
|--------|--------|----------|
| overview（概览） | ❌ 已移除 | 功能已在 workbench |
| agent（代理） | ❌ 已移除 | 已被 workbench 替代 |
| capabilities（能力） | ❌ 已移除 | 已被 readiness-health 替代 |
| mcp-connectors | 集成中心 → MCP连接器 | `/integrations/mcp` |
| plugins-skills | 集成中心 → 插件与技能 | `/integrations/plugins` |
| tools-intents-approvals | 集成中心 → 工具审批 | `/integrations/tools` |
| gateway | 集成中心 → 网关配置 | `/integrations/gateway` |
| financial-manager | 金融实验室 → 财务管理 | `/finance/manager` |
| market-temperature | 金融实验室 → 市场温度 | `/finance/market-temperature` |
| quant | 金融实验室 → 量化研究 | `/finance/quant` |
| strategy-factory | 金融实验室 → 策略工厂 | `/finance/strategy` |
| factor-factory | 金融实验室 → 因子工厂 | `/finance/factor` |
| incubation | 金融实验室 → 孵化池 | `/finance/incubation` |
| data | 金融实验室 → 数据同步 | `/finance/data` |
| workflows | 金融实验室 → 工作流 | `/finance/workflows` |
| factory-events | 金融实验室 → 工厂事件 | `/finance/events` |
| models | 设置 → 模型配置 | `/settings` (Tab) |
| projects-contexts | 设置 → 项目/上下文 | `/settings` (Tab) |
| user | 设置 → 用户画像 | `/settings` (Tab) |

### 10.2 快捷键列表

| 快捷键 | 功能 | 新增/保留 |
|--------|------|----------|
| `Ctrl+N` | 新建线程 | 保留 |
| `Ctrl+K` | 搜索线程 | 保留 |
| `Ctrl+,` | 打开设置 | 新增 |
| `Ctrl+1` | 切换到工作台 | 新增 |
| `Ctrl+2` | 切换到运行与事件 | 新增 |
| `Ctrl+3` | 切换到集成中心 | 新增 |
| `Ctrl+4` | 切换到金融实验室 | 新增 |
| `Ctrl+5` | 切换到系统准备度 | 新增 |

### 10.3 参考资料

**Hermes Agent 源码**：
- `vendor/hermes-agent-upstream/apps/desktop/src/app/chat/sidebar/index.tsx` - 侧边栏实现
- `vendor/hermes-agent-upstream/apps/desktop/src/app/settings/index.tsx` - 设置面板
- `vendor/hermes-agent-upstream/apps/desktop/src/components/page-search-shell.tsx` - PageShell 参考

**本项目详细文档**：
- `docs/refactor/phase1-sidebar-simplification.md` - Phase 1 详细步骤（导航合并规则、文件修改清单、测试计划）
- `docs/refactor/phase2-page-shell-component.md` - Phase 2 详细步骤（完整组件代码、迁移指南、性能优化）
- `docs/refactor/phase3-route-system.md` - Phase 3 详细步骤（路由配置、嵌套路由、URL参数）
- `docs/refactor/implementation-roadmap.md` - 8周实施路线图（每天的具体任务、风险管理）

### 10.4 技术栈

- **框架**：React 18
- **路由**：React Router 6.20+
- **状态管理**：React Context + useState/useReducer
- **样式**：CSS Modules / Tailwind CSS
- **图标**：lucide-react
- **构建工具**：Vite
- **测试**：Vitest + React Testing Library

---

**文档版本**: v3.0-detailed  
**最后更新**: 2026-06-14  
**作者**: Claude Code  
**状态**: ✅ 详细方案完成，可以开始实施

**Let's build a better AIASK! 🚀**


对于需要保留的高级功能（如诊断、覆盖矩阵等），可以：

**方案一**：通过 URL 直接访问
```
http://localhost:5173/#/diagnostics
http://localhost:5173/#/coverage
```

**方案二**：在设置中添加"高级诊断"入口
- 设置 → 高级设置 → 旧诊断页面
- 显示警告提示："此页面为旧版诊断入口，仅供高级用户使用"

### 6.2 快捷键兼容

保留常用快捷键：
- `Ctrl+N`: 新建对话
- `Ctrl+K`: 搜索会话
- `Ctrl+,`: 打开设置
- `Ctrl+1-5`: 切换核心视图

### 6.3 扩展插槽保留

保留现有的扩展插槽系统：
- `sidebar-top`
- `sidebar-secondary`
- `pre-main`
- `post-main`
- `overlay`

确保第三方插件可继续工作。

---

## 七、风险评估与缓解

### 7.1 主要风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 用户找不到原有功能 | 高 | 中 | 添加迁移指南，保留旧入口作为过渡 |
| 设置面板性能问题 | 中 | 低 | 使用懒加载，按需渲染设置页面 |
| 移动端/小屏适配 | 中 | 中 | Overlay 模式自适应调整为全屏 |
| 第三方插件兼容性 | 中 | 低 | 保留扩展插槽，文档说明变更 |

### 7.2 回退策略

保留一个 `legacy-mode` 配置项：
```json
{
  "ui": {
    "simplifiedMode": true,  // 新版简化模式
    "legacyMode": false      // 旧版完整模式
  }
}
```

用户可在设置中切换回旧版 UI。

---

## 八、后续优化方向

### 8.1 智能搜索增强

参考 Hermes 的搜索功能，增强全局搜索：
- 搜索会话内容
- 搜索工具调用记录
- 搜索设置项
- 搜索帮助文档

### 8.2 工作区概念强化

参考 Hermes 的工作区分组：
- 按项目路径自动分组会话
- 支持在特定工作区启动新会话
- 工作区级别的配置隔离

### 8.3 快捷操作面板

添加命令面板（Cmd+K / Ctrl+K）：
- 快速执行常用操作
- 搜索并跳转到任意功能
- 查看快捷键列表

---

## 九、总结

### 9.1 改造效果预期

**简化程度**：
- 侧边栏导航：从 40+ 个入口减少到 5 个核心入口
- 设置统一：所有配置集中在一个设置面板
- 视图精简：主要视图从 30+ 个减少到 8 个核心视图

**用户体验提升**：
- 降低学习成本：新用户可快速找到核心功能
- 提高效率：常用功能一键直达
- 视觉清爽：界面更加简洁，信息层次清晰

### 9.2 开发工作量估算

- 阶段一（基础结构）：1-2 天
- 阶段二（设置整合）：2-3 天  
- 阶段三（视图精简）：1-2 天
- 阶段四（UI 打磨）：1 天

**总计**：5-8 天（约 1-1.5 周）

### 9.3 关键成功因素

1. **保持核心功能完整**：精简入口但不删除功能
2. **平滑迁移**：提供过渡期和回退选项
3. **参考最佳实践**：借鉴 Hermes Agent 的成熟方案
4. **用户反馈**：尽早收集用户意见，迭代优化

---

## 附录

### A. 参考资料

- Hermes Agent Desktop 源码：`vendor/hermes-agent-upstream/apps/desktop/src/`
- 关键参考文件：
  - `app/chat/sidebar/index.tsx` - 侧边栏实现
  - `app/settings/index.tsx` - 设置面板实现
  - `app/overlays/` - Overlay 组件系统

### B. 配置示例

**简化模式配置**（新增）：
```json
{
  "ui": {
    "mode": "simplified",
    "sidebar": {
      "showProjectCard": false,
      "coreNavigationOnly": true
    },
    "settings": {
      "overlayMode": true,
      "categories": ["basic", "finance", "ops", "advanced", "about"]
    }
  }
}
```

### C. 迁移检查清单

- [ ] Overlay 组件创建完成
- [ ] AppSidebar 简化完成
- [ ] 设置面板 Overlay 模式实现
- [ ] 核心导航 5 个入口可用
- [ ] 所有设置项已整合到设置面板
- [ ] 视图路由逻辑简化
- [ ] 样式更新完成
- [ ] 快捷键配置
- [ ] 兼容性测试通过
- [ ] 用户迁移指南编写

---

**文档版本**: v2.0-simplified  
**最后更新**: 2026-06-14  
**作者**: Claude Code  
**状态**: ✅ 方案完成，待评审
