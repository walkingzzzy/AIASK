# -*- coding: utf-8 -*-
"""
TdxQuant 前端交互测试脚本 (非交互式)

测试通达信客户端前端显示功能
"""

import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'akshare-mcp', 'src'))

# 手动加载 .env 文件
def load_env_file(env_path):
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'packages', 'akshare-mcp', '.env')
load_env_file(env_path)


def main():
    print("="*60)
    print("TdxQuant 前端交互测试 (自动运行)")
    print("="*60)
    
    from akshare_mcp.data_source import data_source
    from akshare_mcp.tools.tdx_integration import (
        create_watchlist, get_user_sectors, delete_watchlist,
        push_message, push_warn, add_stocks_to_watchlist
    )
    
    if not data_source.is_tdx_available():
        print("❌ TdxQuant 不可用")
        return
    
    tq = data_source.get_tdxquant()
    print("✅ TdxQuant 初始化成功\n")
    
    # ========== 测试1: 临时条件股 ==========
    print("="*60)
    print("测试1: 发送临时条件股到通达信前端")
    print("="*60)
    stocks = ["600519.SH", "000001.SZ", "300750.SZ", "601318.SH", "000858.SZ"]
    print(f"📤 发送股票: {stocks}")
    result = tq.send_user_block(block_code='', stocks=stocks, show=True)
    print(f"📥 结果: {result}")
    print("👀 请查看通达信客户端 - 应显示临时条件股\n")
    time.sleep(2)
    
    # ========== 测试2: 创建自选股板块 ==========
    print("="*60)
    print("测试2: 创建自选股板块")
    print("="*60)
    block_code = "MCP_DEMO"
    block_name = "MCP演示板块"
    stocks = ["600519", "000001", "300750", "601318", "000858"]
    print(f"📤 创建板块: {block_name}")
    result = create_watchlist(block_code, block_name, stocks)
    print(f"📥 结果: {result}")
    
    # 获取板块列表
    sectors = get_user_sectors()
    print(f"📋 当前自定义板块: {sectors.get('data', [])}")
    print("👀 请查看通达信客户端 - 应显示新建的板块\n")
    time.sleep(2)
    
    # ========== 测试3: 消息推送 ==========
    print("="*60)
    print("测试3: 消息推送")
    print("="*60)
    msg = f"MCP测试消息|时间:{time.strftime('%H:%M:%S')}|自选股板块已创建"
    print(f"📤 发送消息: {msg}")
    result = push_message(msg)
    print(f"📥 结果: {result}")
    print("👀 请查看通达信客户端 - 应显示消息提示\n")
    time.sleep(2)
    
    # ========== 测试4: 预警推送 ==========
    print("="*60)
    print("测试4: 预警推送")
    print("="*60)
    print("📤 发送预警: 600519 贵州茅台")
    result = push_warn(stock_code="600519", price=1500.00, reason="MCP测试预警", bs_flag=0)
    print(f"📥 结果: {result}")
    print("👀 请查看通达信客户端 - 应显示预警信号\n")
    time.sleep(2)
    
    # ========== 清理 ==========
    print("="*60)
    print("清理: 删除测试板块")
    print("="*60)
    result = delete_watchlist(block_code)
    print(f"📥 删除结果: {result}")
    
    print("\n" + "="*60)
    print("测试完成！请检查通达信客户端是否显示了相应内容")
    print("="*60)


if __name__ == "__main__":
    main()

