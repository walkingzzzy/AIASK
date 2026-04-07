# 策略工厂吞吐验证报告

- 生成时间: 2026-04-06T17:34:23.496513+08:00
- 标签: full-run-20260406-no-json-fix
- 运行轮数: 1

## 关键指标

- 累计候选数: 139
- 累计 Gate-3 通过数: 2
- 总 wall time: 250.7091 秒
- 总 run elapsed: 236.3 秒
- 计算吞吐 candidates/hour: 2117.6471
- 计算吞吐 gate3/hour: 30.4697
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
| factory_run_1775467812_8cf619bc | success | 236.3 | 139 | 2 | 0.81 |
