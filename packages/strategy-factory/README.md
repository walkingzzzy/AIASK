# strategy-factory

独立策略工厂包。

当前状态：

- 新包已经承载策略工厂的主要实现，包含 `domain / application / infrastructure / api` 分层。
- 旧路径 `akshare_mcp.services.strategy_factory` 已退化为兼容层，继续保留历史 import 与 patch surface。
- MCP 侧调用方已经优先通过 `strategy_factory` 公共入口访问调度器、门禁与共享 helper。

迁移目标已经基本完成，当前保留 compat 层主要是为了：

- 兼容历史导入路径；
- 保持 monkeypatch/patch 测试面稳定；
- 为后续 1~2 个迭代周期的观测与裁剪留缓冲。
