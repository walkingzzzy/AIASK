# -*- coding: utf-8 -*-
"""
TdxQuant 前端交互测试脚本

测试通达信客户端前端显示功能：
1. 创建自选股板块并在前端显示
2. 发送消息到前端
3. 发送预警信号

运行前提：
1. 通达信客户端已启动并登录
2. TDX_PLUGIN_PATH 配置正确
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


def test_temp_condition_stocks():
    """测试1: 发送临时条件股（直接在前端显示）"""
    print("\n" + "="*60)
    print("测试1: 发送临时条件股到通达信前端")
    print("="*60)
    print("📌 说明: block_code为空时，股票会显示在'临时条件股'中")
    
    from akshare_mcp.data_source import data_source
    
    if not data_source.is_tdx_available():
        print("❌ TdxQuant 不可用")
        return False
    
    tq = data_source.get_tdxquant()
    
    # 发送到临时条件股（block_code为空）
    stocks = ["600519.SH", "000001.SZ", "300750.SZ", "601318.SH", "000858.SZ"]
    print(f"\n📤 发送股票到临时条件股: {stocks}")
    
    result = tq.send_user_block(
        block_code='',  # 空字符串 = 临时条件股
        stocks=stocks,
        show=True  # 切换到该界面
    )
    print(f"📥 返回结果: {result}")
    
    if isinstance(result, dict) and result.get("ErrorId") == "0":
        print("✅ 发送成功！请查看通达信客户端的'临时条件股'")
        return True
    else:
        print(f"❌ 发送失败: {result}")
        return False


def test_create_watchlist_frontend():
    """测试2: 创建自选股板块并在前端显示"""
    print("\n" + "="*60)
    print("测试2: 创建自选股板块并在前端显示")
    print("="*60)
    
    from akshare_mcp.tools.tdx_integration import (
        create_watchlist, get_user_sectors, delete_watchlist
    )
    
    block_code = "MCP_DEMO"
    block_name = "MCP演示板块"
    stocks = ["600519", "000001", "300750", "601318", "000858", "002594"]
    
    print(f"\n📤 创建板块: {block_name} ({block_code})")
    print(f"📤 添加股票: {stocks}")
    
    result = create_watchlist(block_code, block_name, stocks)
    print(f"📥 返回结果: {result}")
    
    if result.get("success"):
        print("✅ 板块创建成功！请查看通达信客户端")
        print("   - 在'自定义板块'中应该能看到新板块")
        print("   - 客户端应该已自动切换到该板块")
        
        # 显示当前所有自定义板块
        print("\n📋 当前所有自定义板块:")
        sectors = get_user_sectors()
        if sectors.get("success"):
            for s in sectors.get("data", []):
                print(f"   - {s.get('Name')} ({s.get('Code')})")
        
        return True
    else:
        print(f"❌ 创建失败: {result.get('message')}")
        return False


def test_message_push_frontend():
    """测试3: 发送消息到通达信前端"""
    print("\n" + "="*60)
    print("测试3: 发送消息到通达信前端")
    print("="*60)
    
    from akshare_mcp.tools.tdx_integration import push_message
    
    message = "MCP前端测试|这是一条来自akshare-mcp的测试消息|时间: " + time.strftime("%H:%M:%S")
    print(f"\n📤 发送消息: {message}")
    
    result = push_message(message)
    print(f"📥 返回结果: {result}")
    
    if result.get("success"):
        print("✅ 消息发送成功！请查看通达信客户端的消息提示")
        return True
    else:
        print(f"❌ 发送失败: {result.get('message')}")
        return False


def test_warn_push_frontend():
    """测试4: 发送预警信号到通达信前端"""
    print("\n" + "="*60)
    print("测试4: 发送预警信号到通达信前端")
    print("="*60)
    
    from akshare_mcp.tools.tdx_integration import push_warn
    
    print("\n📤 发送预警信号: 600519 贵州茅台 价格突破1500")
    
    result = push_warn(
        stock_code="600519",
        price=1500.00,
        reason="MCP测试预警: 价格突破关键位",
        bs_flag=0  # 0=买入信号
    )
    print(f"📥 返回结果: {result}")
    
    if result.get("success"):
        print("✅ 预警发送成功！请查看通达信客户端的预警提示")
        return True
    else:
        print(f"❌ 发送失败: {result.get('message')}")
        return False


def cleanup():
    """清理测试数据"""
    print("\n" + "="*60)
    print("清理: 删除测试板块")
    print("="*60)
    
    from akshare_mcp.tools.tdx_integration import delete_watchlist
    
    result = delete_watchlist("MCP_DEMO")
    print(f"📥 删除结果: {result}")


def main():
    print("="*60)
    print("TdxQuant 前端交互测试")
    print("="*60)
    print("\n⚠️  请确保通达信客户端已启动并可见")
    print("⚠️  测试过程中请观察通达信客户端的变化\n")
    
    input("按 Enter 键开始测试...")
    
    # 测试1: 临时条件股
    test_temp_condition_stocks()
    input("\n按 Enter 继续下一个测试...")
    
    # 测试2: 创建自选股板块
    test_create_watchlist_frontend()
    input("\n按 Enter 继续下一个测试...")
    
    # 测试3: 消息推送
    test_message_push_frontend()
    input("\n按 Enter 继续下一个测试...")
    
    # 测试4: 预警推送
    test_warn_push_frontend()
    
    # 清理
    input("\n按 Enter 清理测试数据...")
    cleanup()
    
    print("\n" + "="*60)
    print("前端交互测试完成")
    print("="*60)


if __name__ == "__main__":
    main()

