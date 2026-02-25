# -*- coding: utf-8 -*-
# 在通达信安装目录下的 PYPlugins/user 中确认 tqcenter 是否提供公式接口
#
# 用法一（推荐）：在通达信 PYPlugins/user 目录下运行
#   cd 通达信安装目录\PYPlugins\user
#   python check_tqcenter_formula_in_tdx_dir.py
#
# 用法二：从任意目录运行，指定插件路径
#   set TDX_PLUGIN_PATH=通达信安装目录\PYPlugins\user
#   python tests\tdx-quant\check_tqcenter_formula_in_tdx_dir.py
#
# 输出：列出该目录下的 tqcenter 相关文件、tqcenter 模块及 tq 对象中所有含 formula 的成员，便于确认是否提供公式接口。

import os
import sys
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# 确定 PYPlugins/user 目录：优先环境变量，其次当前工作目录（便于在 PYPlugins/user 下直接运行）
TDX_USER = os.getenv('TDX_PLUGIN_PATH', '').strip()
if not TDX_USER or not os.path.isdir(TDX_USER):
    TDX_USER = os.getcwd()
if TDX_USER not in sys.path:
    sys.path.insert(0, TDX_USER)

print("=" * 60)
print("在通达信 PYPlugins/user 中确认 tqcenter 是否提供公式接口")
print("=" * 60)
print(f"使用目录: {os.path.abspath(TDX_USER)}")
print()

# 1. 列出目录下与 tqcenter 相关的文件
print("[1] 目录下与 tqcenter 相关的文件")
print("-" * 60)
try:
    for name in sorted(os.listdir(TDX_USER)):
        if 'tq' in name.lower() or name == 'tqcenter.py':
            path = os.path.join(TDX_USER, name)
            kind = "dir" if os.path.isdir(path) else "file"
            print(f"  {kind}: {name}")
except Exception as e:
    print(f"  列出目录失败: {e}")
print()

# 2. 导入 tqcenter 并查看模块内所有名称
print("[2] tqcenter 模块内所有名称 (dir(tqcenter))")
print("-" * 60)
try:
    import tqcenter
    all_names = [x for x in dir(tqcenter) if not x.startswith('_')]
    print(f"  共 {len(all_names)} 个公开成员: {all_names}")
    formula_in_module = [x for x in all_names if 'formula' in x.lower()]
    if formula_in_module:
        print(f"  其中含 'formula' 的: {formula_in_module}")
    else:
        print("  其中含 'formula' 的: (无)")
except Exception as e:
    print(f"  导入 tqcenter 失败: {e}")
    sys.exit(1)
print()

# 3. 查看 tqcenter.tq 的类型及其中含 formula 的成员
print("[3] tqcenter.tq 的类型与公式相关成员")
print("-" * 60)
try:
    tq = getattr(tqcenter, 'tq', None)
    if tq is None:
        print("  tqcenter 中无 'tq' 属性")
    else:
        print(f"  type(tq): {type(tq)}")
        print(f"  tq 所在模块: {getattr(tq, '__module__', 'N/A')}")
        tq_names = [x for x in dir(tq) if not x.startswith('_')]
        formula_on_tq = [x for x in tq_names if 'formula' in x.lower()]
        print(f"  tq 上含 'formula' 的成员: {formula_on_tq if formula_on_tq else '(无)'}")
        print(f"  tq 全部公开成员数量: {len(tq_names)}")
        if not formula_on_tq and len(tq_names) <= 30:
            print(f"  tq 全部公开成员: {tq_names}")
except Exception as e:
    print(f"  检查 tq 失败: {e}")
print()

# 4. 结论
print("[4] 结论")
print("-" * 60)
try:
    tq = getattr(tqcenter, 'tq', None)
    formula_apis = [
        'formula_set_data_info', 'formula_set_data', 'formula_get_data',
        'formula_format_data', 'formula_zb', 'formula_xg', 'formula_exp'
    ]
    found = [name for name in formula_apis if getattr(tq, name, None) is not None and callable(getattr(tq, name, None))]
    if found:
        print(f"  当前 tqcenter 提供公式接口: {found}")
    else:
        print("  当前 tqcenter 未提供公式接口（tq 上无 formula_set_data_info / formula_zb 等）。")
        print("  可能原因: 本安装包/版本不包含公式模块，或需在通达信客户端内运行才挂载公式接口。")
except Exception as e:
    print(f"  结论检查异常: {e}")
print("=" * 60)
