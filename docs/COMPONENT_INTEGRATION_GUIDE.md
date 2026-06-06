# HERMES 0.15.1 新组件集成指南

**版本**: 1.0  
**日期**: 2026-06-04  
**目标**: 快速集成新创建的增强组件

---

## 📦 新增组件清单

### 运维增强组件
1. `McpOAuthStatus.tsx` - MCP OAuth 状态展示
2. `GatewayRetryPanel.tsx` - Gateway 消息重试
3. `ReadinessDiagnostic.tsx` - 系统健康诊断

### 页面增强组件
4. `PluginLifecycleCard.tsx` - 插件生命周期状态
5. `ModeImpactExplainer.tsx` - 模式影响说明
6. `ConfigSectionManager.tsx` - 配置分区管理

### 样式文件
7. `AgentEnhancements.css` - 运维组件样式
8. `PluginLifecycleCard.css` - 插件组件样式

---

## 🚀 快速集成步骤

### 1. 集成 McpOAuthStatus 到 MCP 页面

#### 步骤 1.1: 导入组件
```typescript
// desktop/src/features/mcp/McpPanel.tsx
import { McpOAuthStatus } from "../../components/McpOAuthStatus";
import "../../components/AgentEnhancements.css";
```

#### 步骤 1.2: 准备数据
```typescript
// 在 McpPanel 组件中添加数据转换
function McpPanel({ payload, ... }) {
  // ... 现有代码
  
  const oauthServers = useMemo(() => {
    if (!payload?.mcp?.oauth) return [];
    
    return payload.mcp.oauth.map(server => ({
      server: server.server || server.name,
      status: server.authenticated ? "authenticated" : "missing",
      expires_at: server.expires_at,
      last_auth_at: server.last_auth_at,
      error_message: server.error
    }));
  }, [payload]);

  async function handleReauthorize(server: string) {
    await api.mcpOauthStart(server);
    await onRefresh?.();
  }
  
  // ...
}
```

#### 步骤 1.3: 添加到渲染
```typescript
// 在 McpPanel 的返回 JSX 中添加
return (
  <section className="capability-section">
    {/* ... 现有内容 */}
    
    {/* 新增 OAuth 状态面板 */}
    <McpOAuthStatus
      oauthServers={oauthServers}
      onReauthorize={handleReauthorize}
    />
  </section>
);
```

---

### 2. 集成 GatewayRetryPanel 到 Gateway 页面

#### 步骤 2.1: 导入组件
```typescript
// desktop/src/features/agent-pages/GatewayPage.tsx
import { GatewayRetryPanel } from "../../components/GatewayRetryPanel";
import "../../components/AgentEnhancements.css";
```

#### 步骤 2.2: 添加状态和 API 调用
```typescript
export function GatewayPage({ endpoint, apiToken, controlToken, userId }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [messages, setMessages] = useState<GatewayMessage[]>([]);

  async function loadMessages() {
    try {
      const result = await api.gatewayMessagesList({ status: "failed" });
      setMessages(result.data || []);
    } catch (error) {
      console.error("Failed to load messages:", error);
    }
  }

  async function retryMessage(messageId: string) {
    await api.gatewayMessageRetry(messageId);
    await loadMessages();
  }

  async function batchRetryMessages(messageIds: string[]) {
    await Promise.all(messageIds.map(id => api.gatewayMessageRetry(id)));
    await loadMessages();
  }

  useEffect(() => {
    loadMessages();
  }, []);

  return (
    <section className="capabilities-workspace">
      {/* ... 现有内容 */}
      
      <GatewayRetryPanel
        messages={messages}
        onRetry={retryMessage}
        onBatchRetry={batchRetryMessages}
      />
    </section>
  );
}
```

---

### 3. 集成 ReadinessDiagnostic 到 Readiness 页面

#### 步骤 3.1: 导入组件
```typescript
// desktop/src/features/agent-pages/ReadinessHealthPage.tsx
import { ReadinessDiagnostic } from "../../components/ReadinessDiagnostic";
import "../../components/AgentEnhancements.css";
```

#### 步骤 3.2: 准备诊断数据
```typescript
export function ReadinessHealthPage({ endpoint, apiToken }) {
  const [diagnosticResults, setDiagnosticResults] = useState<DiagnosticResult[]>([]);

  async function runDiagnostics() {
    try {
      const result = await api.readinessDiagnostic();
      setDiagnosticResults(result.data?.results || []);
    } catch (error) {
      // 如果后端还没实现，可以使用模拟数据
      setDiagnosticResults(getMockDiagnosticResults());
    }
  }

  function getMockDiagnosticResults(): DiagnosticResult[] {
    return [
      {
        category: "连接",
        status: "healthy",
        title: "API 连接正常",
        message: "所有 API 端点响应正常，延迟在可接受范围内。",
        fix_suggestions: []
      },
      {
        category: "MCP",
        status: "warning",
        title: "部分 MCP 服务未认证",
        message: "有 2 个 MCP 服务需要重新认证。",
        fix_suggestions: [
          "前往 MCP/Connectors 页面",
          "点击"重新认证"按钮",
          "完成 OAuth 授权流程"
        ],
        related_page: "MCP / Connectors"
      }
    ];
  }

  function handleNavigate(page: string) {
    // 导航到相关页面
    // 需要集成到路由系统
  }

  return (
    <section className="capabilities-workspace">
      {/* ... 现有内容 */}
      
      <ReadinessDiagnostic
        results={diagnosticResults}
        onNavigate={handleNavigate}
      />
    </section>
  );
}
```

---

### 4. 集成 PluginLifecycleCard 到 Plugins 页面

#### 步骤 4.1: 导入组件
```typescript
// desktop/src/features/capabilities/PluginsPanel.tsx
import { PluginLifecycleCard, inferPluginLifecycleState } from "../../components/PluginLifecycleCard";
import "../../components/PluginLifecycleCard.css";
```

#### 步骤 4.2: 在渲染中使用
```typescript
export function PluginsPanel({ payload, ... }) {
  // ... 现有代码

  return (
    <section>
      {/* 将原有的插件列表替换为生命周期卡片 */}
      {plugins.map((plugin) => {
        const lifecycleState = inferPluginLifecycleState(plugin);
        
        return (
          <PluginLifecycleCard
            key={plugin.name}
            name={plugin.name}
            state={lifecycleState}
            onToggle={() => togglePlugin(plugin)}
            onConfigure={() => {/* 打开配置对话框 */}}
            onTest={() => testPlugin(plugin)}
          />
        );
      })}
    </section>
  );
}
```

---

### 5. 集成 ModeImpactExplainer 到 Settings 页面

#### 步骤 5.1: 导入组件
```typescript
// desktop/src/features/settings/LocalUserSettings.tsx (或类似文件)
import { ModeImpactExplainer } from "../../components/ModeImpactExplainer";
```

#### 步骤 5.2: 准备数据
```typescript
const modeImpacts: ModeImpact[] = [
  {
    mode: "finance_safe",
    tools_available: 120,
    tools_blocked: 35,
    side_effects_allowed: ["read_only", "analytics"],
    confirmations_required: true,
    risk_level: "low",
    recommendations: [
      "适合生产环境使用",
      "所有数据写入操作需要确认",
      "仅允许金融安全的工具"
    ]
  },
  {
    mode: "full",
    tools_available: 155,
    tools_blocked: 0,
    side_effects_allowed: ["read_only", "analytics", "write", "execute"],
    confirmations_required: false,
    risk_level: "high",
    recommendations: [
      "仅用于开发和测试环境",
      "具有完整的系统访问权限",
      "需要谨慎使用"
    ]
  }
];
```

#### 步骤 5.3: 添加到页面
```typescript
return (
  <div className="settings-page">
    <h2>模式配置</h2>
    
    <ModeImpactExplainer
      currentMode={currentMode}
      impacts={modeImpacts}
      onModeSelect={handleModeChange}
    />
  </div>
);
```

---

### 6. 集成 ConfigSectionManager 到 Settings 页面

#### 步骤 6.1: 导入组件
```typescript
import { ConfigSectionManager, DEFAULT_CONFIG_SECTIONS } from "../../components/ConfigSectionManager";
```

#### 步骤 6.2: 使用组件
```typescript
export function SettingsPage() {
  const [activeSection, setActiveSection] = useState("connection");

  return (
    <div className="settings-layout">
      <ConfigSectionManager
        sections={DEFAULT_CONFIG_SECTIONS}
        activeSection={activeSection}
        onSectionChange={setActiveSection}
      />
      
      <div className="settings-content">
        {activeSection === "connection" && <ConnectionSettings />}
        {activeSection === "user" && <UserSettings />}
        {activeSection === "security" && <SecuritySettings />}
        {/* ... 其他分区 */}
      </div>
    </div>
  );
}
```

---

## 🎨 样式集成

### 全局样式导入
在主样式文件中导入新组件样式：

```css
/* desktop/src/styles.css */
@import "./components/AgentEnhancements.css";
@import "./components/PluginLifecycleCard.css";
```

或在需要的组件中单独导入。

---

## 🧪 测试建议

### 集成后测试清单
- [ ] MCP OAuth 状态正确显示
- [ ] Gateway 重试功能可用
- [ ] Readiness 诊断展示正常
- [ ] Plugin 生命周期状态准确
- [ ] 模式切换说明清晰
- [ ] 配置分区导航流畅

### 手动测试步骤
1. 启动应用，检查控制台无错误
2. 依次访问各个增强页面
3. 测试交互功能（按钮、表单）
4. 验证样式正确渲染
5. 测试边界情况（空数据、错误状态）

---

## ⚠️ 常见问题

### Q1: 组件不显示？
**A**: 检查数据格式是否符合组件 Props 类型定义。

### Q2: 样式不生效？
**A**: 确认 CSS 文件已正确导入，检查 className 拼写。

### Q3: API 调用失败？
**A**: 部分功能需要后端支持，暂时可使用 mock 数据。

### Q4: TypeScript 类型错误？
**A**: 确保从正确路径导入类型定义。

---

## 📝 后续工作

### 立即完成（1-2天）
- [ ] 按本指南集成所有组件
- [ ] 补充缺失的 API 调用
- [ ] 完善样式细节

### 短期完成（1周）
- [ ] 添加后端 API 支持
- [ ] 编写单元测试
- [ ] 完善错误处理

### 中期完成（2-3周）
- [ ] 实施扩展机制（见 EXTENSION_MECHANISM_DESIGN.md）
- [ ] 补充 E2E 测试
- [ ] 更新用户文档

---

## 🔗 相关文档

- `HERMES_0_15_1_FINAL_REPORT.md` - 完整实施报告
- `EXTENSION_MECHANISM_DESIGN.md` - 扩展机制设计
- 各组件源码中的 TypeScript 类型定义

---

**状态**: ✅ 指南完成  
**适用对象**: 前端开发人员  
**预计集成时间**: 1-2 天
