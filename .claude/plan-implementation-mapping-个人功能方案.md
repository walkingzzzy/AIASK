## 个人功能开发方案条目到实现映射
生成时间：2026-03-06 11:00
来源：`docs/plans/个人功能开发方案.md`

### 1. 映射范围
本表覆盖方案中的 P0-P3 核心缺失项与本轮实际补齐内容，聚焦：
- 认证与个人档案
- Dashboard / 通知 / 绩效分析
- 安全日志 / 头像昵称 / 新手引导
- 数据导出 / 聊天云同步 / 会话管理

### 2. 实现映射表
| 方案条目 | 方案依据 | 实现文件 | 本地验证 | 状态 |
|---|---|---|---|---|
| 2.1 修改密码 | `POST /auth/change-password` | `apps/bff/src/auth/dto/change-password.dto.ts`、`apps/bff/src/auth/auth.controller.ts`、`apps/bff/src/auth/auth.service.ts`、`apps/web/app/settings/page.tsx` | `npm run build -w apps/bff`、BFF 烟雾测试 `profile/sessions` | 本轮完成 |
| 2.2 Profile 持久化 | `POST /auth/profile` 持久化风险偏好/昵称/头像 | `apps/bff/src/auth/auth.controller.ts`、`apps/bff/src/auth/auth.service.ts`、`apps/bff/src/auth/preferences.service.ts`、`apps/web/store/auth-store.ts` | `npm run build -w apps/bff`、`npm run build -w apps/web` | 本轮完成 |
| 2.3 自选股管理 | 自选股页面与服务端联动 | `apps/bff/src/watchlist/*`、`apps/web/app/watchlist/page.tsx`、`apps/web/store/watchlist-store.ts`、`apps/web/middleware.ts` | `npm run typecheck -w apps/web`、`npm run build -w apps/web` | 既有能力收口完成 |
| 2.4 个人 Dashboard | 首页聚合个人资产/自选/告警/快讯 | `apps/web/app/page.tsx`、`apps/web/components/app-shell.tsx` | `npm run build -w apps/web` | 本轮完成 |
| 2.5 通知中心 + 推送 | 按用户隔离通知与通知中心展示 | `apps/bff/src/notification/notification.service.ts`、`notification.controller.ts`、`notification-bridge.service.ts`、`apps/web/app/notifications/page.tsx`、`apps/web/components/notification-bell.tsx` | BFF 烟雾测试 `notifications`、`npm run build -w apps/web` | 本轮完成 |
| 2.6 收益统计与绩效分析 | `GET /paper-trading/performance` + 前端图表/KPI | `apps/bff/src/paper-trading/paper-trading.controller.ts`、`paper-trading.service.ts`、`apps/web/app/paper-trading/page.tsx` | BFF 烟雾测试 `paper performance`、`npm run build -w apps/web` | 本轮完成 |
| 2.7 登录历史 / 安全日志 | `GET /audit/my-logs` | `apps/bff/src/audit/audit.controller.ts`、`audit.store.ts`、`apps/web/app/settings/page.tsx` | BFF 烟雾测试 `audit` | 本轮完成 |
| 2.8 头像与昵称 | 设置页保存，导航全局生效 | `apps/bff/src/auth/auth.controller.ts`、`auth.service.ts`、`apps/web/app/settings/page.tsx`、`apps/web/components/app-shell.tsx` | `npm run build -w apps/web` | 本轮完成 |
| 2.9 新手引导 | 首次登录轻量 tooltip 引导 | `apps/web/components/onboarding.tsx`、`apps/web/components/app-shell.tsx`、`apps/web/app/page.tsx` | `npm run build -w apps/web` | 本轮新增并完成 |
| 2.10 数据导出 / 投资报告 | `GET /export/my-data`、`GET /export/report` | `apps/bff/src/export/export.module.ts`、`export.controller.ts`、`export.service.ts`、`apps/web/app/settings/page.tsx` | BFF 烟雾测试 `export my-data`、`export report` | 本轮完成 |
| 2.11 对话历史云同步 | conversations 拉取/同步、本地持久化合并 | `apps/bff/src/chat/chat.controller.ts`、`apps/web/store/chat-store.ts`、`apps/web/app/chat/page.tsx` | BFF 烟雾测试 `chat sync`、`chat conversations`、`npm run typecheck -w apps/web` | 本轮完成 |
| 2.12 会话管理 | `GET /auth/sessions`、`POST /auth/sessions/revoke` | `apps/bff/src/auth/auth.controller.ts`、`apps/bff/src/auth/auth.service.ts`、`apps/web/app/settings/page.tsx` | BFF 烟雾测试 `sessions` | 本轮完成 |

### 3. 关键验证结果
- `npm run build -w apps/bff; echo EXIT:$?` → `EXIT:0`
- `npm run typecheck -w apps/web; echo EXIT:$?` → `EXIT:0`
- `npm run build -w apps/web; echo EXIT:$?` → `EXIT:0`
- `node .claude/personal-feature-smoke.mjs` → 成功验证 `chat sync`、`profile`、`sessions`、`audit`、`chat conversations`、`notifications`、`paper performance`、`export my-data`、`export report`

### 4. 当前残余事项
1. `onboarding` 已完成实现与构建验证，但尚无浏览器自动化测试。
2. 通知推送链路已完成用户隔离和读取验证，但尚无专项 WebSocket 自动化测试。

### 5. 结论
就 `docs/plans/个人功能开发方案.md` 的缺口补齐而言，本轮已进入“可验收交付”状态，不再属于“仍有核心功能未实现”的阶段。

