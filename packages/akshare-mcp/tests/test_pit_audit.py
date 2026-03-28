"""PIT（时点一致性）审计测试集 — pit_audit 测试

覆盖场景：
- PITContext 解析与边界
- pit_filter_records 过滤逻辑
- pit_audit 报告准确性
- 未来函数检查（核心研究链路回归测试）
"""

from __future__ import annotations

import datetime

import pytest

from akshare_mcp.services.pit_utils import (
    PITAuditResult,
    PITContext,
    annotate_pit_compliance,
    as_of,
    as_of_now,
    pit_audit,
    pit_filter_dict,
    pit_filter_records,
)

# ── 工具 ─────────────────────────────────────────────────────────────────────

def _record(available_time: str | None, **extra) -> dict:
    r = {"id": 1, "value": 100}
    if available_time is not None:
        r["available_time"] = available_time
    r.update(extra)
    return r


# ── PITContext 解析 ───────────────────────────────────────────────────────────

class TestPITContext:
    def test_none_as_of_means_now(self):
        ctx = PITContext(as_of=None)
        assert ctx.as_of_datetime is not None
        # 应不超过未来 1 秒
        delta = ctx.as_of_datetime - datetime.datetime.now(tz=datetime.timezone.utc)
        assert abs(delta.total_seconds()) < 2

    def test_date_string_expanded_to_end_of_day(self):
        ctx = PITContext(as_of="2025-06-30")
        dt = ctx.as_of_datetime
        assert dt.year == 2025 and dt.month == 6 and dt.day == 30
        assert dt.hour == 23 and dt.minute == 59

    def test_iso_datetime_string(self):
        ctx = PITContext(as_of="2025-01-15T10:30:00")
        dt = ctx.as_of_datetime
        assert dt.year == 2025 and dt.hour == 10

    def test_invalid_as_of_raises(self):
        with pytest.raises(ValueError):
            PITContext(as_of="not-a-date")

    def test_is_available_future_returns_false(self):
        ctx = as_of("2025-06-30")
        assert not ctx.is_available("2025-07-01T00:00:00")

    def test_is_available_same_day_returns_true(self):
        ctx = as_of("2025-06-30")
        assert ctx.is_available("2025-06-30T12:00:00")

    def test_is_available_none_lax(self):
        ctx = as_of("2025-06-30", strict=False)
        assert ctx.is_available(None)  # 宽松模式：缺失视为合规

    def test_is_available_none_strict(self):
        ctx = as_of("2025-06-30", strict=True)
        assert not ctx.is_available(None)  # 严格模式：缺失视为违规

    def test_summary_contains_as_of(self):
        ctx = as_of("2025-06-30")
        s = ctx.summary()
        assert "2025-06-30" in s["as_of"]


# ── pit_filter_records ────────────────────────────────────────────────────────

class TestPITFilterRecords:
    def test_empty_list(self):
        ctx = as_of("2025-06-30")
        assert pit_filter_records([], ctx) == []

    def test_all_compliant(self):
        ctx = as_of("2025-06-30")
        records = [
            _record("2025-01-01"),
            _record("2025-06-30"),
        ]
        result = pit_filter_records(records, ctx)
        assert len(result) == 2

    def test_future_record_removed(self):
        ctx = as_of("2025-06-30")
        records = [
            _record("2025-01-01"),
            _record("2025-07-01"),  # 未来，应被移除
            _record("2025-06-30"),
        ]
        result = pit_filter_records(records, ctx)
        assert len(result) == 2
        assert all(r["available_time"] <= "2025-06-30T23:59:59" for r in result)

    def test_missing_available_time_kept_in_lax_mode(self):
        ctx = as_of("2025-06-30", strict=False)
        records = [_record(None)]
        assert pit_filter_records(records, ctx) == records

    def test_missing_available_time_removed_in_strict_mode(self):
        ctx = as_of("2025-06-30", strict=True)
        records = [_record(None)]
        assert pit_filter_records(records, ctx) == []

    def test_custom_key(self):
        ctx = as_of("2025-06-30")
        records = [
            {"ingest_time": "2025-06-01", "value": 1},
            {"ingest_time": "2025-07-01", "value": 2},  # 违规
        ]
        result = pit_filter_records(records, ctx, available_time_key="ingest_time")
        assert len(result) == 1 and result[0]["value"] == 1


# ── pit_audit ─────────────────────────────────────────────────────────────────

class TestPITAudit:
    def _make_records(self, dates: list[str | None]) -> list[dict]:
        return [_record(d, id=i) for i, d in enumerate(dates)]

    def test_all_compliant(self):
        ctx = as_of("2025-06-30")
        records = self._make_records(["2025-01-01", "2025-06-01", "2025-06-30"])
        result = pit_audit(records, ctx)
        assert isinstance(result, PITAuditResult)
        assert result.total == 3
        assert result.violated == 0
        assert result.compliance_rate == 1.0
        assert result.risk_level == "low"

    def test_some_violated(self):
        ctx = as_of("2025-06-30")
        records = self._make_records(["2025-01-01", "2025-07-01", "2025-08-01"])
        result = pit_audit(records, ctx)
        assert result.violated == 2
        assert result.compliant == 1
        assert result.risk_level == "high"
        assert len(result.violation_examples) == 2

    def test_missing_available_time(self):
        ctx = as_of("2025-06-30")
        records = self._make_records([None, None, "2025-01-01"])
        result = pit_audit(records, ctx)
        assert result.missing_available_time == 2
        assert result.violated == 0  # 缺失在宽松模式下不计违规

    def test_to_dict(self):
        ctx = as_of("2025-06-30")
        records = self._make_records(["2025-01-01"])
        result = pit_audit(records, ctx)
        d = result.to_dict()
        assert "total" in d and "compliance_rate" in d and "risk_level" in d

    def test_max_examples_capped(self):
        ctx = as_of("2025-06-30")
        future_records = self._make_records(["2025-07-01"] * 10)
        result = pit_audit(future_records, ctx, max_examples=3)
        assert len(result.violation_examples) == 3


# ── annotate_pit_compliance ───────────────────────────────────────────────────

class TestAnnotatePITCompliance:
    def test_annotates_records(self):
        ctx = as_of("2025-06-30")
        records = [_record("2025-01-01"), _record("2025-07-01")]
        result = annotate_pit_compliance(records, ctx)
        assert len(result) == 2
        assert result[0]["_pit_ok"] is True
        assert result[1]["_pit_ok"] is False
        assert "_pit_as_of" in result[0]


# ── pit_filter_dict ───────────────────────────────────────────────────────────

class TestPITFilterDict:
    def test_compliant_record_returned(self):
        ctx = as_of("2025-06-30")
        r = _record("2025-06-01")
        assert pit_filter_dict(r, ctx) is r

    def test_violated_record_returns_none(self):
        ctx = as_of("2025-06-30")
        r = _record("2025-07-01")
        assert pit_filter_dict(r, ctx) is None

    def test_non_dict_returned_as_is(self):
        ctx = as_of("2025-06-30")
        assert pit_filter_dict("not a dict", ctx) == "not a dict"  # type: ignore[arg-type]


# ── 未来函数回归测试（核心研究链路）─────────────────────────────────────────────

class TestLookaheadBiasRegression:
    """
    模拟核心研究链路中的未来信息检查。

    这些测试确保在以历史日期为 as_of 时，
    财报、公告、研报等数据不会提前泄露。
    """

    def test_financial_report_not_leaked_before_disclosure(self):
        """2025Q1 财报（3月31日报告期）在 2025-04-29 才公告，
        as_of=2025-04-28 时不可见。"""
        ctx = as_of("2025-04-28")  # 公告前一天
        financial_records = [
            {
                "report_period": "2025-03-31",
                "available_time": "2025-04-29T08:00:00",  # 公告日
                "net_profit": 1_000_000,
            }
        ]
        result = pit_filter_records(financial_records, ctx)
        assert result == [], "财报在公告前不应可见（未来信息泄露）"

    def test_financial_report_visible_after_disclosure(self):
        """as_of=2025-04-29 时财报已可见。"""
        ctx = as_of("2025-04-29")
        financial_records = [
            {
                "report_period": "2025-03-31",
                "available_time": "2025-04-29T08:00:00",
                "net_profit": 1_000_000,
            }
        ]
        result = pit_filter_records(financial_records, ctx)
        assert len(result) == 1

    def test_research_report_not_leaked_before_publish(self):
        """研报在发布前不应可见。"""
        ctx = as_of("2025-03-15")
        reports = [
            {"title": "买入评级", "available_time": "2025-03-16T09:30:00"},
        ]
        result = pit_filter_records(reports, ctx)
        assert result == []

    def test_news_not_leaked(self):
        """新闻在发布前不可见。"""
        ctx = as_of("2025-06-30T08:00:00")
        news = [{"headline": "重大利好", "available_time": "2025-06-30T10:00:00"}]
        result = pit_filter_records(news, ctx)
        assert result == [], "收盘前发布的新闻在 8:00 时不应可见"

    def test_audit_identifies_lookahead_risk(self):
        """混合合规/违规数据的审计结果应正确标识风险。"""
        ctx = as_of("2025-06-30")
        records = [
            {"id": 1, "available_time": "2025-01-01"},  # 合规
            {"id": 2, "available_time": "2025-07-01"},  # 违规
            {"id": 3, "available_time": "2025-07-15"},  # 违规
        ]
        result = pit_audit(records, ctx)
        assert result.risk_level in ("medium", "high")
        assert result.violated == 2
        assert "未来信息" in result.summary
