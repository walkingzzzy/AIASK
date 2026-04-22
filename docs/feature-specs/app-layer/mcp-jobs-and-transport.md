# App Layer：MCP Jobs / Transport 契约

## 覆盖范围

- 本文覆盖：
  - `apps/bff/src/mcp-gateway/mcp-gateway.service.ts::McpGatewayService`
  - `apps/bff/src/mcp-gateway/mcp-transport.contract.ts`
  - `apps/bff/src/common/degrade.interceptor.ts::DegradeInterceptor`
  - `apps/bff/src/mcp-jobs/mcp-jobs.controller.ts::McpJobsController`
  - `apps/bff/src/mcp-jobs/mcp-jobs.service.ts::McpJobsService`
  - `packages/shared-types/src/common.ts`

## 事实来源

- 源码：
  - `apps/bff/src/mcp-gateway/mcp-gateway.service.ts`
  - `apps/bff/src/mcp-gateway/mcp-transport.contract.ts`
  - `apps/bff/src/common/degrade.interceptor.ts`
  - `apps/bff/src/mcp-jobs/mcp-jobs.controller.ts`
  - `apps/bff/src/mcp-jobs/mcp-jobs.dto.ts`
  - `apps/bff/src/mcp-jobs/mcp-jobs.service.ts`
  - `packages/shared-types/src/common.ts`
- 测试：
  - `apps/bff/test/mcp-transport.contracts.test.mjs`
  - `apps/bff/test/mcp-jobs.service.test.mjs`

## 取证方式

- `rg -n "McpTransportSnapshot|McpToolTransportMeta|McpTransportFailureDetail" packages/shared-types/src apps/bff/src/mcp-gateway`
- `rg -n "ALLOWED_JOB_TRANSITIONS|MCP_JOB_|idempotency|poll_path|meta:" apps/bff/src/mcp-jobs`
- `rg -n "DEGRADED_ROUTE_PREFIXES|acceptanceStatus|buildMcpTransportFailureDetail" apps/bff/src/common/degrade.interceptor.ts`

## 不覆盖范围

- 不展开 MCP manager action 的业务语义。
- 不把 transport test fixture 里的示例路径写成运行时常量。

## 共享 transport contract

`packages/shared-types/src/common.ts` 当前锁定的 `McpTransportSnapshot` 字段是：

- `requested_transport: "stdio" | "streamable-http" | "sse" | "auto"`
- `active_transport: "stdio" | "streamable-http" | "sse" | "none"`
- `degraded: boolean`
- `fallback_reason: string | null`
- `source_chain: Array<"stdio" | "streamable-http" | "sse" | "none">`
- `endpoint: string | null`
- `last_error: string | null`

`apps/bff/src/mcp-gateway/mcp-transport.contract.ts::toMcpTransportSnapshot` 会把 BFF gateway 内部命名统一成上面的 snake_case shared contract。`withToolTransportMeta` 与 `buildMcpTransportFailureDetail` 也都复用同一份 `transport` 结构，测试已锁死这一点。

## transport 解析与降级语义

- `requested_transport`
  - 来自 `MCP_TRANSPORT`
  - 归一化后只保留 `stdio | streamable-http | sse | auto`
- `active_transport`
  - 来自实际成功建立的连接类型
  - 所有候选都失败时才会落到 `none`
- `degraded`
  - 发生 fallback、重试后换 transport、或保留了 `lastTransportError` 时为 `true`
- `fallback_reason`
  - 当前记录首个有效 fallback reason
  - 常见值如 `streamable_http_url_missing`、`streamable_http_connect_failed`、`sse_connect_failed`
- `source_chain`
  - 记录去重后的 transport 尝试顺序
  - 若 gateway 快照里没有链路信息，则回退为 `[active_transport]`
- `endpoint`
  - `stdio` 时为本地 `cwd`
  - `streamable-http` / `sse` 时为 URL
- `last_error`
  - 保存最近一次 transport 层错误字符串

## DegradeInterceptor 语义

- 只有上游抛出 `BadGatewayException` 时，`DegradeInterceptor` 才会改写为 transport-aware 的 `503`
- 非降级白名单路径：
  - 默认返回 `acceptanceStatus: "unavailable"`
  - 使用 `buildUnavailableException(...)`
- 降级白名单路径：
  - 当前前缀只包括 `/health`、`/observability`、`/admin`、`/audit`
  - 返回 `503` 且携带：
    - `degraded: true`
    - `acceptanceStatus: "degraded"`
    - `detail.transport: McpTransportSnapshot`
- 注意：
  - 当前对外 metrics surface 仍应按 `/api/metrics` 理解
  - 但 interceptor 的白名单前缀并不包含 `/api/metrics`，因此不要继续把 metrics surface 写成“天然属于 degraded route 白名单”

## MCP jobs HTTP contract

- `POST /api/mcp/jobs`
  - `@Roles("admin")`
  - body DTO：
    - `tool_name: string`，必填，trim 后不能为空
    - `arguments?: Record<string, unknown>`
    - `timeout_ms?: number`，范围 `1000..300000`
    - `idempotency_key?: string`，trim 后不能为空，长度上限 `256`
  - header 兼容：
    - `idempotency-key`
    - `x-idempotency-key`
  - 若 body 与 header 同时提供但不一致，直接返回 `400`
    - `code = "MCP_JOB_IDEMPOTENCY_KEY_MISMATCH"`
- `GET /api/mcp/jobs/:jobId`
  - `@Roles("admin")`
  - `jobId` 必须是 UUID

create 接口当前返回：

- `{ success: true, data, traceId }`
- `data` 是 `McpJobAcceptedResponse`
  - `accepted: true`
  - `deduplicated: boolean`
  - `job: McpJobRecord`

## MCP job record 字段

`McpJobRecord` 当前锁定字段为：

- `job_id`
- `status: "queued" | "running" | "succeeded" | "failed"`
- `submitted_at`
- `started_at?: string | null`
- `completed_at?: string | null`
- `poll_path`
- `idempotency_key`
- `target.kind`
- `target.name`
- `target.arguments`
- `target.timeout_ms`
- `result`
- `error`
- `error_code`
- `trace_id`
- `meta.transport`

其中 `poll_path` 当前固定为 BFF 相对路径 `/api/mcp/jobs/{job_id}`。

## MCP job 状态机

允许迁移由 `apps/bff/src/mcp-jobs/mcp-jobs.service.ts::ALLOWED_JOB_TRANSITIONS` 锁定：

- `queued -> queued | running | failed`
- `running -> running | succeeded | failed`
- `succeeded -> succeeded`
- `failed -> failed`

额外 shape invariant：

- 初次持久化时，状态必须是 `queued`
- `queued`
  - 不能带 `started_at`
  - 不能带 `completed_at`
- `running`
  - 必须带 `started_at`
  - 不能带 `completed_at`
- `succeeded | failed`
  - 必须保留 `started_at`
  - 必须带 `completed_at`

## 执行与去重语义

- 未显式传 `timeout_ms` 时，会走 `mcp.resolveToolTimeoutMs(...)`，即 gateway 默认超时。
- `idempotency_key` 命中时：
  - 直接回放已有 job
  - `deduplicated = true`
  - 保留第一次创建时的 `trace_id`
  - 后续请求不会覆盖已存在 job 的目标参数
- job 元数据里的 `meta.transport`：
  - 创建时写入一次
  - 每次状态推进时会再按当前 gateway 快照覆盖更新
- 默认 TTL：
  - `15 * 60` 秒
  - 最终仍可被 `cache.resolveTtl("mcp.jobs", ...)` 覆盖

## error_code 映射

- `MCP_JOB_TIMEOUT`
  - `McpGatewayTimeoutError(scope="tool_call")`
  - 或错误文案包含 `timed out after`
- `MCP_JOB_TRANSPORT_UNAVAILABLE`
  - `meta.transport.active_transport === "none"`
  - 或错误文案包含：
    - `unable to establish mcp connection`
    - `mcp not reachable`
    - `econnrefused`
    - `econnreset`
- `MCP_JOB_EXECUTION_FAILED`
  - 其他执行失败

## 已知限制

- `endpoint` 在 `stdio` transport 下是本机工作目录路径，只对同一台机器有意义；不要把它写成远端可访问地址。
- 测试 fixture 中常见的 `/tmp/akshare-mcp` 只是 contract fixture，不是当前实现承诺的固定 endpoint。
- `poll_path` 是 BFF 相对路径，不是带签名的外部回调 URL，也不携带 host 信息。
