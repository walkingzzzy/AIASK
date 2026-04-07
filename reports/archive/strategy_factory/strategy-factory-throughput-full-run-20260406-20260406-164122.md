# 策略工厂吞吐验证报告

- 生成时间: 2026-04-06T16:41:21.889891+08:00
- 标签: full-run-20260406
- 运行轮数: 1

## 关键指标

- 累计候选数: 139
- 累计 Gate-3 通过数: 2
- 总 wall time: 524.3042 秒
- 总 run elapsed: 491.6 秒
- 计算吞吐 candidates/hour: 1017.9007
- 计算吞吐 gate3/hour: 14.6461
- 盘中调度折算 candidates/hour: 1668.0
- 盘中调度折算 gate3/hour: 24.0
- 目标达成: 是

## 配置

- event runtime mode: readonly
- factor auto refresh: True
- market interval sec: 300
- off-hours interval sec: 1800
- target candidates/hour: 100
- target gate3/hour: 10

## 单轮摘要

| run_id | status | elapsed_seconds | candidates_spawned | gate_3_passed | readiness_score |
| --- | --- | ---: | ---: | ---: | ---: |
| factory_run_1775464357_84ead636 | partial | 491.6 | 139 | 2 | 0.81 |
