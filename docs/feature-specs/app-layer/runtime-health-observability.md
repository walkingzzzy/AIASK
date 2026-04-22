# App Layer：Health / Observability 状态模型

## 覆盖范围

- 本文覆盖：
  - `apps/bff/src/health/health.service.ts::HealthService`
  - `apps/bff/src/health/health.controller.ts::HealthController`
  - `apps/bff/src/observability/observability.service.ts::ObservabilityService`
  - `apps/bff/src/observability/observability.controller.ts::ObservabilityController`
  - `apps/web/lib/system-health.ts::normalizeSystemHealthSnapshot`
- 目标是把当前已经锁死的字段、状态名、探针语义、指标联动和降级语义写准确。

## 事实来源

- 源码：
  - `apps/bff/src/health/health.service.ts`
  - `apps/bff/src/health/health.controller.ts`
  - `apps/bff/src/observability/observability.service.ts`
  - `apps/bff/src/observability/observability.controller.ts`
  - `apps/bff/src/db/db.service.ts`
  - `apps/bff/src/common/cache.service.ts`
  - `apps/bff/src/audit/audit.store.ts`
  - `apps/bff/src/notification/notification.service.ts`
  - `apps/web/lib/system-health.ts`
- 测试：
  - `apps/bff/test/health.service.test.mjs`

## 取证方式

- `rg -n "type HealthStatus|type HealthSignal|probes:|buildVectorSnapshot|setDependencyState" apps/bff/src/health/health.service.ts`
- `rg -n "@Get\\(|metrics\\(|dependency_status|metricsEndpoint" apps/bff/src/health apps/bff/src/observability`
- `rg -n "normalizeSystemHealthSnapshot|RuntimeHealthStatus|RuntimeHealthSignal" apps/web/lib/system-health.ts`

## 不覆盖范围

- 不展开 Prometheus 抓取、Grafana 告警或监控部署方案。
- 不把 Web 端兼容旧字段的 normalize 逻辑误写成 BFF 当前仍在输出旧字段。

## 当前状态模型

- BFF 当前聚合状态名只使用 `normal | degraded | untrusted`。
- `ok`、`healthy`、`unavailable` 只存在于兼容/归一化语境，不是当前 `HealthService` 的输出值。
- 当前 component signal 字段统一输出 `operational`。
- Web 端 `apps/web/lib/system-health.ts` 仍保留 `boolean` signal 和 `ok/unavailable` 的兼容归一化，只是为了读旧 payload；当前 BFF contract 不应继续按旧值撰写。

## 聚合字段

`GET /api/health` 直接返回 `HealthSnapshot`，不是 `{ success, data }` envelope。当前字段为：

- `success`: 固定为 `true`，不表达 readiness。
- `service`: 固定为 `aiask-bff`。
- `status`: `normal | degraded | untrusted`。
- `startedAt`: BFF 进程启动时间。
- `probes.liveness`: 固定为 `normal`。
- `probes.startup`: `complete | starting`。
- `probes.readiness`: `ready | degraded | blocked`。
- `db | cache | audit | notifications | mcp | vector`: 每项都带 `status`、`signal`、`reasons`，并附带各自 raw 字段。
- `reasons`: 去重后的总原因集合。
- `degradedReasons`: 当前与 `reasons` 等值，只是兼容别名。
- `timestamp`: 本次快照生成时间。

## 聚合判定规则

- 总状态为 `untrusted`：
  - `db.status === "untrusted"`，或
  - `mcp.status === "untrusted"`
- 总状态为 `degraded`：
  - 上面两条都不满足，但聚合 `reasons.length > 0`
- 总状态为 `normal`：
  - 无聚合原因，且 `db` / `mcp` 都不是 `untrusted`
- `readiness`：
  - `blocked` 对应总状态 `untrusted`
  - `degraded` 对应总状态 `degraded`
  - `ready` 对应总状态 `normal`

## 组件判定规则

- `db`
  - `enabled === false` 时：`status = "degraded"`，`mode = "memory"`，原因至少含 `database_disabled`
  - `enabled === true && healthy !== true` 时：`status = "untrusted"`，原因包含 `db_unhealthy`，并优先带上 `lastFailureStage`
- `cache`
  - `configured === false` 时：`status = "degraded"`，原因含 `redis_not_configured`
  - Redis 不可用或 fallback 激活时：`status = "degraded"`，原因含 `cache_memory_fallback`、`redis_unavailable`，并追加 `lastFailureStage`
- `audit`
  - `degraded === true` 时：`status = "degraded"`，原因来自 `degradedReason`
- `notifications`
  - 仅当 `configured === true && failed > 0 && delivered <= 0` 时判为 `degraded`
  - 当前原因码是 `notification_external_delivery_failed`
- `mcp`
  - `reachable === false` 时：`status = "untrusted"`，原因至少含 `mcp_unreachable`
  - transport fallback 或 `matched === false` 时：`status = "degraded"`
  - `matched === false` 会追加 `mcp_tool_count_mismatch`
- `vector`
  - 若 `mcp.status === "untrusted"`：直接返回 `status = "untrusted"`，原因固定含 `mcp_unreachable` 与 `vector_health_unavailable`
  - 否则同步调用 `strategy_manager` 的 `vector_health`
  - 只要命中以下任一条件即为 `degraded`：
    - `fallback_reason`
    - `quality_flags`
    - 缺少 `active_index`
    - 缺少 `latest_snapshot`
    - `collection_count <= 0`
    - `pgvector_enabled === false`
    - `active_index.status` 或 `latest_snapshot.status` 为 `degraded`
  - probe 调用失败时：`status = "untrusted"`，原因为 `vector_health_probe_failed`

## HTTP surface

- `GET /api/health`
  - 直接返回聚合 `HealthSnapshot`
- `GET /api/health/live`
  - 返回 `{ success: true, data: { service, status: "normal", probe: "liveness", startedAt, timestamp } }`
  - 当前不再返回旧值 `status: "ok"`
- `GET /api/health/ready`
  - ready 时返回 `{ success: true, data: HealthSnapshot }`
  - 非 ready 时抛 `503`，响应体仍保持 `{ success: false, data: HealthSnapshot }`
- `GET /api/health/startup`
  - complete 时返回 `{ success: true, data: { ..., status: "normal", probe: "startup" } }`
  - starting 时抛 `503`，响应体是 `{ success: false, data: { ..., status: "starting", probe: "startup" } }`
- `GET /api/health/mcp`
  - 当前返回平铺结构 `{ service, status, signal, reasons, mcp, timestamp }`
  - 不再使用旧的 `{ success, data }` envelope
- `GET /api/health/cache`
  - 当前返回平铺结构 `{ service, status, signal, reasons, cache, timestamp }`
- `GET /api/health/db`
  - 返回 DB 快照加 `reachable`、`latencyMs`
  - `DATABASE_URL` 未配置时仍返回 `200`，但 `status = "degraded"`、`reachable = false`、`mode = "memory"`
- `GET /api/metrics`
  - public
  - controller 会先触发一次 `healthService.getHealth().catch(() => null)`，确保 dependency gauge 在导出前尽量刷新

## Observability 指标联动

- `ObservabilityService.snapshot()` 当前固定对外声明 `metricsEndpoint: "/api/metrics"`
- 指标名已锁定为：
  - `aiask_bff_http_requests_total`
  - `aiask_bff_http_request_duration_seconds`
  - `aiask_bff_mcp_calls_total`
  - `aiask_bff_mcp_call_duration_seconds`
  - `aiask_bff_db_queries_total`
  - `aiask_bff_db_query_duration_seconds`
  - `aiask_bff_dependency_status`
- `aiask_bff_dependency_status` 语义已锁定：
  - `2 = normal`
  - `1 = degraded`
  - `0 = untrusted`
- 依赖 gauge label 当前不是完全跟 `/health` key 一一同名：
  - PostgreSQL 使用 `dependency="postgres"`
  - cache 使用 `dependency="cache"`
  - MCP 使用 `dependency="mcp"`
  - vector / audit / notifications 与 `/health` key 同名

## 运行时行为

- `HealthService.getHealth()` 有 `10s` cache，并对并发请求做 in-flight 合并。
- `McpGatewayService.checkAvailableTools()` 同样有 health cache；`/health` 的 `mcp` 状态默认读取该快照，而不是每次全量重连。
- `vector_health` probe 是同步 probe，超时固定走 `8_000ms`。

## 已知限制

- `apps/web/lib/system-health.ts` 仍兼容旧状态词和旧 signal；这只是前端兜底逻辑，不应在文档里继续把 BFF 当前 contract 写成 `ok/unavailable` 或 `boolean`-only 模式。
- `/health` payload 的组件 key 是 `db`，但 Prometheus dependency label 用的是 `postgres`；告警与面板不要把这两个名字当成完全同一字段。
