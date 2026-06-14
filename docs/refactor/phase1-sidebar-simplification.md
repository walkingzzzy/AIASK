# Phase 1: 侧边栏精简改造方案

## 一、改造目标

将 AIASK 的侧边栏从 **33个导航项** 精简到 **6-8个核心导航**，参考 Hermes Agent 的简洁设计。

### 改造前（当前状态）
```
侧边栏结构：
├── 品牌栏 (AIASK Agent 工作台)
├── 新建线程按钮
├── 项目卡片 (连接状态/主机信息)
├── 扩展插槽
├── 任务线程区
└── 导航区 (4个分组，33个导航项)
    ├── 主工作区 (8项)
    ├── 高级金融 (9项)
    ├── 高级运维 (6项)
    └── 旧入口/诊断 (10项)
```

### 改造后（目标状态）
```
侧边栏结构：
├── 新建线程按钮
├── 6个核心导航
│   ├── 工作台
│   ├── 运行与事件
│   ├── 集成中心
│   ├── 金融实验室
│   ├── 系统准备度
│   └── (设置移到顶栏)
├── 搜索框
└── 线程列表
```

---

## 二、导航项合并规则

### 2.1 保留为核心导航

| 旧导航 | 新导航 | 理由 |
|--------|--------|------|
| workbench | **工作台** | 主工作面，保持不变 |
| runs-events | **运行与事件** | 核心功能，查看历史和审批 |
| integrations | **集成中心** | 已合并 MCP/工具/技能的主入口 |
| finance-lab | **金融实验室** | 金融功能的统一入口 |
| readiness-health | **系统准备度** | 系统状态监控 |

### 2.2 合并到"集成中心"

**原理：** 所有与外部工具、MCP、插件相关的功能合并到一个页面，通过 Tab 切换。

```typescript
// 合并内容
集成中心 = {
  Tab1: "MCP 连接器" (mcp-connectors),
  Tab2: "插件与技能" (plugins-skills),
  Tab3: "工具审批" (tools-intents-approvals),
  Tab4: "网关配置" (gateway)
}
```

**移除的导航项：**
- `mcp-connectors` → 合并为 Tab
- `plugins-skills` → 合并为 Tab
- `tools-intents-approvals` → 合并为 Tab
- `gateway` → 合并为 Tab
- `mcp` (旧入口) → 删除
- `tools` (旧入口) → 删除

### 2.3 合并到"金融实验室"

**原理：** 所有金融相关功能通过二级导航（侧边栏 Tab 或子菜单）访问。

```typescript
// 合并内容
金融实验室 = {
  主页: "概览与快速入口",
  子功能: [
    "财务管理" (financial-manager),
    "市场温度" (market-temperature),
    "量化研究" (quant),
    "策略工厂" (strategy-factory),
    "因子工厂" (factor-factory),
    "孵化池" (incubation),
    "数据同步" (data),
    "工作流" (workflows),
    "工厂事件" (factory-events)
  ]
}
```

**移除的导航项：**
- 整个"高级金融"分组的 9 项全部移除

### 2.4 移到顶栏或其他入口

| 旧导航 | 新位置 | 理由 |
|--------|--------|------|
| settings | 顶栏齿轮图标 | 参考 Hermes，设置不在侧边栏 |
| models | 集成中心 → 模型管理 Tab | 模型配置属于集成 |
| automation | 设置 → 自动化页 | 低频使用 |
| projects-contexts | 顶栏下拉菜单 | 项目切换不需要专门页面 |

### 2.5 完全移除

**旧入口/诊断分组（10项）全部移除：**
- `overview` → 删除（功能已在 workbench）
- `agent` → 删除（已被 workbench 替代）
- `capabilities` → 删除（已被 readiness-health 替代）
- `coverage` → 删除（已被 readiness-health 包含）
- `diagnostics` → 删除（已被 readiness-health 替代）
- `event-console` → 删除（已被 runs-events 替代）
- `skills` → 删除（已合并到 plugins-skills）
- `user` → 删除（已移到 settings）
- `extensions-pilot` → 删除（通过设置访问）

---

## 三、文件修改清单

### 3.1 核心文件修改

#### 文件1：`desktop/src/views.ts`

**修改内容：** 重写 `VIEW_GROUPS` 和 `VIEW_REGISTRY`

```typescript
// 新的视图注册表（只保留核心视图）
export const CORE_VIEWS = [
  'workbench',
  'runs-events', 
  'integrations',
  'finance-lab',
  'readiness-health',
  'settings'
] as const;

export type CoreView = typeof CORE_VIEWS[number];

// 简化后的视图分组
export const VIEW_GROUPS: ViewGroup[] = [
  {
    id: "core",
    label: "核心功能",
    items: [
      { id: 'workbench', label: '工作台', icon: LayoutDashboard },
      { id: 'runs-events', label: '运行与事件', icon: Activity },
      { id: 'integrations', label: '集成中心', icon: Puzzle },
      { id: 'finance-lab', label: '金融实验室', icon: TrendingUp },
      { id: 'readiness-health', label: '系统准备度', icon: Shield }
    ]
  }
];
```

#### 文件2：`desktop/src/components/AppSidebar.tsx`

**修改内容：** 大幅简化侧边栏结构

```typescript
// 移除的元素
// ❌ 删除 brand-row
// ❌ 删除 sidebar-project-card
// ❌ 删除 extension-slot-row
// ❌ 删除分组折叠逻辑

// 新的简化结构
export function AppSidebar({ ... }) {
  return (
    <aside className="sidebar app-sidebar">
      {/* 1. 新建按钮 */}
      <button className="new-task-button" onClick={onNewTask}>
        <Plus size={16} />
        新建线程
      </button>

      {/* 2. 核心导航（扁平化，无分组） */}
      <nav className="sidebar-nav" aria-label="Main navigation">
        {CORE_NAV_ITEMS.map((item) => (
          <IconButton
            key={item.id}
            active={mainView === item.id}
            label={item.label}
            onClick={() => onSelectView(item.id)}
          >
            <item.icon size={16} />
          </IconButton>
        ))}
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

      {/* 5. 底部状态（可选，简化版） */}
      <div className="sidebar-footer">
        <StatusBadge status={status} />
        <span>{tools.length} 工具</span>
      </div>
    </aside>
  );
}
```

---

## 四、实施步骤（详细）

### Step 1: 备份当前代码

```bash
# 创建备份分支
git checkout -b backup/sidebar-before-refactor
git add .
git commit -m "backup: 侧边栏改造前的快照"

# 创建工作分支
git checkout -b refactor/phase1-sidebar-simplification
```

### Step 2: 创建新的视图定义

```bash
# 1. 备份旧文件
cp desktop/src/views.ts desktop/src/views.ts.backup

# 2. 创建新的核心视图定义
# 编辑 desktop/src/views.ts
```

**编辑内容：**
- 删除 `VIEW_GROUPS` 中的 `advanced-finance`, `advanced-ops`, `legacy` 分组
- 保留 `primary` 分组，但只保留 6 个核心导航
- 更新 `MainView` 类型为 `CoreView`

### Step 3: 简化 AppSidebar 组件

```bash
# 编辑 desktop/src/components/AppSidebar.tsx
```

**修改清单：**
1. 删除第 120-129 行：`brand-row` 品牌栏
2. 删除第 136-143 行：`sidebar-project-card` 项目卡片
3. 删除第 145-152 行：`extension-slot-row` 扩展插槽
4. 删除第 192-206 行：`SidebarNavGroup` 分组组件
5. 简化导航为扁平列表（第 192-220 行替换为新代码）

### Step 4: 创建集成中心页面

```bash
# 创建新的集成中心页面
touch desktop/src/features/integrations/IntegrationsWorkspace.tsx
```

**实现内容：** 使用 Tab 组件合并多个功能

```typescript
export function IntegrationsWorkspace() {
  const [activeTab, setActiveTab] = useState<'mcp' | 'plugins' | 'tools' | 'gateway'>('mcp');

  return (
    <PageShell
      title="集成中心"
      filters={
        <TabGroup value={activeTab} onChange={setActiveTab}>
          <Tab value="mcp">MCP 连接器</Tab>
          <Tab value="plugins">插件与技能</Tab>
          <Tab value="tools">工具审批</Tab>
          <Tab value="gateway">网关配置</Tab>
        </TabGroup>
      }
    >
      {activeTab === 'mcp' && <McpConnectorsPanel />}
      {activeTab === 'plugins' && <PluginsSkillsPanel />}
      {activeTab === 'tools' && <ToolsApprovalsPanel />}
      {activeTab === 'gateway' && <GatewayPanel />}
    </PageShell>
  );
}
```

### Step 5: 创建金融实验室入口页

```bash
# 创建金融实验室主页
touch desktop/src/features/finance-lab/FinanceLabHome.tsx
```

**实现内容：** Dashboard 式的快速入口

```typescript
export function FinanceLabHome() {
  return (
    <PageShell title="金融实验室">
      <div className="finance-modules-grid">
        <ModuleCard
          title="财务管理"
          description="投资组合、持仓、绩效"
          icon={<DollarSign />}
          route="/finance-lab/financial-manager"
        />
        <ModuleCard
          title="市场温度"
          description="市场情绪、行业热度"
          icon={<TrendingUp />}
          route="/finance-lab/market-temperature"
        />
        {/* ...其他 7 个模块 */}
      </div>
    </PageShell>
  );
}
```

### Step 6: 更新 App.tsx 主路由

```bash
# 编辑 desktop/src/App.tsx
```

**修改内容：**
- 移除所有已删除视图的 lazy import
- 更新 `mainView` 的渲染逻辑
- 添加新的 `IntegrationsWorkspace` 和 `FinanceLabHome`

### Step 7: 更新样式

```bash
# 编辑 desktop/src/App.css
```

**修改内容：**
- 移除 `.brand-row` 样式
- 移除 `.sidebar-project-card` 样式
- 移除 `.sidebar-nav-group.advanced` 样式
- 添加扁平化导航的新样式

---

## 五、测试计划

### 5.1 功能测试

| 测试项 | 预期结果 | 状态 |
|--------|----------|------|
| 侧边栏只显示 6 个导航 | ✅ 显示工作台/运行/集成/金融/准备度/设置 | [ ] |
| 点击"集成中心"显示 Tab | ✅ 显示 MCP/插件/工具/网关 4个Tab | [ ] |
| 点击"金融实验室"显示模块网格 | ✅ 显示 9 个金融模块卡片 | [ ] |
| 旧导航项已移除 | ✅ 无法访问 overview/agent/capabilities 等 | [ ] |
| 新建线程按钮正常 | ✅ 点击创建新线程 | [ ] |
| 线程列表显示正常 | ✅ 显示当前线程，点击可切换 | [ ] |

### 5.2 UI 测试

- [ ] 侧边栏高度适中，无滚动条（或最小滚动）
- [ ] 导航图标清晰，间距合理
- [ ] 深色模式下样式正常
- [ ] 响应式布局正常（窗口缩放）

### 5.3 回归测试

- [ ] 工作台功能正常
- [ ] 运行事件查看正常
- [ ] MCP 连接器配置正常
- [ ] 金融模块可访问

---

## 六、回滚方案

如果改造出现问题，可以快速回滚：

```bash
# 方案1：回滚到备份分支
git checkout backup/sidebar-before-refactor

# 方案2：仅回滚特定文件
git checkout backup/sidebar-before-refactor -- desktop/src/views.ts
git checkout backup/sidebar-before-refactor -- desktop/src/components/AppSidebar.tsx
```

---

## 七、上线检查清单

上线前确认：
- [ ] 所有测试通过
- [ ] 代码已经过 Code Review
- [ ] 更新了用户文档
- [ ] 创建了迁移指南（如果有破坏性变更）
- [ ] 备份分支已推送到远程
