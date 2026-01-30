#!/usr/bin/env python
"""
AKShare MCP Server 启动脚本
"""

import sys
import os

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    from akshare_mcp.server import main
    
    print("=" * 60)
    print("AKShare MCP Server v2")
    print("=" * 60)
    print(f"Python版本: {sys.version}")
    print(f"工作目录: {os.getcwd()}")
    print("=" * 60)
    print("\n启动服务器...\n")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n服务器已停止")
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)
