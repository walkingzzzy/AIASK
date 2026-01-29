#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
使用 akshare-mcp 获取股票列表（已替代直接调用外部数据源）
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
AKSHARE_MCP_SRC = os.path.join(BASE_DIR, "..", "akshare-mcp", "src")
sys.path.append(AKSHARE_MCP_SRC)

from akshare_mcp.tools.market import get_stock_list


def normalize_market(code: str) -> str:
    if code.startswith("68"):
        return "KCB"
    if code.startswith("30"):
        return "CYB"
    if code.startswith("8") or code.startswith("4"):
        return "BJ"
    if code.startswith("6"):
        return "SH"
    return "SZ"


def main():
    print("=" * 50)
    print("  akshare-mcp 股票列表导出")
    print("=" * 50)
    print()

    res = get_stock_list()
    if not res.get("success"):
        print(f"获取股票列表失败: {res.get('error')}")
        sys.exit(1)

    data = res.get("data") or []
    stocks = []
    for item in data:
        code = str(item.get("code") or item.get("代码") or item.get("symbol") or "").strip()
        name = str(item.get("name") or item.get("名称") or "").strip()
        code = code.replace("SH", "").replace("SZ", "").replace("BJ", "").zfill(6)
        if not code or not name:
            continue
        stocks.append({"code": code, "name": name, "market": normalize_market(code)})

    if not stocks:
        print("获取股票列表失败")
        sys.exit(1)

    print(f"\n共获取 {len(stocks)} 只股票")

    markets = {}
    for s in stocks:
        m = s["market"]
        markets[m] = markets.get(m, 0) + 1

    print("\n按市场分布:")
    for m, cnt in sorted(markets.items()):
        print(f"  {m}: {cnt}")

    output_file = os.path.join(os.path.dirname(__file__), "stocks_akshare.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已保存到 {output_file}")


if __name__ == "__main__":
    main()
