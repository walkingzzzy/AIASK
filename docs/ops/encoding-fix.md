# Kiro / Windows 终端 UTF-8 永久修复

> 创建于 2026-05-27 — 修复 Kiro 终端长命令乱码、PSReadLine `SetCursorPosition: top=-3` 异常、Python 子进程 GBK 输出等系列问题。

## 一、为什么需要这个修复

### 现象

1. Kiro 终端跑长命令(包含中文/拼接多行)时,PSReadLine 抛 `ArgumentOutOfRangeException: top=-3` 异常,命令被截断到一半执行。
2. Python 子进程 stdout 中文乱码(`鈺愨晲` 这类双字节解码错误)。
3. AKShare 数据返回的中文股票名称全部变成 `?` 或 `\xb0\xa1` 形式。
4. PowerShell 管道 / `Out-File` 写入的 UTF-8 文本被读回时是 GBK。

### 根因 (在 zh-CN locale 的 Windows 10/11 上 PS 5.1)

| 层 | 默认值 | 应该是 |
|---|---|---|
| 控制台 codepage (`chcp`) | 65001 (UTF-8) | 65001 ✓ 已对 |
| `[Console]::OutputEncoding` | gb2312 | UTF-8 ❌ |
| `$OutputEncoding` | gb2312 | UTF-8 ❌ |
| `PYTHONUTF8` 环境变量 | (空) | `1` ❌ |
| `PYTHONIOENCODING` | (空) | `utf-8` ❌ |
| PSReadLine 版本 | 2.0.0 (随 PS 5.1) | 2.2.6+ 有 SetCursorPosition fix |

只设 `chcp 65001` **不够** — .NET console encoding 是单独一层,从 system locale 读,不跟 codepage。

## 二、安装

### 步骤 1: 跑一次仓库内的安装脚本(管理员权限**不需要**)

```powershell
PS C:\Users\walking\Desktop\aiask> .\scripts\encoding\install.ps1
```

它会做这些事:
- 创建 `C:\Users\<you>\Documents\WindowsPowerShell\profile.ps1` (如不存在)
- 把 `scripts/encoding/profile.ps1` 的内容嵌入到 `$PROFILE.CurrentUserAllHosts`
- 设置 user-level 环境变量: `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`
- 在当前 session 里立即应用,打印 self-check 结果

脚本是 idempotent — 重复跑安全,会替换已有的 managed block 而不是叠加。

### 步骤 2: 重启 Kiro

最简单的 — Kiro 完全退出后重开。新建终端时会:

1. 走 `.vscode/settings.json` 里 `Kiro PowerShell (UTF-8)` 这个 profile
2. 启动参数 `-File scripts\encoding\profile.ps1` 强制初始化 UTF-8
3. `terminal.integrated.env.windows` 注入 `PYTHONUTF8=1` 等环境变量

## 三、验证

新开终端后跑:

```powershell
[Console]::OutputEncoding.WebName     # 应该是 utf-8 (不是 gb2312)
[Console]::InputEncoding.WebName       # 应该是 utf-8
$OutputEncoding.WebName                # 应该是 utf-8
$env:PYTHONUTF8                        # 应该是 1
$env:KIRO_TERMINAL_UTF8_READY          # 应该是 1 (profile 加载完才有)
chcp                                    # 应该是 65001
```

中文 sanity check:

```powershell
"中文测试 — 涨停板 / 因子挖掘 / 孵化工厂"
python -c "print('中文', '股票', '北向资金')"
```

两条都应该清晰显示中文,没有 mojibake。

## 四、组件清单

| 文件 | 作用 |
|---|---|
| `scripts/encoding/profile.ps1` | 真正的 UTF-8 初始化代码,Kiro 终端启动时通过 `-File` 加载 |
| `scripts/encoding/install.ps1` | 把 profile.ps1 安装到用户级 PowerShell profile |
| `.vscode/settings.json` | Kiro/VS Code 终端配置:默认 profile + 环境变量注入 |
| `docs/ops/encoding-fix.md` | 本文档 |

## 五、卸载

```powershell
# 1. 编辑用户 profile,删除 "# === Kiro UTF-8 profile ===" 到 "# === end Kiro UTF-8 profile ===" 之间的整个块
notepad $PROFILE.CurrentUserAllHosts

# 2. 移除环境变量
[Environment]::SetEnvironmentVariable('PYTHONUTF8', $null, 'User')
[Environment]::SetEnvironmentVariable('PYTHONIOENCODING', $null, 'User')

# 3. 还原 .vscode/settings.json — 保留你需要的 keys,删除 terminal.integrated.* 我们加的部分
```

## 六、已知限制

- 修复**只对新开的终端生效** — 当前已开着的终端要么 `. $PROFILE` 重新加载,要么关闭重开
- 第三方扩展如果在 PS 启动早期写控制台,可能在 profile 加载前就触发 PSReadLine 异常 — 暂无法绕过
- 如果你以前自己改过 `$PROFILE.CurrentUserCurrentHost`(Microsoft.PowerShell_profile.ps1),它会比 `CurrentUserAllHosts` 更晚加载,可能覆盖我们的设置。检查方法: `cat $PROFILE.CurrentUserCurrentHost`。
- 长期建议安装 PowerShell 7+ (`winget install Microsoft.PowerShell`),其 PSReadLine 是 2.2.6+,SetCursorPosition bug 早已修复

## 七、技术细节(供未来排查)

### 为什么 PSReadLine 会崩

PSReadLine 2.0.0 用 `[Console]::SetCursorPosition(left, top)` 渲染。当你输入跨多行的命令时,它根据 `[Console]::WindowHeight` 和当前光标 Y 算 `top`,但**中文字符宽度计算是基于 [Console]::OutputEncoding 的 byte width**。如果 OutputEncoding 是 gb2312,一个中文字符算 2 bytes; 但实际 UTF-8 写出去是 3 bytes,屏幕上的 cell width 又是 2 — 三套数字不一致,top 算到 -3,直接抛 ArgumentOutOfRangeException。

设 `[Console]::OutputEncoding = UTF8` 后,PSReadLine 用 UTF-8 byte length 一致地推断 cell width,top 不会再为负。

### 为什么 `PYTHONUTF8=1` 必要

Python 3.7+ 的 "UTF-8 mode" 开关。开启后:
- `sys.stdout.encoding` = `utf-8`(否则在 Windows 上是 cp936)
- `open()` 默认 encoding = `utf-8`(否则是 locale.getencoding())
- `subprocess.Popen(text=True)` 默认 encoding = `utf-8`

仅设 `PYTHONIOENCODING` 只影响 stdin/stdout/stderr,不影响 `open()` 文件读写,不够用。

### 为什么不直接改系统区域设置

控制面板里有个"使用 Unicode UTF-8 提供全球语言支持"勾选项。开启后:
- 所有 cmd / PowerShell 默认 UTF-8 ✓
- 但同时**会破坏部分老国产软件的中文显示**(因为它们用 ANSI API 假定 GBK)
- AKShare 我们用没问题,但一些金融客户端 / WeChat / 同花顺会出问题

所以选择"workspace 内修复"路径,不动系统全局设置。
