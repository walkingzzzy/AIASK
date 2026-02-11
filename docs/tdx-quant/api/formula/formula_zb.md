# 调用通达信公式进行计算 formula_zb

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3huq37005ro.html
> 抓取时间: 2026-02-03

## 函数说明

调用通达信三种类型的公式进行计算。

```python
# 调用技术指标公式
def formula_zb(formula_name: str = '', formula_arg: str = '')

# 调用条件选股公式
def formula_xg(formula_name: str = '', formula_arg: str = '')

# 调用专家系统公式
def formula_exp(formula_name: str = '', formula_arg: str = '')
```

## 输入参数

| 参数 | 是否必选 | 参数类型 | 参数说明 |
|------|----------|----------|----------|
| formula_name | Y | str | 公式名称 |
| formula_arg | Y | str | 公式参数 |

**说明**：
- 目前支持调用技术指标公式、条件选股公式和专家系统公式
- 调用公式时请注意对应不同的调用接口和公式名
- `formula_arg` 格式为 `"arg1,arg2,arg3,arg4,arg5"`，arg须为纯数字字符串，最多支持16个

## 接口使用

```python
from tqcenter import tq

tq.initialize(__file__)

# 先设置数据信息
formula_set_res = tq.formula_set_data_info(
    stock_code='688318.SH',
    stock_period='1d',
    count=20,
    dividend_type=1
)

# 技术指标公式MACD
formula_zb = tq.formula_zb(formula_name='MACD', formula_arg='12,26,9')
print(formula_zb)

# 条件选股公式UPN
formula_xg = tq.formula_xg(formula_name='UPN', formula_arg='3')
print(formula_xg)

# 专家系统公式CCI
formula_exp = tq.formula_exp(formula_name='CCI', formula_arg='12')
print(formula_exp)
```

## 返回数据样本

```python
# MACD结果
{'Data': {'DEA': [0.0, 0.01, -0.01, ...], 
          'DIF': [0.0, 0.05, -0.07, ...], 
          'MACD': [0.0, 0.07, -0.13, ...]}, 
 'ErrorId': '0'}

# 条件选股结果
{'Data': {'UP3': [None, None, 0.0, ...]}, 'ErrorId': '0'}

# 专家系统结果
{'Data': {'ENTERLONG': [...], 'EXITLONG': [...]}, 'ErrorId': '0'}
```

