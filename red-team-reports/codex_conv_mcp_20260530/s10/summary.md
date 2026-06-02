# N10 · 期权希腊字母链 + 可转债 + 新股

- **判定**: ✅ 通过 (Pass=18 / Degraded=9 / Fail-graceful=3 / Fail-schema=1)
- **真实工具调用数**: 31

## 核心成果

1. **BSM 期权引擎（亮点）**：希腊字母计算质量极高——
   - put-call delta 互补正确（call 0.5448 / put -0.4552，和为约 0.09≈e^{-rT}）
   - IV 反算自洽（price 0.1288 → 19.99%，逼近输入 σ=20%；price 0.5 → 82.83%）
   - Greeks 随 T/σ/moneyness 变化方向全部合理（σ 升 gamma 降、T 升 vega 升）
2. **定价分解**：`calculate_price` 输出 intrinsic/time_value/moneyness（S3.1/K3 → ITM, intrinsic 0.1, time 0.101）。
3. **可转债护栏**：`get_cb_info` tdx_only_mode 正确显式空 + 原因。
4. **新股申购**：返回申购代码/日期/价格/发行 PE（301669 价 7.08 PE 29.97）。

## ⚠ 关键发现

- **F-N10-1 [MEDIUM]**：`calculate_greeks(K=-1)` 对非法行权价**输出 `'nan'`**（option_price 与全部 greeks 均 nan），但 `success=true` 且 interpretation 照常生成"期权价格变动 nan 元"的荒谬解读。BSM 缺少输入合理性校验（K>0/S>0）。
- **F-N10-2 [LOW]**：期权链/波动率微笑因 sina 期权源不可用恒空（options=[]/curve=[]），显式 degraded；纯计算功能不受影响。

## 评价

期权的**纯数学计算引擎（BSM 定价/Greeks/IV）是本系统质量最高的模块之一**，多组参数交叉验证全部自洽。唯一缺陷是非法输入（K≤0）应拒绝而非返回 nan + success=true。实时期权链受环境数据源限制不可用，属预期。
