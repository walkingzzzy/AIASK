# AKShare MCP 服务配置指南

本文档提供在 Augment/Cursor 中配置 AKShare MCP 服务的详细说明。

---

## 📍 配置文件位置

### Cursor
配置文件路径：`.cursor/mcp.json` 或 `.cursor/settings/mcp.json`

### Augment
配置文件路径：`.augment/mcp.json` 或 `.kiro/settings/mcp.json`

---

## 🚀 推荐配置方式

### 方式1：使用 uv 运行（推荐）⭐

```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
        "python",
        "start_server.py"
      ],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src"
      },
      "disabled": false
    }
  }
}
```

**优点**：
- ✅ uv 自动管理虚拟环境和依赖
- ✅ 无需手动激活虚拟环境
- ✅ 自动读取 `.env` 文件

---

### 方式2：使用 Python 直接运行

```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "python",
      "args": ["start_server.py"],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src"
      },
      "disabled": false
    }
  }
}
```

**注意**：需要先安装依赖：
```bash
cd c:\Users\1\Desktop\股票\packages\akshare-mcp
pip install -r requirements.txt
```

---

### 方式3：使用虚拟环境的 Python

```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\.venv\\Scripts\\python.exe",
      "args": ["start_server.py"],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src"
      },
      "disabled": false
    }
  }
}
```

**优点**：
- ✅ 使用项目专用的虚拟环境
- ✅ 依赖隔离，不影响系统Python

**前提**：需要先创建虚拟环境：
```bash
cd c:\Users\1\Desktop\股票\packages\akshare-mcp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

### 方式4：带完整环境变量配置（推荐用于数据库连接问题）

```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
        "python",
        "start_server.py"
      ],
      "cwd": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp",
      "env": {
        "PYTHONPATH": "c:\\Users\\1\\Desktop\\股票\\packages\\akshare-mcp\\src",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "stockdb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "your_password_here",
        "TUSHARE_TOKEN": "your_tushare_token_here"
      },
      "disabled": false
    }
  }
}
```

**优点**：
- ✅ 显式指定所有环境变量
- ✅ 解决 `.env` 文件读取问题
- ✅ 适合数据库连接失败的情况

**注意**：请替换以下内容：
- `your_password_here` → 你的数据库密码
- `your_tushare_token_here` → 你的Tushare Token（可选）

---

## 🔧 配置参数说明

| 参数 | 说明 | 必需 |
|------|------|------|
| `command` | 启动命令（uv/python/绝对路径） | ✅ |
| `args` | 命令参数 | ✅ |
| `cwd` | 工作目录（项目根目录） | ✅ |
| `env` | 环境变量 | 可选 |
| `disabled` | 是否禁用服务 | 可选 |

---

## 📝 Linux/Mac 配置示例

### 使用 uv（推荐）
```json
{
  "mcpServers": {
    "akshare-stock": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/username/Desktop/股票/packages/akshare-mcp",
        "python",
        "start_server.py"
      ],
      "cwd": "/Users/username/Desktop/股票/packages/akshare-mcp",
      "disabled": false
    }
  }
}
```


