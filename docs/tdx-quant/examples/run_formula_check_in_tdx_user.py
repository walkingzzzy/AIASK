# -*- coding: utf-8 -*-
# 在「通达信客户端自带的 Python 环境」下检测公式接口是否挂载
#
# 使用方式（必须按手册来）：
#   1. 先启动通达信金融终端/专业研究版并登录
#   2. 在 VSCode 中：文件 -> 打开文件夹 -> 选择「通达信安装目录\PYPlugins\user」
#   3. 把本文件复制到该 user 目录下（或已在其中打开）
#   4. 在 VSCode 中直接运行本文件（F5 或 运行 Python 文件）
#
# 说明：公式接口由通达信在客户端内挂载到 tq 上，只有在上述环境下运行才能看到
#       formula_set_data_info、formula_zb 等；在项目根目录或其它路径运行可能看不到。

import os
import sys
import io

if getattr(sys.stdout, 'encoding', None) and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

def main():
    print("=" * 60)
    print("通达信客户端内：公式接口挂载检测")
    print("=" * 60)
    print("当前工作目录:", os.path.dirname(os.path.abspath(__file__)))
    print()

    # 1. 导入 tqcenter（当前目录应为 PYPlugins/user）
    try:
        from tqcenter import tq
        print("[1] from tqcenter import tq 成功")
    except Exception as e:
        print("[1] 导入 tqcenter 失败:", e)
        print("     请确认：1) 已打开文件夹「通达信安装目录\\PYPlugins\\user」 2) 该目录下有 tqcenter 相关模块")
        return

    # 2. 按手册要求初始化
    try:
        tq.initialize(__file__)
        print("[2] tq.initialize(__file__) 成功")
    except Exception as e:
        print("[2] tq.initialize(__file__) 失败:", e)
        print("     请确认：通达信客户端已启动并登录")
        return

    # 3. 列出 tq 上所有含 formula 的成员
    tq_attrs = [x for x in dir(tq) if not x.startswith('_')]
    formula_attrs = [x for x in tq_attrs if 'formula' in x.lower()]
    print("[3] tq 上含 'formula' 的成员:", formula_attrs if formula_attrs else "(无)")

    # 4. 若存在 formula_set_data_info，做一次最小调用
    if getattr(tq, 'formula_set_data_info', None) and callable(tq.formula_set_data_info):
        print("[4] 尝试调用 formula_set_data_info(...)")
        try:
            res = tq.formula_set_data_info(
                stock_code='688318.SH',
                stock_period='1d',
                count=10,
                dividend_type=1
            )
            err = res.get('ErrorId', '') if isinstance(res, dict) else ''
            msg = res.get('Msg', '') if isinstance(res, dict) else ''
            if err == '0':
                print("     结果: 成功 (ErrorId=0)", msg or res)
            else:
                print("     结果: 失败", res)
        except Exception as e:
            print("     调用异常:", e)
    else:
        print("[4] 未发现 formula_set_data_info，跳过调用测试")

    # 5. 结论
    print()
    required = ['formula_set_data_info', 'formula_zb']
    has = [n for n in required if getattr(tq, n, None) and callable(getattr(tq, n, None))]
    if len(has) >= len(required):
        print("[结论] 当前环境已挂载公式接口，可按手册使用 formula_set_data_info / formula_zb / formula_xg / formula_exp")
    else:
        print("[结论] 当前环境未挂载公式接口（或仅部分挂载）。请确认：")
        print("       - 已用「通达信安装目录\\PYPlugins\\user」为工作区在 VSCode 中运行本脚本")
        print("       - 通达信客户端已启动并登录")
        print("       - 本机通达信版本/安装包是否包含公式模块")
    print("=" * 60)

if __name__ == '__main__':
    main()
