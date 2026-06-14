# AIASK 前端改造实施路线图

## 总览

基于对 Hermes Agent 的深入对比分析，本改造方案将 AIASK 从 **33个导航项、40个视图** 精简为 **6个核心导航**，并建立统一的页面框架和真正的路由系统。

---

## 改造时间线

```
Week 1-2: Phase 1 - 侧边栏精简
Week 3-4: Phase 2 - PageShell 组件
Week 5-6: Phase 3 - 路由系统
Week 7-8: Phase 4 - 迁移和优化
```

---

## Phase 1: 侧边栏精简（Week 1-2）

### 目标
从 33 个导航项减少到 6 个核心导航

### 时间分配
- Day 1-2: 备份和分析
- Day 3-5: 修改 views.ts 和 AppSidebar
- Day 6-8: 创建集成中心和金融实验室入口
- Day 9-10: 测试和调整

### 详细任务

#### Day 1-2: 准备工作
```bash
# 任务1: 创建备份
git checkout -b backup/sidebar-before-refactor
git add .
git commit -m "backup: 侧边栏改造前完整快照"
git push origin backup/sidebar-before-refactor

# 任务2: 创建工作分支
git checkout -b refactor/phase1-sidebar-simplification

# 任务3: 分析依赖
grep -r "mainView.*==.*\"" desktop/src --include="*.tsx" > /tmp/mainview-usage.txt
# 评估哪些组件依赖 MainView 状态

# 任务4: 创建改造文档目录
mkdir -p docs/refactor
```

#### Day 3-5: 核心代码修改

**任务1: 重写 views.ts**
```typescript
// desktop/src/views.ts

// 删除 advanced-finance, advanced-ops, legacy 分组
// 保留核心视图
export const CORE_VIEWS = [
  'workbench',
  'runs-events',
  'integrations',      // 新建
  'finance-lab',       // 改造为主入口
  'readiness-health',
] as const;

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

**任务2: 简化 AppSidebar.tsx**
```typescript
// 删除：
// - brand-row (第 120-129 行)
// - sidebar-project-card (第 136-143 行)
// - extension-slot-row (第 145-152 行)
// - SidebarNavGroup 分组逻辑 (第 45-84 行)

// 新的简化结构：扁平导航列表
<nav className="sidebar-nav">
  {CORE_NAV.map(item => (
    <IconButton key={item.id} active={mainView === item.id}>
      <item.icon size={16} />
      {item.label}
    </IconButton>
  ))}
</nav>
```

**任务3: 更新 App.tsx**
```typescript
// 移除已删除视图的 lazy import
// 保留 6 个核心视图的导入
// 更新主视图渲染逻辑
```

#### Day 6-8: 新建页面

**任务1: 创建集成中心**
```bash
mkdir -p desktop/src/features/integrations
touch desktop/src/features/integrations/IntegrationsWorkspace.tsx
```

```typescript
// IntegrationsWorkspace.tsx
export function IntegrationsWorkspace() {
  const [activeTab, setActiveTab] = useState<'mcp' | 'plugins' | 'tools' | 'gateway'>('mcp');
  
  return (
    <section className="integrations-workspace">
      <header>
        <h1>集成中心</h1>
        <div className="tabs">
          <button onClick={() => setActiveTab('mcp')}>MCP 连接器</button>
          <button onClick={() => setActiveTab('plugins')}>插件与技能</button>
          <button onClick={() => setActiveTab('tools')}>工具审批</button>
          <button onClick={() => setActiveTab('gateway')}>网关配置</button>
        </div>
      </header>
      <main>
        {activeTab === 'mcp' && <McpConnectorsPanel />}
        {activeTab === 'plugins' && <PluginsSkillsPanel />}
        {activeTab === 'tools' && <ToolsApprovalsPanel />}
        {activeTab === 'gateway' && <GatewayPanel />}
      </main>
    </section>
  );
}
```

**任务2: 创建金融实验室主页**
```bash
touch desktop/src/features/finance-lab/FinanceLabHome.tsx
```

```typescript
// FinanceLabHome.tsx
export function FinanceLabHome() {
  return (
    <section className="finance-lab-home">
      <h1>金融实验室</h1>
      <div className="modules-grid">
        <ModuleCard title="财务管理" icon={<DollarSign />} route="/finance/manager" />
        <ModuleCard title="市场温度" icon={<TrendingUp />} route="/finance/market" />
        <ModuleCard title="量化研究" icon={<LineChart />} route="/finance/quant" />
        {/* 其他 6 个模块 */}
      </div>
    </section>
  );
}
```

#### Day 9-10: 测试

**测试清单:**
- [ ] 侧边栏只显示 6 个导航项
- [ ] 点击每个导航能正常切换
- [ ] 集成中心的 4 个 Tab 正常切换
- [ ] 金融实验室显示 9 个模块卡片
- [ ] 旧的导航项无法访问
- [ ] 样式正常，无滚动条
- [ ] 深色模式正常

**如果发现问题:**
```bash
# 回滚到备份分支
git checkout backup/sidebar-before-refactor
# 分析问题
# 修复后重新尝试
```

### 交付物
- ✅ 简化后的 `desktop/src/views.ts`
- ✅ 简化后的 `desktop/src/components/AppSidebar.tsx`
- ✅ 新的 `IntegrationsWorkspace.tsx`
- ✅ 新的 `FinanceLabHome.tsx`
- ✅ 测试报告

---

## Phase 2: PageShell 统一框架（Week 3-4）

### 目标
创建统一的页面框架组件，为所有功能页提供一致的布局

### 时间分配
- Day 1-2: 创建 PageShell 组件
- Day 3-5: 迁移高优先级页面（3个）
- Day 6-8: 迁移中优先级页面（5个）
- Day 9-10: 编写测试和文档

### 详细任务

#### Day 1-2: 创建 PageShell

```bash
# 创建组件文件
touch desktop/src/components/PageShell.tsx
touch desktop/src/components/PageShell.css
touch desktop/src/components/PageShell.test.tsx
```

**实现完整的 PageShell 组件**（参考 phase2 文档）

#### Day 3-5: 迁移高优先级页面

**迁移顺序:**
1. SettingsWorkspace（Day 3）
2. RunsEventsPage（Day 4）
3. IntegrationsWorkspace（Day 5，刚创建的）

**每个页面的迁移步骤:**
```typescript
// 1. 导入 PageShell
import { PageShell } from '@/components/PageShell';

// 2. 删除自定义 header
// 删除： <header><h1>标题</h1>...</header>

// 3. 使用 PageShell 包裹
<PageShell
  title="页面标题"
  searchValue={search}
  onSearchChange={setSearch}
>
  {/* 原有内容 */}
</PageShell>

// 4. 测试功能
// 5. 提交代码
```

#### Day 6-8: 迁移中优先级页面

**迁移页面:**
- ModelsWorkspace
- ReadinessHealthPage
- FinanceLabHome
- GatewayPage
- McpConnectorsPage

#### Day 9-10: 测试和文档

**单元测试:**
```typescript
// PageShell.test.tsx
describe('PageShell', () => {
  it('renders title', () => { ... });
  it('renders search when provided', () => { ... });
  it('shows loading state', () => { ... });
  it('shows empty state', () => { ... });
});
```

**文档:**
- 组件 API 文档
- 使用指南
- 迁移检查清单

### 交付物
- ✅ `PageShell.tsx` 组件
- ✅ `PageShell.css` 样式
- ✅ `PageShell.test.tsx` 测试
- ✅ 8 个页面已迁移
- ✅ 组件文档

---

## Phase 3: 路由系统（Week 5-6）

### 目标
添加真正的 URL 路由，支持浏览器前进/后退、刷新保持状态

### 时间分配
- Day 1-2: 安装依赖和创建路由配置
- Day 3-5: 改造 App.tsx 和 AppSidebar
- Day 6-8: 实现嵌套路由和导航
- Day 9-10: 测试和优化

### 详细任务

#### Day 1-2: 准备工作

```bash
# 安装 React Router
npm install react-router-dom@^6.20.0
npm install --save-dev @types/react-router-dom

# 创建路由配置
touch desktop/src/routes.ts
```

**创建路由表:**
```typescript
// routes.ts
export const ROUTES = {
  HOME: '/',
  RUNS: '/runs',
  INTEGRATIONS: '/integrations',
  FINANCE_LAB: '/finance',
  READINESS: '/readiness',
  SETTINGS: '/settings',
  // 子路由
  INTEGRATIONS_MCP: '/integrations/mcp',
  // ...
} as const;
```

#### Day 3-5: 改造主应用

**任务1: 改造 App.tsx**
```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom';

export function App() {
  return (
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
  );
}
```

**任务2: 改造 AppSidebar**
```typescript
import { Link, useLocation } from 'react-router-dom';

// 从 onClick 改为 Link
<Link to="/runs" className={location.pathname === '/runs' ? 'active' : ''}>
  运行与事件
</Link>
```

#### Day 6-8: 实现嵌套路由

**集成中心嵌套路由:**
```typescript
// IntegrationsWorkspace.tsx
import { NavLink, Outlet } from 'react-router-dom';

export function IntegrationsWorkspace() {
  return (
    <PageShell
      title="集成中心"
      filters={
        <div className="tabs">
          <NavLink to="/integrations/mcp">MCP 连接器</NavLink>
          <NavLink to="/integrations/plugins">插件与技能</NavLink>
        </div>
      }
    >
      <Outlet />
    </PageShell>
  );
}
```

**金融实验室嵌套路由:**
```typescript
// App.tsx
<Route path="/finance" element={<FinanceLabLayout />}>
  <Route index element={<FinanceLabHome />} />
  <Route path="manager" element={<FinancialManager />} />
  <Route path="market" element={<MarketTemperature />} />
  {/* 其他子路由 */}
</Route>
```

#### Day 9-10: 测试

**路由测试:**
- [ ] 直接访问 `/runs` 显示正确页面
- [ ] 浏览器前进/后退正常
- [ ] 刷新页面保持当前路由
- [ ] 嵌套路由 Tab 切换正常
- [ ] URL 参数正常（如 `/runs?search=test`）
- [ ] 404 页面正常

### 交付物
- ✅ `routes.ts` 路由配置
- ✅ 改造后的 `App.tsx`
- ✅ 改造后的 `AppSidebar.tsx`
- ✅ 嵌套路由实现
- ✅ 路由测试

---

## Phase 4: 迁移和优化（Week 7-8）

### 目标
完成剩余页面迁移，优化性能，编写文档

### 时间分配
- Day 1-4: 迁移剩余页面到 PageShell
- Day 5-6: 性能优化
- Day 7-8: 文档和培训

### 详细任务

#### Day 1-4: 迁移剩余页面

**剩余页面清单:**
- QuantResearchWorkspace
- StrategyFactoryPanel
- FactorFactoryPanel
- IncubationFactoryPanel
- DataSyncWorkspace
- WorkflowsWorkspace
- FactoryEventTriggerPanel
- MarketTemperatureWorkspace
- FinancialManagerWorkspace

**每天迁移 2-3 个页面**

#### Day 5-6: 性能优化

**优化项:**
1. **代码分割**
   ```typescript
   const StrategyFactory = lazy(() => import('./features/factory/StrategyFactoryPanel'));
   ```

2. **路由预加载**
   ```typescript
   // 鼠标悬停时预加载
   <Link to="/finance" onMouseEnter={() => import('./features/finance-lab/FinanceLabHome')}>
   ```

3. **虚拟滚动**（大列表）
   ```typescript
   import { useVirtualizer } from '@tanstack/react-virtual';
   ```

4. **搜索防抖**
   ```typescript
   const debouncedSearch = useMemo(() => debounce(setSearch, 300), []);
   ```

#### Day 7-8: 文档

**需要编写的文档:**
1. **用户文档**
   - 新导航结构说明
   - 功能位置迁移对照表
   - 快捷键列表

2. **开发者文档**
   - PageShell 使用指南
   - 路由添加指南
   - 页面开发规范

3. **迁移指南**
   - 从旧版本升级说明
   - 破坏性变更列表
   - 迁移检查清单

### 交付物
- ✅ 所有页面已迁移到 PageShell
- ✅ 性能优化完成
- ✅ 完整文档
- ✅ 培训材料

---

## 代码审查检查清单

每个 Pull Request 需要检查：

### 功能性
- [ ] 所有导航链接正常工作
- [ ] 页面标题正确
- [ ] 搜索功能正常
- [ ] Tab 切换正常
- [ ] URL 反映当前页面
- [ ] 浏览器前进/后退正常
- [ ] 刷新页面保持状态

### 代码质量
- [ ] 使用了 PageShell 组件
- [ ] 使用了 Link/NavLink 而非 onClick
- [ ] 移除了无用的状态管理
- [ ] 代码符合 ESLint 规则
- [ ] 没有 console.log
- [ ] 类型定义完整

### UI/UX
- [ ] 样式与其他页面一致
- [ ] 响应式布局正常
- [ ] 深色模式正常
- [ ] 加载状态友好
- [ ] 空状态有提示
- [ ] 错误提示清晰

### 测试
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 手动测试通过
- [ ] 无回归问题

### 文档
- [ ] 更新了相关文档
- [ ] 添加了 JSDoc 注释
- [ ] 更新了 CHANGELOG

---

## 风险管理

### 高风险项

#### 风险1: 破坏现有功能
**影响:** 用户无法访问某些功能
**缓解措施:**
- 每个 Phase 完成后充分测试
- 保持备份分支
- 准备快速回滚方案

**回滚方案:**
```bash
# 回滚到备份分支
git checkout backup/sidebar-before-refactor
git push origin master -f  # 慎用！

# 或只回滚特定文件
git checkout backup/sidebar-before-refactor -- desktop/src/views.ts
```

#### 风险2: 用户习惯改变
**影响:** 用户找不到常用功能
**缓解措施:**
- 提供功能位置迁移对照表
- 在旧入口位置显示跳转提示
- 保留过渡期（1-2周）

**过渡方案:**
```typescript
// 在旧页面显示迁移提示
export function LegacyToolsPage() {
  return (
    <div className="migration-notice">
      <h2>此功能已迁移</h2>
      <p>工具审批功能现在在"集成中心"的"工具审批" Tab 中</p>
      <Link to="/integrations/tools">前往新位置</Link>
    </div>
  );
}
```

#### 风险3: 性能退化
**影响:** 页面加载变慢
**缓解措施:**
- 使用代码分割
- 监控性能指标
- 优化大列表渲染

**性能监控:**
```typescript
// 使用 React DevTools Profiler
<Profiler id="PageShell" onRender={logProfile}>
  <PageShell>...</PageShell>
</Profiler>
```

### 中风险项

#### 风险4: 路由冲突
**影响:** 某些 URL 无法访问
**缓解措施:**
- 统一路由配置在 routes.ts
- 避免动态路由与静态路由冲突
- 充分测试所有路由

#### 风险5: 样式不一致
**影响:** UI 体验不统一
**缓解措施:**
- PageShell 提供统一样式
- 使用设计 token
- 视觉回归测试

---

## 成功指标

### 定量指标
- [ ] 导航项从 33 个减少到 6 个（✅ 减少 82%）
- [ ] 侧边栏代码行数减少 50%+
- [ ] 页面加载时间 < 1s
- [ ] Lighthouse 分数 > 90

### 定性指标
- [ ] 用户反馈：更易找到功能
- [ ] 开发者反馈：更易维护
- [ ] 代码审查：结构更清晰
- [ ] 新功能开发：速度提升 30%+

---

## 总结

本改造方案通过 **3 个核心 Phase** 将 AIASK 前端从复杂混乱的状态改造为简洁统一的架构：

1. **Phase 1（侧边栏精简）**: 33个导航 → 6个核心导航
2. **Phase 2（PageShell组件）**: 40种页面布局 → 1个统一框架
3. **Phase 3（路由系统）**: 状态切换 → 真正的URL路由

**预期收益:**
- ✅ 用户体验：更快找到功能，学习成本降低
- ✅ 开发效率：新页面开发时间减少 50%+
- ✅ 代码质量：结构清晰，易于维护
- ✅ 可扩展性：添加新功能更容易

**总工时估算:** 8 周（1 名全职开发者）
**关键里程碑:** Week 2, Week 4, Week 6
**最终交付:** Week 8

---

## 下一步行动

1. **立即开始 Phase 1**
   ```bash
   git checkout -b refactor/phase1-sidebar-simplification
   ```

2. **每周同步进度**
   - 周一：计划本周任务
   - 周五：Review 本周成果

3. **保持沟通**
   - 遇到问题及时讨论
   - 不确定时先小范围验证

**Let's build a better AIASK! 🚀**
