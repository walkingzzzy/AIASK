# 数据质量测试 - 全量运行器
# 运行所有数据质量测试并生成报告

import sys
import io
import os
import subprocess
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def run_test_file(filepath, timeout=120):
    """运行单个测试文件"""
    print(f"\n{'='*70}")
    print(f"运行: {os.path.basename(filepath)}")
    print('='*70)

    try:
        result = subprocess.run(
            [sys.executable, '-B', filepath],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=os.path.dirname(os.path.abspath(filepath))
        )
        print(result.stdout)
        if result.stderr:
            # 只打印非空 stderr
            stderr = result.stderr.strip()
            if stderr:
                print(f"[stderr] {stderr[:500]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] 测试超时 (>{timeout}s): {filepath}")
        return False
    except Exception as e:
        print(f"[ERROR] 运行失败: {e}")
        return False


def main():
    start_time = datetime.now()

    print("#" * 70)
    print("#  AKShare MCP 数据质量全面测试")
    print(f"#  时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)

    test_dir = os.path.dirname(os.path.abspath(__file__))

    # 测试文件列表 (按依赖顺序)
    # Tushare 测试 (不需要 TDX)
    tushare_tests = [
        ('test_01_tushare_macro.py', '宏观数据质量', 60),
        ('test_02_tushare_finance.py', '财务数据质量', 90),
        ('test_03_tushare_valuation.py', '历史估值质量', 60),
        ('test_04_tushare_limit_up.py', '涨停板数据质量', 60),
        ('test_05_tushare_block_trades.py', '大宗交易+名称映射', 60),
    ]

    # TDX 测试 (需要通达信客户端)
    tdx_tests = [
        ('test_06_tdx_kline.py', 'TDX K线全面质量', 90),
        ('test_07_tdx_technical.py', 'TDX 公式系统与技术指标', 90),
        ('test_08_cross_source.py', '跨源一致性', 90),
        ('test_10_tdx_finance.py', 'TDX 财务数据与股票信息', 90),
        ('test_11_tdx_trading.py', 'TDX 交易数据与市场数据', 90),
        ('test_12_tdx_misc.py', 'TDX 其他接口(IPO/可转债/板块/公式)', 90),
    ]

    # 集成测试
    integration_tests = [
        ('test_09_mcp_integration.py', 'MCP 集成测试', 120),
    ]

    all_tests = tushare_tests + tdx_tests + integration_tests
    results = []

    print("\n" + "=" * 70)
    print("第一阶段: Tushare 数据源测试")
    print("=" * 70)
    for test_file, desc, timeout in tushare_tests:
        filepath = os.path.join(test_dir, test_file)
        if os.path.exists(filepath):
            success = run_test_file(filepath, timeout)
            results.append((test_file, desc, success))
        else:
            print(f"[SKIP] 文件不存在: {test_file}")
            results.append((test_file, desc, None))

    print("\n" + "=" * 70)
    print("第二阶段: TDX 数据源测试 (需要通达信客户端)")
    print("=" * 70)
    for test_file, desc, timeout in tdx_tests:
        filepath = os.path.join(test_dir, test_file)
        if os.path.exists(filepath):
            success = run_test_file(filepath, timeout)
            results.append((test_file, desc, success))
        else:
            print(f"[SKIP] 文件不存在: {test_file}")
            results.append((test_file, desc, None))

    print("\n" + "=" * 70)
    print("第三阶段: MCP 集成测试")
    print("=" * 70)
    for test_file, desc, timeout in integration_tests:
        filepath = os.path.join(test_dir, test_file)
        if os.path.exists(filepath):
            success = run_test_file(filepath, timeout)
            results.append((test_file, desc, success))
        else:
            print(f"[SKIP] 文件不存在: {test_file}")
            results.append((test_file, desc, None))

    # 汇总报告
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("数据质量测试报告")
    print("=" * 70)
    print(f"  运行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  耗时: {duration:.1f} 秒")
    print()

    passed = sum(1 for _, _, r in results if r is True)
    failed = sum(1 for _, _, r in results if r is False)
    skipped = sum(1 for _, _, r in results if r is None)

    for test_file, desc, result in results:
        if result is None:
            status = "SKIP"
        elif result:
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  [{status}] {desc} ({test_file})")

    print()
    print(f"  总计: {passed} 通过, {failed} 失败, {skipped} 跳过")
    print("=" * 70)

    # 生成报告文件
    report_path = os.path.join(test_dir, 'DATA_QUALITY_REPORT.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# 数据质量测试报告\n\n")
        f.write(f"- 运行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 耗时: {duration:.1f} 秒\n")
        f.write(f"- 结果: {passed} 通过, {failed} 失败, {skipped} 跳过\n\n")
        f.write(f"| 测试文件 | 描述 | 结果 |\n")
        f.write(f"|---------|------|------|\n")
        for test_file, desc, result in results:
            status = "SKIP" if result is None else ("PASS" if result else "FAIL")
            f.write(f"| {test_file} | {desc} | {status} |\n")
        f.write(f"\n## 测试覆盖的问题\n\n")
        f.write(f"| 原始问题 | 对应测试 |\n")
        f.write(f"|---------|----------|\n")
        f.write(f"| FAIL #1 CPI 数据 | test_01, test_09 |\n")
        f.write(f"| WARN #2 财务数据 null | test_02, test_09 |\n")
        f.write(f"| WARN #7 大宗交易 name 空 | test_05, test_09 |\n")
        f.write(f"| WARN #8 000001 Invalid argument | test_02 |\n")
        f.write(f"| WARN #9 历史估值不足 | test_03 |\n")
        f.write(f"| WARN #10/#11/#14 涨停统计全0 | test_04, test_09 |\n")
        f.write(f"| WARN #15 PE/PB/PS=0 | test_03, test_09 |\n")
        f.write(f"| WARN #19 DMA 跳变 | test_07 |\n")
        f.write(f"| 跨源一致性 | test_08 |\n")

    print(f"\n  报告已保存: {report_path}")

    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
