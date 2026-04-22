# Production-Gap Readiness

围绕当前 worktree 最近收口的三块内容，这份清单把代码入口、断言、监控文件和前端消费面串成一条可执行证据链。

## 统一入口

- 静态 + 断言：`npm run verify:production-gap-readiness`
- 再加在线探测：`node scripts/production-gap-readiness.mjs --with-tests --live`
- 只跑监控探测：`npm run verify:monitoring`

## 1. observability / health

已接线

- BFF 健康与 metrics：`/api/health`、`/api/health/live`、`/api/health/startup`、`/api/health/ready`、`/api/metrics`
- 指标记录点：HTTP interceptor、DB query metrics、MCP call metrics、dependency gauge
- 前端状态：`apps/web/components/home/SystemStatus.tsx`、`apps/web/app/admin/page.tsx`、`apps/web/app/api/bff-availability/route.ts`
- 监控 profile：`monitoring/prometheus.yml`、`monitoring/alertmanager.yml`、`monitoring/otel-collector-config.yml`、`monitoring/postgres-exporter-queries.yml`、`monitoring/blackbox.yml`、`monitoring/alerts/bff-readiness.rules.yml`

已有自动断言

- `apps/bff/test/health.service.test.mjs`
- `apps/bff/test/production-gap.readiness.test.mjs`
- `scripts/monitoring-smoke.mjs`

仍属 gap

- 首页和管理页目前没有专门绑定 health 状态的浏览器级 smoke；现在的前端证据仍以代码接线和 API 探测为主。
- 在线探测必须依赖本机 BFF 与 monitoring profile 已启动；否则 readiness 只会给出“未取得运行证据”，不会伪装成已验证。

## 2. mcp-jobs / mcp-gateway transport

已接线

- BFF transport/runtime：`apps/bff/src/mcp-gateway/mcp-gateway.service.ts`
- degraded/unavailable 合同：`apps/bff/src/mcp-gateway/mcp-transport.contract.ts`、`apps/bff/src/common/acceptance.ts`、`apps/bff/src/common/degrade.interceptor.ts`
- 异步 job 入口：`apps/bff/src/mcp-jobs/mcp-jobs.controller.ts`、`apps/bff/src/mcp-jobs/mcp-jobs.service.ts`
- 前端状态：home/admin health 快照，以及 `apps/web/app/admin/tools/page.tsx` 的工具统计页

已有自动断言

- `apps/bff/test/mcp-jobs.service.test.mjs`
- `apps/bff/test/mcp-transport.contracts.test.mjs`
- `apps/bff/test/production-gap.readiness.test.mjs`

仍属 gap

- `/api/mcp/jobs` 目前没有专门的前端提交/轮询页面，真实 job 流程仍以 API 为主。
- readiness 在线探测只能安全验证 `/api/health/mcp`；不会自动发起需要管理员鉴权的 job create/poll 流程。

## 3. execution-audit acceptance -> replay -> acceptance

已接线

- BFF route：`apps/bff/src/strategy/strategy-incubation.controller.ts`
- 前端状态：`apps/web/app/strategy-market/hooks/use-strategy-detail-page.ts` 与 `apps/web/app/strategy-market/components/factory-review-panel/summary-section.tsx`
- 脚本链路：
  - `scripts/strategy-execution-audit-acceptance.py`
  - `scripts/strategy-incubation-history-replay.py`

已有自动断言

- `packages/akshare-mcp/tests/test_execution_audit_replay_contract.py`
- `packages/strategy-factory/tests/test_execution_audit_gate_taxonomy.py`
- readiness 脚本会额外校验两个 CLI 能否正常解析 `--help`

仍属 gap

- `strategy-incubation-history-replay.py` 会写库，且 `--reset-state` 会清理既有 runtime state，所以默认 readiness 不会自动执行真实 replay。
- 真正的“acceptance -> replay -> acceptance”运行证据仍需人工在目标库上执行，并保留报告产物。

推荐手动链路

1. `npm run verify:execution-audit-acceptance`
2. 取 acceptance JSON 报告中的 sample-gap 策略，执行 replay：
   `npm run replay:incubation-history-samples -- --from-acceptance-report <report.json> --sample-gap-only`
3. 再次执行 acceptance，确认 blockers 是否收敛

## 当前分类口径

- `present + passed`：代码与断言都已覆盖
- `present + not_run`：代码已接线，但本次没有取得在线证据
- `warn/manual`：路径成立，但仍需人工运行、鉴权或真实库证据
- `fail`：当前 worktree 缺文件、缺断言或命令执行失败
