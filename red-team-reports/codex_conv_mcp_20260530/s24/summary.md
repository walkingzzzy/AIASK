# N24 · 期权希腊字母链

**工具**: options_manager (calculate_greeks / calculate_price / implied_volatility / volatility_smirk / list)
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- calculate_greeks：call/put × 多 K(2.5/3/3.5/4) × 多 T(0.02/0.25/1) × 多 sigma(0/0.2/0.4/1.5) × r(-0.01/0.03)
- calculate_price：call/put、expiry_date 覆盖 T
- implied_volatility：往返一致性、不可能价格、多别名(market_price/price/option_price)
- volatility_smirk / list：真实链(周末空)
- 边界：负 K、sigma=0、T=0、缺 K、大写/未知 option_type、bogus action

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N24-1 | **high** | option_type 仅识别小写 `call`，`CALL`/`straddle`/拼写错误**静默当作 put**(返回看跌 delta)，期权方向静默误判 |
| F-N24-2 | medium | 负行权价 K=-3 → 全部 greeks/price 返回 `nan`，success=true 无校验 |
| F-N24-3 | medium | sigma=0→静默替换 25%；T=0→静默替换 0.25；缺 K→默认 3.5。边界/缺失值被默认值覆盖无提示 |
| F-N24-4 | low | list/volatility_smirk 空数据时顶层 envelope degraded 与内层不一致 |

## 正向能力
- **★★ Black-Scholes 解析完全正确**：call/put delta、gamma(ATM 峰值 + 临近到期 spike 至 4.03)、theta/vega/rho 全符合理论；put-call delta parity(call−put≈1.0)严格成立。
- **★ IV 反演高精度往返**：按 σ 定价后反解误差 <0.01%(σ=0.2→19.99%)，多档(0.2~1.5)均收敛。
- calculate_price 含 intrinsic/time_value/moneyness；expiry_date 可覆盖 T。
- 边界优雅：不可能价格→"未收敛"拒绝；非法 action→列出 6 合法项；负利率/150% 波动率合理接受。
- IV 参数多别名兼容；希腊字母中文解读清晰。

## standing caveat
周末非交易时段，真实期权链(list/volatility_smirk)上游 Sina 无数据返回空；Black-Scholes 解析计算不依赖实时数据可正常验证。
