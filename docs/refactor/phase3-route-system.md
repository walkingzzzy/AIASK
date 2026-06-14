# Phase 3: 添加真正的路由系统

## 一、改造目标

将 AIASK 从基于状态的视图切换改造为真正的 **URL 路由系统**，参考 Hermes Agent 的路由实现。

### 问题诊断

**当前状态：** 基于 `MainView` 状态切换
```typescript
// 没有真正的路由，URL 始终不变
const [mainView, setMainView] = useState<MainView>("workbench");

// 切换视图
<button onClick={() => setMainView("settings")}>设置</button>

// URL 不反映当前页面
// http://localhost:3000/  <- 无论在哪个页面都一样
```

**目标状态：** 基于 React Router 的真实路由
```typescript
// URL 反映当前页面
http://localhost:3000/                  -> 工作台
http://localhost:3000/runs              -> 运行与事件
http://localhost:3000/integrations      -> 集成中心
http://localhost:3000/finance-lab       -> 金融实验室
http://localhost:3000/settings          -> 设置

// 支持浏览器前进/后退
// 支持直接访问 URL
// 支持刷新保持页面
```

---

## 二、路由设计

### 2.1 核心路由表

参考 Hermes 的 `routes.ts` 设计：

```typescript
// desktop/src/routes.ts

export const ROUTES = {
  // 主路由
  HOME: '/',
  WORKBENCH: '/',
  
  // 核心功能
  RUNS: '/runs',
  INTEGRATIONS: '/integrations',
  FINANCE_LAB: '/finance',
  READINESS: '/readiness',
  SETTINGS: '/settings',
  
  // 集成中心子路由
  INTEGRATIONS_MCP: '/integrations/mcp',
  INTEGRATIONS_PLUGINS: '/integrations/plugins',
  INTEGRATIONS_TOOLS: '/integrations/tools',
  INTEGRATIONS_GATEWAY: '/integrations/gateway',
  
  // 金融实验室子路由
  FINANCE_MANAGER: '/finance/manager',
  FINANCE_MARKET_TEMP: '/finance/market-temperature',
  FINANCE_QUANT: '/finance/quant',
  FINANCE_STRATEGY: '/finance/strategy',
  FINANCE_FACTOR: '/finance/factor',
  FINANCE_INCUBATION: '/finance/incubation',
  FINANCE_DATA: '/finance/data',
  FINANCE_WORKFLOWS: '/finance/workflows',
  FINANCE_EVENTS: '/finance/events',
  
  // 线程详情（动态路由）
  THREAD: '/thread/:threadId',
} as const;

export type RouteKey = keyof typeof ROUTES;
export type RoutePath = typeof ROUTES[RouteKey];

// 路由元数据
export interface RouteMetadata {
  path: string;
  title: string;
  icon?: React.ComponentType;
  requiresAuth?: boolean;
  breadcrumb?: string[];
}

export const ROUTE_METADATA: Record<string, RouteMetadata> = {
  [ROUTES.WORKBENCH]: {
    path: ROUTES.WORKBENCH,
    title: '工作台',
  },
  [ROUTES.RUNS]: {
    path: ROUTES.RUNS,
    title: '运行与事件',
  },
  [ROUTES.INTEGRATIONS]: {
    path: ROUTES.INTEGRATIONS,
    title: '集成中心',
  },
  [ROUTES.FINANCE_LAB]: {
    path: ROUTES.FINANCE_LAB,
    title: '金融实验室',
  },
  [ROUTES.READINESS]: {
    path: ROUTES.READINESS,
    title: '系统准备度',
  },
  [ROUTES.SETTINGS]: {
    path: ROUTES.SETTINGS,
    title: '设置',
  },
};

// 工具函数
export function getRouteTitle(pathname: string): string {
  return ROUTE_METADATA[pathname]?.title || '未知页面';
}

export function isActiveRoute(current: string, target: string): boolean {
  if (target === ROUTES.HOME) {
    return current === target;
  }
  return current.startsWith(target);
}
```

### 2.2 路由配置

```typescript
// desktop/src/App.tsx (改造后)

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ROUTES } from './routes';

export function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          {/* 主路由 */}
          <Route path={ROUTES.WORKBENCH} element={<WorkbenchView />} />
          
          {/* 核心功能 */}
          <Route path={ROUTES.RUNS} element={<RunsEventsPage />} />
          <Route path={ROUTES.SETTINGS} element={<SettingsWorkspace />} />
          <Route path={ROUTES.READINESS} element={<ReadinessHealthPage />} />
          
          {/* 集成中心 */}
          <Route path={ROUTES.INTEGRATIONS} element={<IntegrationsWorkspace />}>
            <Route index element={<Navigate to={ROUTES.INTEGRATIONS_MCP} replace />} />
            <Route path="mcp" element={<McpConnectorsPanel />} />
            <Route path="plugins" element={<PluginsSkillsPanel />} />
            <Route path="tools" element={<ToolsApprovalsPanel />} />
            <Route path="gateway" element={<GatewayPanel />} />
          </Route>
          
          {/* 金融实验室 */}
          <Route path={ROUTES.FINANCE_LAB} element={<FinanceLabLayout />}>
            <Route index element={<FinanceLabHome />} />
            <Route path="manager" element={<FinancialManagerWorkspace />} />
            <Route path="market-temperature" element={<MarketTemperatureWorkspace />} />
            <Route path="quant" element={<QuantResearchWorkspace />} />
            <Route path="strategy" element={<StrategyFactoryPanel />} />
            <Route path="factor" element={<FactorFactoryPanel />} />
            <Route path="incubation" element={<IncubationFactoryPanel />} />
            <Route path="data" element={<DataSyncWorkspace />} />
            <Route path="workflows" element={<WorkflowsWorkspace />} />
            <Route path="events" element={<FactoryEventTriggerPanel />} />
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

---

## 三、导航组件改造

### 3.1 侧边栏导航

**改造前：**
```typescript
// 使用状态切换
<button onClick={() => setMainView("settings")}>设置</button>
```

**改造后：**
```typescript
// 使用 Link 组件
import { Link, useLocation } from 'react-router-dom';
import { ROUTES, isActiveRoute } from './routes';

export function AppSidebar() {
  const location = useLocation();
  
  return (
    <nav>
      <Link 
        to={ROUTES.WORKBENCH}
        className={isActiveRoute(location.pathname, ROUTES.WORKBENCH) ? 'active' : ''}
      >
        <LayoutDashboard />
        工作台
      </Link>
      
      <Link 
        to={ROUTES.RUNS}
        className={isActiveRoute(location.pathname, ROUTES.RUNS) ? 'active' : ''}
      >
        <Activity />
        运行与事件
      </Link>
      
      {/* ... 其他导航 */}
    </nav>
  );
}
```

### 3.2 嵌套路由导航（Tab）

```typescript
// desktop/src/features/integrations/IntegrationsWorkspace.tsx

import { NavLink, Outlet } from 'react-router-dom';
import { ROUTES } from '@/routes';

export function IntegrationsWorkspace() {
  return (
    <PageShell
      title="集成中心"
      filters={
        <div className="tab-nav">
          <NavLink to={ROUTES.INTEGRATIONS_MCP} className={({ isActive }) => isActive ? 'active' : ''}>
            MCP 连接器
          </NavLink>
          <NavLink to={ROUTES.INTEGRATIONS_PLUGINS} className={({ isActive }) => isActive ? 'active' : ''}>
            插件与技能
          </NavLink>
          <NavLink to={ROUTES.INTEGRATIONS_TOOLS} className={({ isActive }) => isActive ? 'active' : ''}>
            工具审批
          </NavLink>
          <NavLink to={ROUTES.INTEGRATIONS_GATEWAY} className={({ isActive }) => isActive ? 'active' : ''}>
            网关配置
          </NavLink>
        </div>
      }
    >
      <Outlet />
    </PageShell>
  );
}
```

### 3.3 编程式导航

```typescript
// 在事件处理中导航
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/routes';

export function SomeComponent() {
  const navigate = useNavigate();
  
  const handleSuccess = () => {
    // 导航到其他页面
    navigate(ROUTES.RUNS);
  };
  
  const handleThreadClick = (threadId: string) => {
    // 带参数导航
    navigate(`/thread/${threadId}`);
  };
  
  const handleBack = () => {
    // 返回上一页
    navigate(-1);
  };
  
  return (
    // ...
  );
}
```

---

## 四、URL 参数和查询字符串

### 4.1 动态路由参数

```typescript
// 线程详情页
import { useParams } from 'react-router-dom';

export function ThreadDetailView() {
  const { threadId } = useParams<{ threadId: string }>();
  
  useEffect(() => {
    if (threadId) {
      fetchThread(threadId);
    }
  }, [threadId]);
  
  return (
    <PageShell title={`线程 ${threadId}`}>
      {/* 内容 */}
    </PageShell>
  );
}
```

### 4.2 查询字符串

```typescript
// 带搜索和筛选的页面
import { useSearchParams } from 'react-router-dom';

export function RunsEventsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  
  const search = searchParams.get('search') || '';
  const status = searchParams.get('status') || 'all';
  
  const handleSearchChange = (value: string) => {
    setSearchParams({ search: value, status });
  };
  
  const handleStatusChange = (value: string) => {
    setSearchParams({ search, status: value });
  };
  
  return (
    <PageShell
      title="运行与事件"
      searchValue={search}
      onSearchChange={handleSearchChange}
      filters={
        <select value={status} onChange={(e) => handleStatusChange(e.target.value)}>
          <option value="all">全部</option>
          <option value="running">运行中</option>
          <option value="completed">已完成</option>
        </select>
      }
    >
      {/* 内容 */}
    </PageShell>
  );
}

// URL 示例
// http://localhost:3000/runs?search=test&status=running
```

### 4.3 保持 URL 状态

```typescript
// 自定义 Hook：URL 状态同步
export function useUrlState<T>(
  key: string,
  defaultValue: T
): [T, (value: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  
  const value = useMemo(() => {
    const param = searchParams.get(key);
    return param ? (JSON.parse(param) as T) : defaultValue;
  }, [searchParams, key, defaultValue]);
  
  const setValue = useCallback(
    (newValue: T) => {
      const params = new URLSearchParams(searchParams);
      params.set(key, JSON.stringify(newValue));
      setSearchParams(params);
    },
    [key, searchParams, setSearchParams]
  );
  
  return [value, setValue];
}

// 使用
export function FilterablePage() {
  const [filters, setFilters] = useUrlState('filters', { category: 'all', sortBy: 'date' });
  
  return (
    <PageShell title="可筛选页面">
      <select 
        value={filters.category} 
        onChange={(e) => setFilters({ ...filters, category: e.target.value })}
      >
        <option value="all">全部</option>
        <option value="finance">金融</option>
      </select>
    </PageShell>
  );
}
```

---

## 五、面包屑导航

### 5.1 自动生成面包屑

```typescript
// desktop/src/components/Breadcrumbs.tsx

import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';
import { ROUTE_METADATA } from '@/routes';

export function Breadcrumbs() {
  const location = useLocation();
  const pathSegments = location.pathname.split('/').filter(Boolean);
  
  const breadcrumbs = useMemo(() => {
    const items = [{ path: '/', title: '工作台' }];
    
    let currentPath = '';
    for (const segment of pathSegments) {
      currentPath += `/${segment}`;
      const metadata = ROUTE_METADATA[currentPath];
      if (metadata) {
        items.push({ path: currentPath, title: metadata.title });
      }
    }
    
    return items;
  }, [location.pathname]);
  
  if (breadcrumbs.length <= 1) {
    return null;
  }
  
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      {breadcrumbs.map((item, index) => (
        <span key={item.path} className="breadcrumb-item">
          {index > 0 && <ChevronRight size={14} />}
          {index === breadcrumbs.length - 1 ? (
            <span className="current">{item.title}</span>
          ) : (
            <Link to={item.path}>{item.title}</Link>
          )}
        </span>
      ))}
    </nav>
  );
}
```

### 5.2 集成到 PageShell

```typescript
// 在 PageShell 中显示面包屑
export function PageShell({ title, showBreadcrumbs = true, ... }) {
  return (
    <section className="page-shell">
      <header className="page-shell-header">
        {showBreadcrumbs && <Breadcrumbs />}
        <h1>{title}</h1>
        {/* ... */}
      </header>
      {/* ... */}
    </section>
  );
}
```

---

## 六、路由守卫

### 6.1 权限检查

```typescript
// desktop/src/components/ProtectedRoute.tsx

import { Navigate, useLocation } from 'react-router-dom';
import { ROUTES } from '@/routes';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiresAuth?: boolean;
  requiresFullMode?: boolean;
}

export function ProtectedRoute({
  children,
  requiresAuth = false,
  requiresFullMode = false,
}: ProtectedRouteProps) {
  const location = useLocation();
  const { isAuthenticated, fullModeActive } = useAppStatus();
  
  if (requiresAuth && !isAuthenticated) {
    return <Navigate to={ROUTES.SETTINGS} state={{ from: location }} replace />;
  }
  
  if (requiresFullMode && !fullModeActive) {
    return (
      <div className="access-denied">
        <h2>需要完整模式</h2>
        <p>此功能需要启用完整工具模式</p>
        <Link to={ROUTES.SETTINGS}>前往设置</Link>
      </div>
    );
  }
  
  return <>{children}</>;
}

// 使用
<Route 
  path={ROUTES.FINANCE_STRATEGY} 
  element={
    <ProtectedRoute requiresFullMode>
      <StrategyFactoryPanel />
    </ProtectedRoute>
  } 
/>
```

### 6.2 数据预加载

```typescript
// 使用 loader 预加载数据（React Router v6.4+）
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

const router = createBrowserRouter([
  {
    path: ROUTES.THREAD,
    element: <ThreadDetailView />,
    loader: async ({ params }) => {
      const thread = await fetchThread(params.threadId);
      return { thread };
    },
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}

// 在组件中使用
import { useLoaderData } from 'react-router-dom';

export function ThreadDetailView() {
  const { thread } = useLoaderData();
  
  return (
    <PageShell title={thread.title}>
      {/* 数据已预加载 */}
    </PageShell>
  );
}
```

---

## 七、实施步骤

### Step 1: 安装依赖

```bash
npm install react-router-dom@^6.20.0
npm install --save-dev @types/react-router-dom
```

### Step 2: 创建路由配置文件

```bash
touch desktop/src/routes.ts
```

复制上面的路由配置代码。

### Step 3: 改造 App.tsx

```bash
# 备份原文件
cp desktop/src/App.tsx desktop/src/App.tsx.backup

# 编辑文件，添加 BrowserRouter 和 Routes
code desktop/src/App.tsx
```

**关键改动：**
1. 移除 `useState<MainView>` 状态
2. 添加 `<BrowserRouter>` 包裹
3. 将视图切换逻辑改为 `<Routes>`
4. 更新 `onSelectView` 为 `navigate`

### Step 4: 改造 AppSidebar

```bash
code desktop/src/components/AppSidebar.tsx
```

**关键改动：**
1. 将 `onClick={() => onSelectView(view)}` 改为 `<Link to={ROUTES[view]}>`
2. 使用 `useLocation` 判断当前路由
3. 使用 `isActiveRoute` 设置 active 样式

### Step 5: 改造功能页导航

逐个更新功能页：
- IntegrationsWorkspace：使用 `<Outlet>` 和 `<NavLink>`
- FinanceLabLayout：使用嵌套路由
- 其他页面：移除状态切换逻辑

### Step 6: 测试路由功能

```bash
# 启动开发服务器
npm run dev

# 测试清单
# [ ] 直接访问 URL 正常
# [ ] 浏览器前进/后退正常
# [ ] 刷新页面保持当前页
# [ ] 侧边栏导航正常
# [ ] Tab 切换正常
# [ ] URL 参数正常
```

---

## 八、迁移对照表

| 旧方式 | 新方式 |
|--------|--------|
| `setMainView("settings")` | `navigate(ROUTES.SETTINGS)` |
| `mainView === "settings"` | `location.pathname === ROUTES.SETTINGS` |
| `<button onClick={() => setMainView("runs")}>` | `<Link to={ROUTES.RUNS}>` |
| 无 URL 变化 | `http://localhost:3000/runs` |
| 刷新页面回到首页 | 刷新保持当前页 |
| 无法分享当前页面 | 可以复制 URL 分享 |

---

## 九、常见问题

### Q1: 现有的 MainView 状态怎么办？

**A:** 逐步废弃，通过路由获取当前页面：

```typescript
// 旧代码
const [mainView, setMainView] = useState<MainView>("workbench");

// 新代码
import { useLocation } from 'react-router-dom';

function getCurrentView(pathname: string): string {
  if (pathname.startsWith('/runs')) return 'runs';
  if (pathname.startsWith('/integrations')) return 'integrations';
  // ...
  return 'workbench';
}

const location = useLocation();
const currentView = getCurrentView(location.pathname);
```

### Q2: 如何兼容旧的 URL（如果已部署）？

**A:** 添加重定向路由：

```typescript
<Routes>
  {/* 新路由 */}
  <Route path="/runs" element={<RunsEventsPage />} />
  
  {/* 兼容旧 URL（如果有） */}
  <Route path="/old-runs" element={<Navigate to="/runs" replace />} />
</Routes>
```

### Q3: 如何处理外部链接跳转？

**A:** 使用 `window.location.hash` 或 URL 参数：

```typescript
// 外部链接（如邮件）
// https://app.aiask.com/#/runs?threadId=123

// 在 App 中处理
useEffect(() => {
  const hash = window.location.hash;
  if (hash) {
    const path = hash.slice(1); // 移除 #
    navigate(path);
  }
}, []);
```

---

## 十、测试计划

### 10.1 路由测试

```typescript
// desktop/src/__tests__/routes.test.tsx

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';

describe('Routes', () => {
  it('renders workbench at root', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText('工作台')).toBeInTheDocument();
  });
  
  it('renders runs page at /runs', () => {
    render(
      <MemoryRouter initialEntries={['/runs']}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText('运行与事件')).toBeInTheDocument();
  });
  
  it('redirects to 404 for invalid routes', () => {
    render(
      <MemoryRouter initialEntries={['/invalid-route']}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText('404')).toBeInTheDocument();
  });
});
```

### 10.2 导航测试

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { AppSidebar } from '../components/AppSidebar';

describe('AppSidebar Navigation', () => {
  it('navigates to settings when clicked', () => {
    render(
      <BrowserRouter>
        <AppSidebar />
      </BrowserRouter>
    );
    
    const settingsLink = screen.getByText('设置');
    fireEvent.click(settingsLink);
    
    expect(window.location.pathname).toBe('/settings');
  });
});
```

---

## 十一、性能优化

### 11.1 代码分割

```typescript
// 懒加载路由组件
import { lazy, Suspense } from 'react';

const FinanceLabLayout = lazy(() => import('./features/finance-lab/FinanceLabLayout'));
const StrategyFactoryPanel = lazy(() => import('./features/factory/StrategyFactoryPanel'));

// 使用 Suspense 包裹
<Route 
  path={ROUTES.FINANCE_LAB} 
  element={
    <Suspense fallback={<PageLoader />}>
      <FinanceLabLayout />
    </Suspense>
  }
/>
```

### 11.2 预加载常用路由

```typescript
// 在 App 启动时预加载
useEffect(() => {
  // 预加载常用页面
  import('./features/runs/RunsEventsPage');
  import('./features/integrations/IntegrationsWorkspace');
}, []);
```

---

## 十二、上线检查清单

- [ ] 所有页面都有对应的路由
- [ ] 侧边栏导航使用 Link 组件
- [ ] 嵌套路由使用 Outlet
- [ ] URL 参数和查询字符串正常
- [ ] 浏览器前进/后退正常
- [ ] 刷新页面保持状态
- [ ] 面包屑导航显示正确
- [ ] 404 页面正常
- [ ] 路由守卫生效
- [ ] 所有测试通过
- [ ] 更新了文档
