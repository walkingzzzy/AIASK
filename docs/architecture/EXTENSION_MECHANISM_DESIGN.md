# HERMES 扩展机制设计 - Slot & Page Registration

**版本**: 1.0  
**日期**: 2026-06-04  
**状态**: 设计完成，待实施

---

## 1. 设计目标

### 1.1 核心需求
- 允许插件注册自定义页面和组件
- 提供统一的扩展点（Slot）机制
- 保持类型安全和开发体验
- 支持热插拔和生命周期管理

### 1.2 非功能需求
- 向后兼容现有页面系统
- 最小化性能开销
- 清晰的错误处理和降级策略

---

## 2. 架构设计

### 2.1 Slot 系统

#### Slot Schema
```typescript
interface SlotDefinition {
  id: string;                    // 唯一标识，如 "workbench.quick-actions"
  name: string;                  // 显示名称
  location: string;              // 所在页面，如 "workbench" | "sessions"
  type: "component" | "action" | "section";
  position?: "top" | "bottom" | "sidebar";
  priority?: number;             // 排序优先级，默认 100
  constraints?: {
    max_items?: number;
    required_permissions?: string[];
  };
}

interface SlotContent {
  slot_id: string;
  plugin_id: string;
  component: React.ComponentType<any>;
  props?: Record<string, unknown>;
  enabled: boolean;
  priority: number;
}
```

#### 预定义 Slot 位置
```typescript
const BUILTIN_SLOTS: SlotDefinition[] = [
  {
    id: "workbench.quick-actions",
    name: "Workbench 快捷操作",
    location: "workbench",
    type: "action",
    position: "top"
  },
  {
    id: "workbench.summary-cards",
    name: "Workbench 摘要卡片",
    location: "workbench",
    type: "component",
    position: "sidebar"
  },
  {
    id: "sessions.toolbar",
    name: "Sessions 工具栏",
    location: "sessions",
    type: "action",
    position: "top"
  },
  {
    id: "tools.detail-tabs",
    name: "Tools 详情选项卡",
    location: "tools",
    type: "section"
  }
];
```

### 2.2 Page Registration

#### Page Schema
```typescript
interface PageRegistration {
  id: string;                    // 唯一标识
  plugin_id: string;             // 所属插件
  path: string;                  // 路由路径，如 "/plugin/my-page"
  component: React.ComponentType<PageProps>;
  metadata: {
    title: string;
    group?: "agent" | "operations" | "settings" | "custom";
    icon?: React.ComponentType;
    requires_control_token?: boolean;
    visible_in_nav?: boolean;
  };
  lifecycle?: {
    onMount?: () => void;
    onUnmount?: () => void;
  };
}

interface PageProps {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
}
```

---

## 3. 实现方案

### 3.1 Slot Registry

```typescript
// desktop/src/slots/SlotRegistry.ts
class SlotRegistry {
  private slots = new Map<string, SlotDefinition>();
  private contents = new Map<string, SlotContent[]>();

  registerSlot(slot: SlotDefinition) {
    this.slots.set(slot.id, slot);
  }

  registerContent(content: SlotContent) {
    const existing = this.contents.get(content.slot_id) || [];
    this.contents.set(content.slot_id, [...existing, content]);
  }

  getSlotContents(slotId: string): SlotContent[] {
    return (this.contents.get(slotId) || [])
      .filter(c => c.enabled)
      .sort((a, b) => a.priority - b.priority);
  }
}

export const slotRegistry = new SlotRegistry();
```

### 3.2 SlotRenderer 组件

```typescript
// desktop/src/components/SlotRenderer.tsx
interface SlotRendererProps {
  slotId: string;
  fallback?: React.ReactNode;
  maxItems?: number;
}

export function SlotRenderer({ slotId, fallback, maxItems }: SlotRendererProps) {
  const contents = slotRegistry.getSlotContents(slotId);
  const items = maxItems ? contents.slice(0, maxItems) : contents;

  if (items.length === 0) {
    return fallback ? <>{fallback}</> : null;
  }

  return (
    <div className="slot-container" data-slot-id={slotId}>
      {items.map((content) => {
        const Component = content.component;
        return (
          <div key={`${content.plugin_id}-${content.slot_id}`} className="slot-item">
            <Component {...content.props} />
          </div>
        );
      })}
    </div>
  );
}
```

### 3.3 Page Registry

```typescript
// desktop/src/pages/PageRegistry.ts
class PageRegistry {
  private pages = new Map<string, PageRegistration>();

  register(page: PageRegistration) {
    if (this.pages.has(page.id)) {
      console.warn(`Page ${page.id} already registered, overwriting`);
    }
    this.pages.set(page.id, page);
  }

  unregister(pageId: string) {
    this.pages.delete(pageId);
  }

  getPage(pageId: string): PageRegistration | undefined {
    return this.pages.get(pageId);
  }

  getAllPages(): PageRegistration[] {
    return Array.from(this.pages.values());
  }

  getVisiblePages(): PageRegistration[] {
    return this.getAllPages().filter(p => p.metadata.visible_in_nav !== false);
  }
}

export const pageRegistry = new PageRegistry();
```

### 3.4 路由集成

```typescript
// desktop/src/App.tsx 中的扩展
function App() {
  // ... 现有代码

  // 动态注册的页面路由
  const dynamicPages = pageRegistry.getAllPages();

  return (
    <Router>
      <Routes>
        {/* 现有静态路由 */}
        <Route path="/" element={<WorkbenchPage {...} />} />
        
        {/* 动态插件页面路由 */}
        {dynamicPages.map(page => (
          <Route
            key={page.id}
            path={page.path}
            element={<page.component {...commonProps} />}
          />
        ))}
      </Routes>
    </Router>
  );
}
```

---

## 4. 使用示例

### 4.1 插件注册自定义页面

```typescript
// 插件代码示例
import { pageRegistry } from "@aiask/desktop/pages/PageRegistry";
import { MyCustomPage } from "./MyCustomPage";

export function registerMyPlugin() {
  pageRegistry.register({
    id: "my-plugin.custom-page",
    plugin_id: "my-plugin",
    path: "/plugin/my-custom-page",
    component: MyCustomPage,
    metadata: {
      title: "我的自定义页面",
      group: "custom",
      visible_in_nav: true
    }
  });
}
```

### 4.2 插件注册 Slot 内容

```typescript
import { slotRegistry } from "@aiask/desktop/slots/SlotRegistry";
import { QuickActionButton } from "./QuickActionButton";

export function registerSlotContent() {
  slotRegistry.registerContent({
    slot_id: "workbench.quick-actions",
    plugin_id: "my-plugin",
    component: QuickActionButton,
    props: { action: "my-action" },
    enabled: true,
    priority: 50
  });
}
```

### 4.3 页面中使用 Slot

```typescript
// desktop/src/features/agent-pages/WorkbenchView.tsx
import { SlotRenderer } from "../../components/SlotRenderer";

export function WorkbenchView() {
  return (
    <div>
      {/* 现有内容 */}
      <div className="quick-actions">
        <SlotRenderer slotId="workbench.quick-actions" maxItems={5} />
      </div>

      <div className="summary-sidebar">
        <SlotRenderer slotId="workbench.summary-cards" />
      </div>
    </div>
  );
}
```

---

## 5. 生命周期管理

### 5.1 插件加载流程

```typescript
class PluginLifecycleManager {
  async loadPlugin(pluginId: string) {
    // 1. 加载插件代码
    const plugin = await import(`./plugins/${pluginId}`);
    
    // 2. 验证插件 schema
    if (!this.validatePlugin(plugin)) {
      throw new Error(`Invalid plugin: ${pluginId}`);
    }
    
    // 3. 注册页面和 Slot
    if (plugin.registerPages) {
      plugin.registerPages(pageRegistry);
    }
    if (plugin.registerSlots) {
      plugin.registerSlots(slotRegistry);
    }
    
    // 4. 调用生命周期钩子
    if (plugin.onLoad) {
      await plugin.onLoad();
    }
  }

  async unloadPlugin(pluginId: string) {
    // 1. 调用卸载钩子
    const plugin = this.plugins.get(pluginId);
    if (plugin?.onUnload) {
      await plugin.onUnload();
    }
    
    // 2. 清理注册的页面和 Slot
    this.cleanupPluginRegistrations(pluginId);
    
    // 3. 移除插件引用
    this.plugins.delete(pluginId);
  }
}
```

---

## 6. 安全和权限

### 6.1 权限检查

```typescript
interface PermissionCheck {
  required_permissions: string[];
  requires_control_token: boolean;
  requires_admin: boolean;
}

function canRenderSlot(
  slot: SlotContent,
  userPermissions: string[],
  hasControlToken: boolean
): boolean {
  const slotDef = slotRegistry.getSlot(slot.slot_id);
  
  if (slotDef.constraints?.required_permissions) {
    const hasPermissions = slotDef.constraints.required_permissions.every(
      perm => userPermissions.includes(perm)
    );
    if (!hasPermissions) return false;
  }
  
  // 其他权限检查...
  return true;
}
```

---

## 7. 实施计划

### 7.1 Phase 1: 基础架构（1周）
- [ ] 实现 SlotRegistry
- [ ] 实现 PageRegistry
- [ ] 创建 SlotRenderer 组件
- [ ] 集成到 App.tsx 路由

### 7.2 Phase 2: 内置 Slot（1周）
- [ ] 在 Workbench 添加 2-3 个 Slot
- [ ] 在 Sessions/Tools 添加 Slot
- [ ] 创建示例插件验证

### 7.3 Phase 3: 文档和工具（3天）
- [ ] 编写插件开发文档
- [ ] 创建插件模板
- [ ] 提供 TypeScript 类型定义

---

## 8. 测试策略

### 8.1 单元测试
- SlotRegistry 增删改查
- PageRegistry 路由注册
- 权限检查逻辑

### 8.2 集成测试
- 插件加载和卸载流程
- Slot 渲染优先级
- 页面导航和生命周期

### 8.3 E2E 测试
- 完整插件安装流程
- 多个插件共存
- 插件热更新

---

## 9. 性能考虑

### 9.1 优化策略
- Slot 内容缓存
- 懒加载插件组件
- 虚拟滚动大量 Slot 内容

### 9.2 监控指标
- 插件加载时间
- Slot 渲染性能
- 内存占用

---

## 10. 向后兼容

### 10.1 迁移策略
- 保持现有页面系统不变
- 扩展机制作为附加层
- 逐步迁移内置功能到 Slot

### 10.2 降级方案
- Slot 加载失败时隐藏
- 插件错误不影响主应用
- 提供禁用扩展的开关

---

**状态**: ✅ 设计完成，可进入实施阶段  
**预计工期**: 2-3 周  
**依赖**: 无阻塞依赖  
**风险**: 低（隔离设计，不影响现有功能）
