# 数据质量测试 - 公共配置

import sys
import io
import os
from pathlib import Path

# Windows 控制台编码修复
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def _load_dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in values:
                    values[key] = value
        except Exception:
            continue
    return values


_DOTENV_VALUES = _load_dotenv_values()


def _resolve_setting(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or _DOTENV_VALUES.get(name, "").strip() or default

# ============ Tushare 配置 ============
TUSHARE_TOKEN = _resolve_setting('TUSHARE_TOKEN')
TUSHARE_HTTP_URL = _resolve_setting('TUSHARE_HTTP_URL', 'http://lianghua.nanyangqiankun.top')

# ============ 测试股票 ============
TEST_STOCKS = {
    'SH': '600519',   # 贵州茅台 (沪市)
    'SZ': '000001',   # 平安银行 (深市)
    'SZ2': '000858',  # 五粮液 (深市)
    'CYB': '300750',  # 宁德时代 (创业板)
}

# ============ 数据质量阈值 ============
THRESHOLDS = {
    'field_completeness_min': 0.8,     # 字段完整率最低 80%
    'nan_ratio_max': 0.2,              # NaN 比例最高 20%
    'price_range_min': 0.01,           # 最低价格
    'price_range_max': 100000,         # 最高价格
    'volume_min': 0,                   # 最低成交量
    'pe_range': (-1000, 10000),        # PE 合理范围
    'pb_range': (-100, 1000),          # PB 合理范围
    'kline_price_tolerance': 0.05,     # 多源K线价格容差 5%
}


def tushare_call_api(api_name, params=None, fields=''):
    """通过 HTTP 调用 Tushare 代理 API

    重要: fields 必须放在外层，不能放在 params 字典里。
    代理服务器对 params 中包含 fields 的请求会间歇性返回"服务器内部错误"。
    本函数会自动从 params 中提取 fields 到外层。
    """
    import requests
    import pandas as pd

    if not TUSHARE_TOKEN:
        raise RuntimeError("未配置 TUSHARE_TOKEN：请在环境变量或 packages/akshare-mcp/.env 中设置")

    params = dict(params or {})
    # 关键修复: 从 params 中提取 fields 到外层
    # 代理服务器对 params 中的 fields 处理不一致，某些 API 会间歇性失败
    if 'fields' in params:
        if not fields:
            fields = params.pop('fields')
        else:
            params.pop('fields')  # 外层优先

    payload = {
        'api_name': api_name,
        'token': TUSHARE_TOKEN,
        'params': params,
        'fields': fields
    }
    response = requests.post(TUSHARE_HTTP_URL, json=payload, timeout=30)
    result = response.json()
    if result.get('code') != 0:
        raise Exception(result.get('msg', 'Unknown error'))
    data = result.get('data', {})
    if data:
        return pd.DataFrame(data.get('items', []), columns=data.get('fields', []))
    return pd.DataFrame()


def get_tushare_pro():
    """获取 Tushare Pro SDK 实例 (用于 cpi/ppi 等 SDK 专属方法)"""
    import tushare as ts
    if not TUSHARE_TOKEN:
        raise RuntimeError("未配置 TUSHARE_TOKEN：请在环境变量或 packages/akshare-mcp/.env 中设置")
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api(TUSHARE_TOKEN)
    if TUSHARE_HTTP_URL:
        try:
            pro._DataApi__token = TUSHARE_TOKEN
            pro._DataApi__http_url = TUSHARE_HTTP_URL.rstrip("/")
        except Exception:
            pass
    return pro
class TestResult:
    """测试结果收集器"""

    def __init__(self, name):
        self.name = name
        self.checks = []

    def check(self, description, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        self.checks.append((description, passed, detail))
        icon = "✓" if passed else "✗"
        print(f"  [{icon}] {description}")
        if detail and not passed:
            print(f"      → {detail}")

    def warn(self, description, detail=""):
        self.checks.append((description, None, detail))
        print(f"  [!] {description}")
        if detail:
            print(f"      → {detail}")

    def summary(self):
        total = len([c for c in self.checks if c[1] is not None])
        passed = sum(1 for c in self.checks if c[1] is True)
        failed = sum(1 for c in self.checks if c[1] is False)
        warns = sum(1 for c in self.checks if c[1] is None)
        print(f"\n  结果: {passed}/{total} 通过, {failed} 失败, {warns} 警告")
        return passed, failed, warns
