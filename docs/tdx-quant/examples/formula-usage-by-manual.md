# 手册中的公式用法说明

根据 `docs/tdx-quant/api/formula/` 与安装/FAQ 整理，用于在**通达信客户端环境**下确认公式接口是否可用。

---

## 1. 手册要求的运行环境

- **先启动通达信**：运行任何 TdxQuant 策略前，必须先启动通达信金融终端或专业研究版，并**登录**。
- **再运行 Python**：
  - **方式 A**：在 VSCode 中**打开通达信安装目录下的 `PYPlugins/user` 文件夹**，在该工作区下运行 `.py` 文件（此时当前目录和模块搜索路径即该目录）。
  - **方式 B**：脚本可放在任意位置，在 `import tqcenter` 之前将通达信 `PYPlugins/user` 加入路径：
    ```python
    import sys
    sys.path.append('通达信安装目录/PYPlugins/user')  # 例如 C:/new_tdx64/PYPlugins/user
    from tqcenter import tq
    tq.initialize(__file__)
    ```
- **数据**：在客户端中通过「系统 -> 盘后数据下载」下载日线/分钟线，避免取数为空。

---

## 2. 公式调用流程（手册顺序）

调用公式前须先**设置公式数据信息**，再调用具体公式。

### 2.1 设置数据信息（必须第一步）

使用 `formula_set_data_info` 指定要计算的股票、周期、K 线数量、复权方式：

```python
from tqcenter import tq
tq.initialize(__file__)

formula_set_res = tq.formula_set_data_info(
    stock_code='688318.SH',   # 股票代码，带后缀 .SH / .SZ
    stock_period='1d',        # K线周期：1m/5m/15m/30m/1h/1d/1w/1M
    count=100,                # 截取最近 count 根K线；-1 表示全部
    dividend_type=1           # 0 不复权 1 前复权 2 后复权
)
# 成功返回：{'ErrorId': '0', 'Msg': '向通达信公式系统设置数据信息成功！', 'run_id': '1'}
```

### 2.2 技术指标公式 formula_zb

例如 MACD、KDJ、RSI、BOLL：

```python
# 接上面 formula_set_data_info 之后
formula_zb_result = tq.formula_zb(formula_name='MACD', formula_arg='12,26,9')
# 返回：{'Data': {'DEA': [...], 'DIF': [...], 'MACD': [...]}, 'ErrorId': '0'}
```

### 2.3 条件选股公式 formula_xg

```python
formula_xg_result = tq.formula_xg(formula_name='UPN', formula_arg='3')
# 返回：{'Data': {'UP3': [None, None, 0.0, ...]}, 'ErrorId': '0'}
```

### 2.4 专家系统公式 formula_exp

```python
formula_exp_result = tq.formula_exp(formula_name='CCI', formula_arg='12')
# 返回：{'Data': {'ENTERLONG': [...], 'EXITLONG': [...]}, 'ErrorId': '0'}
```

### 2.5 获取公式用 K 线 formula_get_data

在 `formula_set_data_info` 之后，可获取当前公式设置对应的 K 线数据（不调用 formula_zb/xg/exp 也可用）：

```python
tq.formula_set_data_info(stock_code='688318.SH', stock_period='1d', count=5, dividend_type=1)
formula_kline = tq.formula_get_data()
# 返回：{'Code': '688318.SH', 'Data': [{'Date': '...', 'Open': ..., 'High', 'Low', 'Close', 'Volume', 'Amount'}, ...], 'ErrorId': '0'}
```

### 2.6 格式化 K 线 formula_format_data

将 `get_market_data` 得到的 K 线格式化为公式可用的格式：

```python
raw_md = tq.get_market_data(stock_list=['688318.SH'], count=5, period='1d')
formatted = tq.formula_format_data(raw_md)
```

---

## 3. 在「客户端环境」内再测一次公式是否挂载

手册要求：**先启动并登录通达信**，再在 **通达信自带的 Python 运行环境**（即以 `PYPlugins/user` 为工作目录）下运行脚本。公式接口由通达信在客户端内挂载到 `tq` 上，只有在该环境下才能看到 `formula_set_data_info`、`formula_zb` 等。

### 3.1 推荐步骤（用自带脚本检测）

1. **先启动通达信**：打开通达信金融终端或专业研究版并登录。
2. **用通达信 user 目录做工作区**：在 VSCode 中「文件 -> 打开文件夹」，选择 **通达信安装目录\PYPlugins\user**（不要打开项目根目录）。
3. **复制检测脚本**：将项目中的  
   `docs/tdx-quant/examples/run_formula_check_in_tdx_user.py`  
   复制到上述 `PYPlugins\user` 目录下（或在该目录下新建同名文件粘贴内容）。
4. **在 VSCode 中运行**：在 `PYPlugins\user` 工作区下打开该脚本，直接运行（F5 或「运行 Python 文件」）。
5. **看输出结论**：
   - 若出现「tq 上含 formula 的成员: [..., formula_set_data_info, formula_zb, ...]」且 **[结论] 当前环境已挂载公式接口**，说明在客户端内公式接口可用。
   - 若为「(无)」或 **[结论] 当前环境未挂载公式接口**，说明本机 tqcenter/通达信版本未在该环境下提供公式接口，或未在 user 目录下运行。

### 3.2 手册中的公式用法小结

- 使用公式前必须先 **设置数据信息**：`tq.formula_set_data_info(stock_code, stock_period, count, dividend_type)`。
- 技术指标用 **formula_zb**（如 MACD、KDJ、RSI、BOLL），条件选股用 **formula_xg**，专家系统用 **formula_exp**。
- 获取公式用 K 线：先 `formula_set_data_info`，再 `tq.formula_get_data()`。
- 详细 API 见 `docs/tdx-quant/api/formula/` 下各页。

---

## 4. 参考：完整示例（手册 formula_zb 页）

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

# 技术指标公式 MACD
formula_zb = tq.formula_zb(formula_name='MACD', formula_arg='12,26,9')
print(formula_zb)

# 条件选股公式 UPN
formula_xg = tq.formula_xg(formula_name='UPN', formula_arg='3')
print(formula_xg)

# 专家系统公式 CCI
formula_exp = tq.formula_exp(formula_name='CCI', formula_arg='12')
print(formula_exp)
```

---

## 5. 常见问题（摘自 FAQ）

- **必须先启动通达信并登录**，再运行策略。
- 若报错找不到 `TPythClient.dll` 或依赖：检查 `PYPlugins` 目录下是否有 `tdxrpcx64.dll`，是否被杀毒软件拦截。
- 数据为空：检查是否在客户端做了「盘后数据下载」、代码与时间范围是否正确。
