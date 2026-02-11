# -*- coding: utf-8 -*-
# TDX 公式接口诊断与测试脚本
# 用途：确认 tqcenter 中公式相关 API 是否存在、调用是否成功，便于定位 MCP 公式工具报错原因
# 运行：在项目根目录或 tests/tdx-quant 下执行 python tests/tdx-quant/test_formula_diagnosis.py
# 环境：可设置 TDX_PLUGIN_PATH 指向通达信 PYPlugins/user 目录，未设置时使用下方默认路径

import os
import sys
import io

# 控制台编码
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# TDX 插件路径：优先环境变量，其次默认（可按本机安装修改）
_DEFAULT_TDX_PATH = r'C:\new_tdx_test\PYPlugins\user'
TDX_PLUGIN_PATH = os.getenv('TDX_PLUGIN_PATH', '').strip() or _DEFAULT_TDX_PATH

if TDX_PLUGIN_PATH and os.path.isdir(TDX_PLUGIN_PATH) and TDX_PLUGIN_PATH not in sys.path:
    sys.path.insert(0, TDX_PLUGIN_PATH)
    print(f"[Config] TDX_PLUGIN_PATH: {TDX_PLUGIN_PATH}")
else:
    print(f"[Config] Using sys.path (TDX_PLUGIN_PATH not set or not dir: {TDX_PLUGIN_PATH!r})")

# 公式相关 API（与 docs/tdx-quant/api/formula 及 MCP tdx_formula 使用一致）
FORMULA_APIS = [
    'formula_set_data_info',  # 设置公式数据信息（K线范围等）
    'formula_set_data',       # 设置公式数据
    'formula_get_data',       # 获取公式中设置的数据 / 公式用K线
    'formula_format_data',    # 格式化 get_market_data 的K线供公式用
    'formula_zb',             # 技术指标公式 (MACD/KDJ/RSI/BOLL 等)
    'formula_xg',             # 条件选股公式
    'formula_exp',            # 专家系统/表达式公式
]


def check_method(tq, name):
    """检查 tq 是否具有指定方法（存在且可调用）"""
    return hasattr(tq, name) and callable(getattr(tq, name, None))


def diagnose_tq(tq):
    """诊断：列出 tq 的类型、模块及公式 API 存在情况"""
    print("\n" + "=" * 60)
    print("[诊断] tq 对象与公式 API 存在性")
    print("=" * 60)
    print(f"  type(tq): {type(tq)}")
    print(f"  tq module: {getattr(tq, '__module__', 'N/A')}")
    print()
    for name in FORMULA_APIS:
        exists = check_method(tq, name)
        print(f"  hasattr(tq, {name!r}) and callable: {exists}")
    print()
    return [name for name in FORMULA_APIS if check_method(tq, name)]


def test_formula_set_data_info(tq, available):
    """测试 formula_set_data_info（设置公式用K线信息）"""
    print("\n" + "-" * 60)
    print("[Test] formula_set_data_info")
    print("-" * 60)
    if 'formula_set_data_info' not in available:
        print("  [SKIP] formula_set_data_info 不可用")
        return None
    try:
        res = tq.formula_set_data_info(
            stock_code='688318.SH',
            stock_period='1d',
            count=100,
            dividend_type=1
        )
        ok = res.get('ErrorId') == '0'
        print(f"  Result: {res}")
        print(f"  [PASS]" if ok else "  [FAIL] ErrorId != 0")
        return ok
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_formula_get_data(tq, available):
    """测试 formula_get_data（需先 formula_set_data_info）"""
    print("\n" + "-" * 60)
    print("[Test] formula_get_data")
    print("-" * 60)
    if 'formula_get_data' not in available:
        print("  [SKIP] formula_get_data 不可用")
        return None
    try:
        # 先设置数据信息，再获取（与手册一致）
        if 'formula_set_data_info' in available:
            tq.formula_set_data_info(stock_code='688318.SH', stock_period='1d', count=10, dividend_type=1)
        res = tq.formula_get_data()
        err = res.get('ErrorId', '') if isinstance(res, dict) else str(res)
        has_data = isinstance(res, dict) and (res.get('Data') is not None or res.get('Code'))
        print(f"  Result type: {type(res)}, keys: {list(res.keys()) if isinstance(res, dict) else 'N/A'}")
        if isinstance(res, dict) and res.get('Data'):
            data = res['Data']
            print(f"  Data length: {len(data) if isinstance(data, list) else 'N/A'}")
        print(f"  [PASS]" if (err == '0' or has_data) else f"  [FAIL] ErrorId={err}")
        return err == '0' or has_data
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_formula_zb(tq, available):
    """测试 formula_zb（技术指标，如 MACD）"""
    print("\n" + "-" * 60)
    print("[Test] formula_zb (MACD)")
    print("-" * 60)
    if 'formula_zb' not in available:
        print("  [SKIP] formula_zb 不可用")
        return None
    try:
        # 先设置数据（部分版本要求）
        if 'formula_set_data_info' in available:
            tq.formula_set_data_info(stock_code='688318.SH', stock_period='1d', count=50, dividend_type=1)
        res = tq.formula_zb(formula_name='MACD', formula_arg='12,26,9')
        err = res.get('ErrorId', '') if isinstance(res, dict) else ''
        print(f"  Result: {type(res)}, ErrorId: {err}")
        if isinstance(res, dict) and res.get('Data'):
            print(f"  Data keys: {list(res['Data'].keys())[:5]}...")
        print(f"  [PASS]" if err == '0' else f"  [FAIL] ErrorId={err}")
        return err == '0'
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_formula_format_data(tq, available):
    """测试 formula_format_data（格式化 get_market_data 结果为公式用）"""
    print("\n" + "-" * 60)
    print("[Test] formula_format_data")
    print("-" * 60)
    if 'formula_format_data' not in available:
        print("  [SKIP] formula_format_data 不可用")
        return None
    try:
        md = tq.get_market_data(stock_list=['688318.SH'], count=5, period='1d')
        formatted = tq.formula_format_data(md)
        print(f"  get_market_data keys: {list(md.keys()) if isinstance(md, dict) else type(md)}")
        print(f"  formula_format_data result type: {type(formatted)}")
        print("  [PASS]")
        return True
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def main():
    print("\n" + "#" * 60)
    print("#  TDX 公式接口诊断与测试")
    print("#  请确保：1) 通达信客户端已启动  2) TDX_PLUGIN_PATH 指向正确（或使用默认）")
    print("#" * 60)

    try:
        from tqcenter import tq
    except ImportError as e:
        print(f"\n[FATAL] 无法导入 tqcenter: {e}")
        print("  请设置 TDX_PLUGIN_PATH 为通达信安装目录下的 PYPlugins/user 路径")
        return 1

    try:
        tq.initialize(__file__)
        print("\n[OK] tq.initialize(__file__) 成功")
    except Exception as e:
        print(f"\n[FATAL] tq.initialize(__file__) 失败: {e}")
        return 1

    available = diagnose_tq(tq)
    if not available:
        print("[结论] 当前 tq 对象不包含任何公式 API，MCP 公式类工具会报 attribute 错误。")
        print("        请确认：1) 使用通达信安装目录下 PYPlugins/user 中的 tqcenter  2) 客户端已启动")
        return 0

    print(f"[结论] 可用公式 API: {available}")
    print("\n" + "=" * 60)
    print("[测试] 逐项调用")
    print("=" * 60)

    results = []
    results.append(("formula_set_data_info", test_formula_set_data_info(tq, available)))
    results.append(("formula_get_data",       test_formula_get_data(tq, available)))
    results.append(("formula_zb (MACD)",      test_formula_zb(tq, available)))
    results.append(("formula_format_data",    test_formula_format_data(tq, available)))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)
    for name, r in results:
        status = 'PASS' if r is True else ('FAIL' if r is False else 'SKIP')
        print(f"  {name}: {status}")
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
