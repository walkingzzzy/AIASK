# 常见问题 FAQ

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-tdxpy.html
> 抓取时间: 2026-02-03

## Q: 运行的python文件可不可以随便放，不一定在PYPlugins\user目录下？

**A:** 可以。在import tqcenter前添加通达信安装目录\PYPlugins\user这个绝对路径。

```python
import sys
sys.path.append('C:/new_tdx64/PYPlugins/user')
from tqcenter import tq
tq.initialize(__file__)
```

## Q: 出现类似报错怎么办？

```
FileNotFoundError: Could not find module 'F:\tdx\new_tdx_600\PYPlugins\TPythClient.dll' (or one of its dependencies). Try using the full path with constructor syntax.
```

**A:** 这通常是TPythClient.dll缺少依赖库导致的，请检查TPythClient.dll同目录下（../PYPlugins/）是否有tdxrpcx64.dll，通常是杀毒软件误杀此dll导致，需要重装或给予白名单确保tdxrpcx64.dll不会被杀毒软件误杀。

## 其他常见问题

### 1. 如何确保通达信客户端已启动？

在运行TdxQuant策略之前，必须先启动通达信金融终端或专业研究版，并确保已登录。

### 2. 数据获取为空怎么办？

- 检查是否已在客户端下载了盘后数据
- 确认股票代码格式正确（如：600519.SH、000001.SZ）
- 检查时间范围是否有效

### 3. 如何获取更多历史数据？

在通达信客户端中，通过"系统"->"盘后数据下载"功能下载更多历史数据。

