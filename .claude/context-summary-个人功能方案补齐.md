## 项目上下文摘要（个人功能方案补齐）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `apps/bff/src/paper-trading/paper-trading.controller.ts` + `apps/bff/src/paper-trading/paper-trading.service.ts`
  - 模式：NestJS `controller -> service -> MCP/DB`。
  - 可复用：统一封装参数、返回 `{ success, data }`、异常转 `BadGatewayException`。
  - 需注意：优先复用现有 service 调用与 query 失效机制。

- **实现2**: `apps/bff/src/watchlist/watchlist.controller.ts` + `apps/bff/src/watchlist/watchlist.service.ts`
  - 模式：当前用户 `req.user?.id` 注入、`CommonCacheService` 缓存列表、MCP manager/工具调用。
  - 可复用：按用户缓存 key、组装 `JSON.stringify({ user_id, ... })`。
  - 需注意：已有接口为 `/watchlist/groups|stocks/*`，与方案草案路径不完全一致。

- **实现3**: `apps/bff/src/notification/notification.controller.ts` + `notification.service.ts` + `apps/web/components/notification-bell.tsx`
  - 模式：BFF 维护通知列表与未读数，前端 30 秒轮询 + WS 增量提醒。
  - 可复用：未读计数、列表接口、下拉面板 UI。
  - 需注意：当前通知是全局缓存，未按用户隔离，需要补齐。

- **实现4**: `apps/bff/src/auth/preferences.service.ts` + `apps/web/hooks/use-dashboard-prefs.ts`
  - 模式：`PreferencesService` 读写 `app_users.preferences`，前端本地 + 远端偏好同步。
  - 可复用：`setPreferences()`、profile `preferences` 合并写入。
  - 需注意：`/auth/profile` 当前只回显不持久化。

- **实现5**: `apps/bff/src/audit/audit.store.ts`
  - 模式：DB + 内存双模式存储。
  - 可复用：`list(limit)` 的 DB/内存降级模式，可扩展为 `listByUser(userId, limit)`。
  - 需注意：当前 controller 仅 admin 可读，不满足个人安全日志需求。

### 2. 项目约定
- **后端风格**：NestJS，controller 使用 DTO + class-validator；service 负责业务与数据访问。
- **前端风格**：Next App Router，复用 `PageContainer`、`SectionCard`、`KpiCard/KpiGrid`、`DataTable`、`useApiQuery`、`useApiMutation`。
- **导出能力**：复用 `apps/web/lib/export.ts:exportCSV`。
- **登录态**：前端 `logged_in` cookie 供 `middleware.ts` 判断；真实鉴权依赖 BFF cookie。
- **会话模型**：`AuthService` 已有 `app_sessions`（DB）+ `sessionsByRefresh`（内存）双模式。

### 3. 可复用组件清单
- `apps/bff/src/auth/preferences.service.ts`：用户 preferences 持久化。
- `apps/bff/src/common/cache.service.ts`：缓存未读数、自选股、通知列表。
- `apps/bff/src/audit/audit.store.ts`：审计日志存取。
- `apps/web/lib/export.ts`：CSV 导出。
- `apps/web/hooks/use-dashboard-prefs.ts`：本地+远端偏好同步模式。
- `apps/web/components/notification-bell.tsx`：通知下拉交互骨架。
- `apps/web/app/user/page.tsx`：个人信息与模拟盘概览现有 UI 基线。

### 4. 测试与验证基线
- **BFF**：无现成单元测试脚本，最可靠验证为 `npm run build -w apps/bff`。
- **Web**：`npm run typecheck -w apps/web`、`npm run build -w apps/web`。
- **Python**：若涉及 MCP/虚拟盘再用 `pytest -o addopts='' ...`，本任务优先 BFF/Web。
- **现有测试目录**：`apps/bff/test/contract` 存在但规模很小，当前更适合用构建验证。

### 5. 依赖与集成点
- **Auth**：`auth.controller.ts`、`auth.service.ts`、`preferences.service.ts`、`auth-store.ts`。
- **Dashboard**：`apps/web/app/page.tsx`、`/auth/profile`、`/paper-trading/*`、`/alerts/list`、`/market/batch-quotes`。
- **Watchlist**：`watchlist.service.ts` 与 `watchlist-store.ts` 已部分并存，需要避免重复状态源冲突。
- **Notification**：当前 `notification.service.ts` 全局缓存，需改为按用户隔离，并接 WS/页面读取。
- **Settings/User**：当前以 `/user`、`/settings/security`、`/settings/audit-log` 分散存在，需整合 `settings/page.tsx`。
- **Export/Chat Sync**：`apps/bff/src/export/` 为空；`chat-store.ts` 仅内存态，无服务端同步。

### 6. 关键缺口结论
- **P0**：修改密码未实现；profile 持久化未实现；自选股主体已实现但缺路由保护与方案收口。
- **P1**：首页已是 Dashboard，但不是个人资产聚合；通知中心已存在但需按用户隔离；绩效分析接口未实现。
- **P2**：个人安全日志、头像昵称、新手引导未实现。
- **P3**：导出/报告、聊天云同步、会话管理未实现。

### 7. 风险点
- `@nestjs/schedule` 当前不在 `apps/bff/package.json`，实现定时通知时要避免依赖新增或另行申请安装授权。
- `watchlist-store.ts` 与 `watchlist` 页面可能存在重复数据源，需要统一以服务端为准并保留本地增强体验。
- `auth/profile` 返回结构会影响 `auth-store.ts`、`app-shell.tsx`、首页与用户中心多个页面。
- 连续大改需要分批验证，优先保证 BFF/Web build 通过。

### 8. 本轮补齐结果回填
- 已完成：`change-password`、`profile` 持久化、`sessions/revoke`、`audit/my-logs`、通知按用户隔离、虚拟盘绩效分析、导出/报告、聊天会话云同步。
- 已完成前端收口：个人首页聚合、`settings/page.tsx`、头像昵称展示、`middleware.ts` 路由保护、`app-shell.tsx` 设置入口。
- 已新增：`apps/web/components/onboarding.tsx`，通过 `data-tour` 与 `localStorage` 实现首次登录轻量引导。
- 验证方式：`npm run build -w apps/bff`、`npm run typecheck -w apps/web`、`npm run build -w apps/web`、启动 BFF 后执行 `.claude/personal-feature-smoke.mjs` 进行接口烟雾验证。
