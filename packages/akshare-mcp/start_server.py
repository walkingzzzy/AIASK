#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AKShare MCP Server 启动脚本

建议以 UTF-8 模式启动以避免编码错误，例如：
  python -X utf8 start_server.py
或在环境变量中设置 PYTHONUTF8=1 后启动。
"""
import sys
import os
from pathlib import Path

# 在导入 akshare_mcp 之前加载 .env，使 get_db() 等使用实际数据库配置
# 注意：如果环境变量已设置（来自 MCP 配置），则不覆盖，确保 MCP 配置优先级更高
_env_path = Path(__file__).resolve().parent / '.env'
if _env_path.exists():
    try:
        _env_content = _env_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        _env_content = ""
    for line in _env_content.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            k, v = key.strip(), value.strip()
            # 如果环境变量已设置（来自 MCP 配置），则不覆盖
            if k not in os.environ:
                os.environ[k] = v

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    import logging
    import sys as _sys
    
    # MCP stdio 协议要求 stdout 只传输协议数据，启动日志走 stderr
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=_sys.stderr,
    )
    _log = logging.getLogger("start_server")
    
    from akshare_mcp.server import main
    
    _log.info("=" * 60)
    _log.info("AKShare MCP Server v2")
    _log.info("=" * 60)
    _log.info("Python版本: %s", sys.version)
    _log.info("工作目录: %s", os.getcwd())
    _log.info("=" * 60)
    _log.info("启动服务器...")
    
    try:
        main()
    except KeyboardInterrupt:
        _log.info("服务器已停止")
    except Exception as e:
        _log.error("错误: %s", e)
        sys.exit(1)
