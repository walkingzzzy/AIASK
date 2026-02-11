# 安装Python及VSCode等开发环境

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00970eq1rtc.html
> 抓取时间: 2026-02-03

## 1. 安装 Python 环境

安装Python：建议使用Python3.7及以上版本

### 1.1 下载地址

[Python官网](https://www.python.org/)

**特别提示**：安装时候务必勾选 `Add Python to PATH`（将Python添加到环境变量）

## 2. 安装IDE 建议使用VSCode或PyCharm

### 2.1 下载地址

[Visual Studio Code官网](https://code.visualstudio.com/)

### 2.2 安装 Python 插件（Extensions）

VSCode安装好后，在VSCode终端-扩展-输入下文，分别添加相关扩展：

- 简体中文
- python

### 2.3 选择Python解释器

选择python3.13安装路径的exe：

1. 使用 `Ctrl+Shift+P` 快捷键打开 command palette 窗口
2. 输入关键字 `python select` 并找到 `Python: Select Interpreter` 一项
3. 点击该项并在随后弹出的 Python 解释器列表中选择目标解释器

### 2.4 安装常用库

在VSCode终端-扩展-分别输入下文，常用库建议安装：

```bash
pip install numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install pandas -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install backtrader -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install vectorbt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2.5 调试运行

在需要的文件上打上断点，然后 debug（按F5）运行。

显示选择调试配置 - "Python文件"，调试打开的 Python 文件。可以查看变量等等。

## 3. 用户py的文件位置

在策略管理器界面，点击[文件位置]。

- 用户的py文件一般在客户端 `PYPlugins` 下面的 `user` 目录下面
- py运行过程的生成的文件一般在 `PYPlugins` 下面的 `data` 和 `file` 目录下

