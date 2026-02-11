"""
测试 macro.py 的 AkShare 回退功能。
直接调用 _try_akshare_macro 验证数据解析。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from akshare_mcp.tools.macro import _try_akshare_macro


def test_akshare_fallback():
    """逐个测试 AkShare 回退的 5 个指标"""
    indicators = ['cpi', 'ppi', 'gdp', 'pmi', 'm2']

    for ind in indicators:
        print(f"\n{'='*50}")
        print(f"测试 AkShare 回退: {ind}")
        result = _try_akshare_macro(ind, limit=5)
        if result is None:
            print(f"  ❌ 返回 None")
            continue
        if not result.get('success'):
            print(f"  ❌ success=False: {result}")
            continue
        data = result.get('data', {})
        records = data.get('records', [])
        source = data.get('source', '?')
        print(f"  ✅ source={source}, records={len(records)}")
        for r in records[:3]:
            print(f"     {r['period']}: value={r['value']}, yoy={r.get('yoyChange')}, mom={r.get('momChange')}")


if __name__ == '__main__':
    test_akshare_fallback()
