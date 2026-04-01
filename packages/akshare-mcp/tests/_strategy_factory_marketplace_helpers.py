"""Shared helpers for split strategy factory marketplace tests."""

from __future__ import annotations

import numpy as np


def _make_klines(n=300, base=10.0, trend=0.001, noise=0.02):
    """生成模拟K线数据"""
    klines = []
    price = base
    for i in range(n):
        change = trend + np.random.uniform(-noise, noise)
        price *= 1 + change
        price = max(price, 0.5)
        vol = int(np.random.uniform(5000, 50000))
        klines.append(
            {
                "time": f"2024-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
                "open": round(price * 0.998, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "close": round(price, 2),
                "volume": vol,
            }
        )
    return klines


def _closes_from_klines(klines):
    return np.array([float(k["close"]) for k in klines])


def _volumes_from_klines(klines):
    return np.array([float(k["volume"]) for k in klines])
