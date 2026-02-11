# 安装通达信终端并获取数据

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00kk3jsibbc.html
> 抓取时间: 2026-02-03

## 1. 安装通达信终端

### 1.1 下载地址

持续更新中

- [通达信金融终端内测版](https://www.tdx.com.cn/)
- 或正式版：下载通达信专业研究版 https://www.tdx.com.cn/soft.html

### 1.2 登录通达信金融终端

启动通达信金融终端并登录账户。

### 1.3 系统-盘后数据下载

进行日线和分钟线等数据下载，确保本地有足够的历史数据。

## 2. 使用VSCode集成环境

### 2.1 使用VSCode运行py

#### 2.1.1 打开py文件

在 VS Code 中点击打开一个本地文件夹，"文件"->"打开文件夹"。

#### 2.1.2 运行py文件

在VSCode中打开通达信终端目录 `.../PYPlugins/user` 文件夹，运行 `tdxdata_test.py` 文件。

**注意**：客户端安装目录下面的 `.../PYPlugins/user` 文件夹中的 `tqcenter.py` 是最主要的TQData支撑文件，请勿修改或删除，否则需要重新下载。

### 2.2 使用VSCode编辑新文件

#### 2.2.1 新建py文件

在打开的文件夹中鼠标右键创建新的 `.py` python 文件，文件名例如 `tdxdemo.py`。

#### 2.2.2 编辑py文件

```python
# 使用tqcenter的API函数查看平安银行日线数据示例
from tqcenter import tq

# 初始化
tq.initialize(__file__)  # 所有策略连接通达信客户端都必须调用此函数进行初始化

# 获取平安银行日线前复权收盘数据
df = tq.get_market_data(
    field_list=['Close'],
    stock_list=["000001.SZ"],
    start_time='20251219',
    end_time='20251225',
    dividend_type='front',
    period='1d',
)
print(df)
```

运行结果将显示平安银行的日线收盘价数据。

