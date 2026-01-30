#!/usr/bin/env python3
"""
验证修复效果的测试脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from akshare_mcp.tools import (
    technical, sentiment, skills, semantic, quant, search,
    alerts, backtest, data_warmup, decision, portfolio, valuation
)
from akshare_mcp.utils import ok, fail


def test_ok_function():
    """测试ok函数是否正确工作"""
    print("测试 ok() 函数...")
    
    # 测试正常调用
    result1 = ok({'test': 'data'})
    assert result1['success'] == True
    assert result1['data'] == {'test': 'data'}
    print("  ✓ 正常调用成功")
    
    # 测试cached参数
    result2 = ok({'test': 'data'}, cached=True)
    assert result2['success'] == True
    assert result2['cached'] == True
    print("  ✓ cached参数成功")
    
    # 测试source参数应该失败
    try:
        result3 = ok({'test': 'data'}, source='test')
        print("  ✗ source参数应该失败但没有")
        return False
    except TypeError as e:
        if 'source' in str(e):
            print("  ✓ source参数正确拒绝")
        else:
            print(f"  ✗ 意外错误: {e}")
            return False
    
    return True


def test_imports():
    """测试所有模块是否可以正常导入"""
    print("\n测试模块导入...")
    
    modules = [
        ('technical', technical),
        ('sentiment', sentiment),
        ('skills', skills),
        ('semantic', semantic),
        ('quant', quant),
        ('search', search),
        ('alerts', alerts),
        ('backtest', backtest),
        ('data_warmup', data_warmup),
        ('decision', decision),
        ('portfolio', portfolio),
        ('valuation', valuation),
    ]
    
    for name, module in modules:
        try:
            # 检查register函数是否存在
            if hasattr(module, 'register'):
                print(f"  ✓ {name} 模块导入成功")
            else:
                print(f"  ✗ {name} 模块缺少register函数")
                return False
        except Exception as e:
            print(f"  ✗ {name} 模块导入失败: {e}")
            return False
    
    return True


def check_source_parameter():
    """检查是否还有source参数的使用"""
    print("\n检查source参数使用...")
    
    tools_dir = Path(__file__).parent / 'src' / 'akshare_mcp' / 'tools'
    found_issues = []
    
    for py_file in tools_dir.glob('*.py'):
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 检查是否还有 source= 的使用
        if 'source=' in content and 'ok(' in content:
            # 排除注释
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'source=' in line and 'ok(' in line and not line.strip().startswith('#'):
                    found_issues.append(f"{py_file.name}:{i}")
    
    if found_issues:
        print("  ✗ 发现以下文件仍使用source参数:")
        for issue in found_issues:
            print(f"    - {issue}")
        return False
    else:
        print("  ✓ 所有文件已移除source参数")
        return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("股票MCP服务修复验证")
    print("=" * 60)
    
    tests = [
        ("ok()函数测试", test_ok_function),
        ("模块导入测试", test_imports),
        ("source参数检查", check_source_parameter),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} 执行失败: {e}")
            results.append((name, False))
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！修复成功！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，需要进一步检查")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
