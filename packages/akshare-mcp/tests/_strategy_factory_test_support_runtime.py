from __future__ import annotations

import math
from datetime import date, datetime, timezone

from akshare_mcp.services.trade_audit_writer import aggregate_trade_position

_EXECUTION_AUDIT_REQUIRED_TABLES = (
    "strategy_candidate_evidence",
    "strategy_signal_evidence",
    "strategy_trade_positions",
    "strategy_trade_position_fills",
)
_EXECUTION_AUDIT_REQUIRED_COLUMNS = {
    "paper_orders": ("signal_id", "position_id"),
    "paper_trades": ("signal_id", "position_id"),
}
_EXECUTION_AUDIT_REQUIRED_MIGRATIONS = (
    "paper_trades_best_effort_position_backfill_v1",
    "strategy_candidate_evidence_native_backfill_v1",
    "strategy_signal_evidence_native_backfill_v1",
    "strategy_trade_positions_roundtrip_backfill_v1",
)

class _StrategyDBRuntimeMixin:
    async def save_strategy_factory_run(self, run):
        self._factory_runs = [item for item in self._factory_runs if item.get("run_id") != run.get("run_id")]
        self._factory_runs.append(dict(run))
        self._factory_runs.sort(key=lambda item: item.get("started_at") or "", reverse=True)

    async def list_strategy_factory_runs(self, limit=20):
        return self._factory_runs[:limit]

    async def get_latest_strategy_factory_run(self):
        rows = await self.list_strategy_factory_runs(limit=1)
        return rows[0] if rows else None

    async def get_strategy_factory_run(self, run_id):
        for item in self._factory_runs:
            if item.get("run_id") == run_id:
                return item
        return None

    @staticmethod
    def _normalize_snapshot_date(snapshot_date):
        return str(snapshot_date)

    async def save_daily_snapshot(self, snapshot_date, data):
        normalized = self._normalize_snapshot_date(snapshot_date)
        item = {"snapshot_date": normalized, **dict(data)}
        self._daily_snapshots = [row for row in self._daily_snapshots if row.get("snapshot_date") != normalized]
        self._daily_snapshots.append(item)
        self._daily_snapshots.sort(key=lambda row: row.get("snapshot_date") or "", reverse=True)

    async def save_factory_market_internal_snapshot(self, item):
        payload = {"snapshot_date": self._normalize_snapshot_date((item or {}).get("snapshot_date") or (item or {}).get("date")), **dict(item or {})}
        self._factory_market_internals = [row for row in self._factory_market_internals if row.get("snapshot_date") != payload.get("snapshot_date")]
        self._factory_market_internals.append(payload)
        self._factory_market_internals.sort(key=lambda row: row.get("snapshot_date") or "", reverse=True)
        return dict(payload)

    async def get_factory_market_internal_snapshot(self, snapshot_date=None):
        if snapshot_date is None:
            return dict(self._factory_market_internals[0]) if self._factory_market_internals else None
        normalized = self._normalize_snapshot_date(snapshot_date)
        for item in self._factory_market_internals:
            if item.get("snapshot_date") == normalized:
                return dict(item)
        return None

    async def list_factory_market_internal_snapshots(self, limit=20):
        return [dict(item) for item in self._factory_market_internals[: max(1, min(int(limit or 20), 200))]]

    async def get_recent_north_fund_summary(self, days=3, sample_limit=5):
        if self._north_fund_summary is not None:
            return dict(self._north_fund_summary)
        return None

    async def get_daily_snapshot(self, snapshot_date=None):
        if snapshot_date is None:
            return self._daily_snapshots[0] if self._daily_snapshots else None
        normalized = self._normalize_snapshot_date(snapshot_date)
        for item in self._daily_snapshots:
            if item.get("snapshot_date") == normalized:
                return item
        return None

    async def list_daily_snapshots(self, limit=20, start_date=None, end_date=None):
        rows = list(self._daily_snapshots)
        if start_date:
            rows = [row for row in rows if row.get("snapshot_date") >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row.get("snapshot_date") <= str(end_date)]
        return rows[:limit]

    async def save_factory_event_cluster(self, item):
        event_id = str((item or {}).get('event_id') or '').strip()
        self._factory_event_clusters = [row for row in self._factory_event_clusters if str(row.get('event_id') or '').strip() != event_id]
        saved = dict(item or {})
        saved.setdefault('event_id', event_id)
        self._factory_event_clusters.append(saved)
        self._factory_event_clusters.sort(key=lambda row: row.get('last_seen_at') or row.get('occurred_at') or '', reverse=True)
        return saved

    async def list_factory_event_clusters(self, status=None, event_type=None, limit=20):
        rows = [dict(item) for item in self._factory_event_clusters]
        if status:
            rows = [row for row in rows if str(row.get('status') or 'active') == str(status)]
        if event_type:
            rows = [row for row in rows if str(row.get('event_type') or '') == str(event_type)]
        rows.sort(key=lambda row: (row.get('last_seen_at') or row.get('occurred_at') or '', float(row.get('confidence') or 0.0)), reverse=True)
        return rows[: max(1, min(int(limit or 20), 200))]

    async def save_factory_theme_definition(self, item):
        theme_code = str((item or {}).get('theme_code') or '').strip()
        self._factory_theme_definitions = [row for row in self._factory_theme_definitions if str(row.get('theme_code') or '').strip() != theme_code]
        saved = dict(item or {})
        saved.setdefault('theme_code', theme_code)
        self._factory_theme_definitions.append(saved)
        self._factory_theme_definitions.sort(key=lambda row: str(row.get('theme_code') or ''))
        return saved

    async def list_factory_theme_definitions(self, active_only=True, limit=200):
        rows = [dict(item) for item in self._factory_theme_definitions]
        if active_only:
            rows = [row for row in rows if bool(row.get('active', True))]
        rows.sort(key=lambda row: str(row.get('theme_code') or ''))
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_company_theme_exposure(self, item):
        symbol = str((item or {}).get('symbol') or '').strip()
        theme_code = str((item or {}).get('theme_code') or '').strip()
        exposure_type = str((item or {}).get('exposure_type') or 'revenue')
        self._factory_company_theme_exposures = [
            row for row in self._factory_company_theme_exposures
            if not (
                str(row.get('symbol') or '').strip() == symbol
                and str(row.get('theme_code') or '').strip() == theme_code
                and str(row.get('exposure_type') or 'revenue') == exposure_type
            )
        ]
        saved = dict(item or {})
        self._factory_company_theme_exposures.append(saved)
        self._factory_company_theme_exposures.sort(key=lambda row: float(row.get('exposure_score') or 0.0), reverse=True)
        return saved

    async def list_factory_company_theme_exposures(self, theme_codes=None, symbols=None, limit=200):
        rows = [dict(item) for item in self._factory_company_theme_exposures]
        normalized_theme_codes = {str(item).strip() for item in list(theme_codes or []) if str(item).strip()}
        normalized_symbols = {str(item).strip() for item in list(symbols or []) if str(item).strip()}
        if normalized_theme_codes:
            rows = [row for row in rows if str(row.get('theme_code') or '').strip() in normalized_theme_codes]
        if normalized_symbols:
            rows = [row for row in rows if str(row.get('symbol') or '').strip() in normalized_symbols]
        rows.sort(key=lambda row: float(row.get('exposure_score') or 0.0), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_event_signal(self, item):
        event_id = str((item or {}).get('event_id') or '').strip()
        symbol = str((item or {}).get('symbol') or '').strip()
        theme_code = str((item or {}).get('theme_code') or '').strip()
        self._factory_event_signals = [
            row for row in self._factory_event_signals
            if not (
                str(row.get('event_id') or '').strip() == event_id
                and str(row.get('symbol') or '').strip() == symbol
                and str(row.get('theme_code') or '').strip() == theme_code
            )
        ]
        saved = dict(item or {})
        self._factory_event_signals.append(saved)
        self._factory_event_signals.sort(key=lambda row: (float(row.get('final_score') or 0.0), row.get('observed_at') or ''), reverse=True)
        return saved

    async def list_factory_event_signals(self, event_id=None, theme_code=None, symbols=None, min_final_score=None, limit=200):
        rows = [dict(item) for item in self._factory_event_signals]
        if event_id:
            rows = [row for row in rows if str(row.get('event_id') or '').strip() == str(event_id)]
        if theme_code is not None:
            rows = [row for row in rows if str(row.get('theme_code') or '').strip() == str(theme_code)]
        normalized_symbols = {str(item).strip() for item in list(symbols or []) if str(item).strip()}
        if normalized_symbols:
            rows = [row for row in rows if str(row.get('symbol') or '').strip() in normalized_symbols]
        if min_final_score is not None:
            rows = [row for row in rows if float(row.get('final_score') or 0.0) >= float(min_final_score)]
        rows.sort(key=lambda row: (float(row.get('final_score') or 0.0), row.get('observed_at') or ''), reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_factory_task_evidence(self, item):
        saved = dict(item or {})
        self._factory_task_evidence.append(saved)
        self._factory_task_evidence.sort(key=lambda row: row.get('created_at') or '', reverse=True)
        return saved

    async def list_factory_task_evidence(self, task_key=None, event_id=None, limit=200):
        rows = [dict(item) for item in self._factory_task_evidence]
        if task_key:
            rows = [row for row in rows if str(row.get('task_key') or '') == str(task_key)]
        if event_id:
            rows = [row for row in rows if str(row.get('event_id') or '') == str(event_id)]
        rows.sort(key=lambda row: row.get('created_at') or '', reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_market_headline_labels(self, stock_code, doc_type, labels):
        saved = []
        for raw in list(labels or []):
            item = dict(raw or {})
            label_id = str(item.get("label_id") or "").strip()
            if not label_id:
                label_id = (
                    f"{stock_code}:{doc_type}:{item.get('doc_uid') or item.get('headline') or len(self._market_headline_labels)}"
                )
                item["label_id"] = label_id
            self._market_headline_labels = [
                row for row in self._market_headline_labels
                if str(row.get("label_id") or "").strip() != label_id
            ]
            item.setdefault("stock_code", stock_code)
            item.setdefault("doc_type", doc_type)
            self._market_headline_labels.append(item)
            saved.append(dict(item))
        self._market_headline_labels.sort(
            key=lambda row: row.get("published_at") or row.get("created_at") or "",
            reverse=True,
        )
        return saved

    async def list_market_headline_labels(self, stock_code=None, doc_type=None, limit=200):
        rows = [dict(item) for item in self._market_headline_labels]
        if stock_code is not None:
            rows = [row for row in rows if str(row.get("stock_code") or "") == str(stock_code)]
        if doc_type is not None:
            rows = [row for row in rows if str(row.get("doc_type") or "") == str(doc_type)]
        rows.sort(key=lambda row: row.get("published_at") or row.get("created_at") or "", reverse=True)
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_market_documents(self, stock_code, doc_type, items, **_kwargs):
        code = str(stock_code or "").strip()
        normalized_doc_type = str(doc_type or "").strip().lower()
        documents = [dict(item or {}) for item in list(items or []) if isinstance(item, dict)]
        inserted_labels = []
        for item in documents:
            doc_uid = str(
                item.get("doc_uid")
                or f"{code}:{normalized_doc_type}:{item.get('id') or item.get('title') or item.get('headline') or len(self._market_documents)}"
            )
            row = {
                "doc_uid": doc_uid,
                "stock_code": code,
                "doc_type": normalized_doc_type,
                **item,
            }
            self._market_documents = [
                existing for existing in self._market_documents
                if str(existing.get("doc_uid") or "") != doc_uid
            ]
            self._market_documents.append(row)
            headline = str(item.get("headline") or item.get("title") or "").strip()
            label = str(item.get("label") or "").strip().lower()
            if headline and label:
                label_row = {
                    "label_id": str(item.get("headline_label_id") or f"{doc_uid}:label"),
                    "doc_uid": doc_uid,
                    "stock_code": code,
                    "doc_type": normalized_doc_type,
                    "published_at": item.get("published_at") or item.get("date"),
                    "headline": headline,
                    "label": label,
                    "event_type": item.get("event_type"),
                    "direction": item.get("direction"),
                    "horizon_days": item.get("horizon_days"),
                    "intensity": item.get("intensity"),
                    "confidence": item.get("confidence"),
                    "keywords": list(item.get("keywords") or []),
                    "payload": dict(item.get("payload") or {}),
                }
                inserted_labels.extend(
                    await self.save_market_headline_labels(code, normalized_doc_type, [label_row])
                )
        return {
            "documents": len(documents),
            "chunks": 0,
            "embedded_chunks": 0,
            "headline_labels": len(inserted_labels),
        }

    async def save_strategy_candidate_evidence(self, item):
        saved = dict(item or {})
        candidate_id = str(saved.get('candidate_id') or '').strip()
        evidence_id = str(saved.get('evidence_id') or '').strip()
        self._strategy_candidate_evidence = [
            row for row in self._strategy_candidate_evidence
            if not (
                str(row.get('candidate_id') or '').strip() == candidate_id
                and str(row.get('evidence_id') or '').strip() == evidence_id
            )
        ]
        self._strategy_candidate_evidence.append(saved)
        return dict(saved)

    async def list_strategy_candidate_evidence(self, *, candidate_id=None, strategy_id=None, limit=200):
        rows = [dict(item) for item in self._strategy_candidate_evidence]
        if candidate_id is not None:
            rows = [item for item in rows if str(item.get('candidate_id') or '').strip() == str(candidate_id)]
        if strategy_id is not None:
            rows = [item for item in rows if str(item.get('strategy_id') or '').strip() == str(strategy_id)]
        return rows[: max(1, min(int(limit or 200), 500))]

    async def save_strategy_signal_evidence(self, item):
        saved = dict(item or {})
        signal_id = str(saved.get('signal_id') or '').strip()
        evidence_id = str(saved.get('evidence_id') or '').strip()
        applied_claim_id = str(saved.get('applied_claim_id') or '').strip()
        applied_trade_step_id = str(saved.get('applied_trade_step_id') or '').strip()
        self._strategy_signal_evidence = [
            row for row in self._strategy_signal_evidence
            if not (
                str(row.get('signal_id') or '').strip() == signal_id
                and str(row.get('evidence_id') or '').strip() == evidence_id
                and str(row.get('applied_claim_id') or '').strip() == applied_claim_id
                and str(row.get('applied_trade_step_id') or '').strip() == applied_trade_step_id
            )
        ]
        self._strategy_signal_evidence.append(saved)
        return dict(saved)

    async def list_strategy_signal_evidence(self, *, signal_id=None, strategy_id=None, limit=200):
        rows = [dict(item) for item in self._strategy_signal_evidence]
        if signal_id is not None:
            rows = [item for item in rows if str(item.get('signal_id') or '').strip() == str(signal_id)]
        if strategy_id is not None:
            rows = [item for item in rows if str(item.get('strategy_id') or '').strip() == str(strategy_id)]
        rows.sort(
            key=lambda item: (
                str(item.get("signal_ts") or item.get("created_at") or ""),
                str(item.get("applied_claim_id") or ""),
                str(item.get("applied_trade_step_id") or ""),
            ),
            reverse=True,
        )
        return rows[: max(1, min(int(limit or 200), 500))]

    async def get_paper_account_by_strategy(self, strategy_id):
        for item in self._paper_accounts.values():
            if item.get('strategy_id') == strategy_id:
                return dict(item)
        return None

    async def get_paper_account(self, account_id):
        item = self._paper_accounts.get(account_id)
        return dict(item) if item else None

    async def save_paper_account(self, account):
        item = dict(account)
        existing = self._paper_accounts.get(item['id']) or {}
        merged = {**existing, **item}
        self._paper_accounts[item['id']] = merged
        return dict(merged)

    async def update_paper_account_status(self, account_id, status, stage=None, promotion_candidate=None):
        account = self._paper_accounts.get(account_id)
        if not account:
            return None
        account['status'] = status
        if stage is not None:
            account['incubation_stage'] = stage
        if promotion_candidate is not None:
            account['promotion_candidate'] = promotion_candidate
        return dict(account)

    async def list_strategy_paper_orders(self, strategy_id, signal_date=None, status=None, limit=200):
        rows = [dict(item) for item in self._paper_orders if item.get('strategy_id') == strategy_id]
        if signal_date is not None:
            rows = [item for item in rows if str(item.get('signal_date')) == str(signal_date)]
        if status is not None:
            rows = [item for item in rows if str(item.get('status')) == str(status)]
        rows.sort(key=lambda item: int(item.get('id') or 0), reverse=True)
        return rows[:limit]

    async def list_strategy_paper_trades(self, strategy_id, account_id=None, limit=500):
        rows = [dict(item) for item in self._paper_trades if item.get('strategy_id') == strategy_id]
        if account_id is not None:
            rows = [item for item in rows if item.get('account_id') == account_id]
        rows.sort(key=lambda item: str(item.get('trade_time') or ''), reverse=True)
        return rows[:limit]

    async def save_paper_order(self, order):
        item = dict(order)
        item.setdefault('id', len(self._paper_orders) + 1)
        self._paper_orders.append(item)
        return dict(item)

    async def update_paper_order(self, order_id, updates):
        for item in self._paper_orders:
            if int(item.get('id')) == int(order_id):
                item.update(dict(updates or {}))
                return dict(item)
        return None

    async def list_paper_positions(self, account_id):
        rows = [dict(item) for item in self._paper_positions.values() if item.get('account_id') == account_id]
        rows.sort(key=lambda item: str(item.get('stock_code') or ''))
        return rows

    async def save_paper_position(self, position):
        item = dict(position)
        key = (item.get('account_id'), item.get('stock_code'))
        existing = self._paper_positions.get(key) or {}
        merged = {**existing, **item}
        self._paper_positions[key] = merged
        return dict(merged)

    async def save_paper_trade(self, trade):
        item = dict(trade)
        self._paper_trades.append(item)
        return dict(item)

    async def save_strategy_signal_event_snapshot(self, snapshot):
        item = dict(snapshot or {})
        strategy_id = str(item.get("strategy_id") or "").strip()
        code = str(item.get("code") or "").strip()
        as_of_date = str(item.get("as_of_date") or "").strip()
        if not strategy_id or not code or not as_of_date:
            raise ValueError("strategy_id/code/as_of_date are required for signal event snapshots")
        item["strategy_id"] = strategy_id
        item["code"] = code
        item["as_of_date"] = as_of_date
        item.setdefault("recent_events", [])
        item.setdefault("metadata", {})
        self._signal_event_snapshots = [
            row
            for row in self._signal_event_snapshots
            if not (
                str(row.get("strategy_id") or "").strip() == strategy_id
                and str(row.get("code") or "").strip() == code
                and str(row.get("as_of_date") or "").strip() == as_of_date
            )
        ]
        self._signal_event_snapshots.append(item)
        self._signal_event_snapshots.sort(
            key=lambda row: (
                str(row.get("as_of_date") or ""),
                str(row.get("updated_at") or row.get("created_at") or ""),
            ),
            reverse=True,
        )
        return dict(item)

    async def list_strategy_signal_event_snapshots(
        self,
        strategy_id=None,
        code=None,
        as_of_date=None,
        *,
        latest_only=False,
        limit=20,
    ):
        rows = [dict(item) for item in self._signal_event_snapshots]
        if strategy_id is not None:
            rows = [row for row in rows if str(row.get("strategy_id") or "") == str(strategy_id)]
        if code is not None:
            rows = [row for row in rows if str(row.get("code") or "") == str(code)]
        if as_of_date is not None:
            rows = [row for row in rows if str(row.get("as_of_date") or "") == str(as_of_date)]
        rows.sort(
            key=lambda row: (
                str(row.get("as_of_date") or ""),
                str(row.get("updated_at") or row.get("created_at") or ""),
            ),
            reverse=True,
        )
        if latest_only:
            latest_rows = []
            seen = set()
            for row in rows:
                key = (
                    str(row.get("strategy_id") or ""),
                    str(row.get("code") or ""),
                )
                if key in seen:
                    continue
                latest_rows.append(row)
                seen.add(key)
            rows = latest_rows
        return rows[: max(1, min(int(limit or 20), 500))]

    async def get_latest_strategy_signal_event_snapshot(self, strategy_id, code=None):
        rows = await self.list_strategy_signal_event_snapshots(
            strategy_id=strategy_id,
            code=code,
            latest_only=True,
            limit=1,
        )
        return dict(rows[0]) if rows else None

    async def update_paper_trade_linkage(self, trade_id, updates):
        for item in self._paper_trades:
            if str(item.get('id')) == str(trade_id):
                item.update(dict(updates or {}))
                return dict(item)
        return None

    async def get_strategy_trade_position(self, position_id):
        item = self._strategy_trade_positions.get(str(position_id))
        return dict(item) if item else None

    async def list_strategy_trade_positions(self, strategy_id=None, account_id=None, code=None, status=None, limit=200):
        rows = [dict(item) for item in self._strategy_trade_positions.values()]
        if strategy_id is not None:
            rows = [item for item in rows if item.get('strategy_id') == strategy_id]
        if account_id is not None:
            rows = [item for item in rows if item.get('account_id') == account_id]
        if code is not None:
            rows = [item for item in rows if item.get('code') == code]
        if status is not None:
            rows = [item for item in rows if item.get('status') == status]
        rows.sort(key=lambda item: str(item.get('closed_at') or item.get('opened_at') or ''))
        return rows[:limit]

    async def save_strategy_trade_position(self, position):
        item = dict(position)
        key = str(item.get('position_id') or '')
        existing = self._strategy_trade_positions.get(key) or {}
        merged = {**existing, **item}
        self._strategy_trade_positions[key] = merged
        return dict(merged)

    async def list_strategy_trade_position_fills(self, *, position_id=None, strategy_id=None, limit=500):
        rows = [dict(item) for item in self._strategy_trade_position_fills]
        if position_id is not None:
            rows = [item for item in rows if item.get('position_id') == position_id]
        if strategy_id is not None:
            rows = [item for item in rows if item.get('strategy_id') == strategy_id]
        rows.sort(key=lambda item: str(item.get('trade_time') or ''))
        return rows[:limit]

    async def save_strategy_trade_position_fill(self, fill):
        item = dict(fill)
        trade_id = str(item.get('trade_id') or '')
        fill_id = str(item.get('fill_id') or '')
        self._strategy_trade_position_fills = [
            row for row in self._strategy_trade_position_fills
            if not (
                (trade_id and str(row.get('trade_id') or '') == trade_id)
                or (fill_id and str(row.get('fill_id') or '') == fill_id)
            )
        ]
        self._strategy_trade_position_fills.append(item)
        return dict(item)

    @staticmethod
    def _aggregate_trade_position(existing, fills):
        return aggregate_trade_position(existing, fills)

    async def _enrich_trade_position_price_path(self, position):
        item = dict(position or {})
        code = str(item.get("code") or "").strip()
        entry_ts = item.get("entry_ts") or item.get("opened_at")
        exit_ts = item.get("exit_ts") or item.get("closed_at") or datetime.now(timezone.utc).isoformat()
        entry_price = float(item.get("entry_avg_price") or 0.0)
        if not code:
            item["price_path_audit_status"] = "missing_kline_source"
            return item
        if not entry_ts or entry_price <= 0:
            item["price_path_audit_status"] = "missing_entry_context"
            return item
        start_date = str(entry_ts)[:10]
        end_date = str(exit_ts)[:10]
        try:
            klines = await self.get_klines(code, start_date=start_date, end_date=end_date)
        except TypeError:
            klines = await self.get_klines(code, limit=200)
        if not klines:
            item["price_path_audit_status"] = "missing_kline"
            return item
        highs = [float(row.get("high") or row.get("close") or 0.0) for row in klines]
        lows = [float(row.get("low") or row.get("close") or 0.0) for row in klines]
        highs = [value for value in highs if value > 0]
        lows = [value for value in lows if value > 0]
        if not highs or not lows:
            item["price_path_audit_status"] = "missing_kline"
            return item
        direction = str(item.get("direction") or "long").strip().lower()
        if direction == "short":
            mfe = max((entry_price - low) / entry_price for low in lows)
            mae = min((entry_price - high) / entry_price for high in highs)
        else:
            mfe = max((high - entry_price) / entry_price for high in highs)
            mae = min((low - entry_price) / entry_price for low in lows)
        item["mfe"] = round(mfe, 6)
        item["mae"] = round(mae, 6)
        item["price_path_audit_status"] = "ok"
        return item

    async def refresh_strategy_trade_position(self, position_id):
        fills = await self.list_strategy_trade_position_fills(position_id=str(position_id), limit=2000)
        if not fills:
            return await self.get_strategy_trade_position(position_id)
        existing = await self.get_strategy_trade_position(position_id)
        aggregate = self._aggregate_trade_position(existing, fills)
        aggregate['position_id'] = str(position_id)
        aggregate = await self._enrich_trade_position_price_path(aggregate)
        return await self.save_strategy_trade_position(aggregate)

    async def backfill_trade_position_links(self, strategy_id=None):
        strategy_filter = str(strategy_id or '').strip() or None
        positions_touched = set()
        order_map = {
            str(item.get('id')): item
            for item in self._paper_orders
            if strategy_filter is None or item.get('strategy_id') == strategy_filter
        }
        for trade in self._paper_trades:
            if strategy_filter is not None and trade.get('strategy_id') != strategy_filter:
                continue
            source_order = order_map.get(str(trade.get('source_order_id') or ''))
            if source_order and source_order.get('position_id'):
                if not trade.get('strategy_id'):
                    trade['strategy_id'] = source_order.get('strategy_id')
                if not trade.get('signal_id'):
                    trade['signal_id'] = source_order.get('signal_id')
                if not trade.get('position_id'):
                    trade['position_id'] = source_order.get('position_id')
            position_id = str(trade.get('position_id') or '').strip()
            if not position_id:
                continue
            await self.save_strategy_trade_position_fill(
                {
                    'fill_id': f"fill_{trade.get('id')}",
                    'position_id': position_id,
                    'trade_id': trade.get('id'),
                    'order_id': trade.get('source_order_id'),
                    'signal_id': trade.get('signal_id'),
                    'strategy_id': trade.get('strategy_id'),
                    'account_id': trade.get('account_id'),
                    'code': trade.get('stock_code'),
                    'fill_side': trade.get('trade_type'),
                    'quantity': int(trade.get('quantity') or 0),
                    'price': float(trade.get('price') or 0.0),
                    'amount': float(trade.get('amount') or 0.0),
                    'commission': float(trade.get('commission') or 0.0),
                    'trade_time': trade.get('trade_time'),
                    'payload': {'source': 'paper_trades_backfill'},
                }
            )
            positions_touched.add(position_id)
        for position_id in positions_touched:
            await self.refresh_strategy_trade_position(position_id)
        return {
            'strategy_id': strategy_filter,
            'position_count': len(positions_touched),
            'fill_count': len(
                [
                    trade for trade in self._paper_trades
                    if (strategy_filter is None or trade.get('strategy_id') == strategy_filter)
                    and str(trade.get('position_id') or '').strip()
                ]
            ),
        }

    async def get_strategy_trade_audit_summary(self, strategy_id):
        manual_summary = dict(self._strategy_trade_audit_summaries.get(strategy_id) or {})
        if manual_summary:
            from akshare_mcp.services.strategy_lifecycle_shared import evaluate_execution_audit_gate

            gate_status, gate_reasons, metric_passes, gate_metrics = evaluate_execution_audit_gate(manual_summary)
            manual_summary.setdefault("approximate", False)
            manual_summary.setdefault("method", "manual_trade_audit_summary")
            manual_summary.setdefault("source_tables", ["strategy_trade_positions"])
            manual_summary.setdefault("mapped_position_count", int(manual_summary.get("realized_trade_count") or 0))
            manual_summary.setdefault("incomplete_position_count", 0)
            manual_summary["audit_grade"] = bool(manual_summary.get("realized_trade_count"))
            manual_summary["audit_ready_for_hard_gate"] = gate_status == "passed"
            manual_summary["execution_audit_gate_status"] = gate_status
            manual_summary["execution_audit_gate_reasons"] = gate_reasons
            manual_summary["hard_gate_metric_passes"] = metric_passes
            manual_summary["hard_gate_metrics"] = gate_metrics
            return manual_summary

        await self.backfill_trade_position_links(strategy_id)
        rows = [
            dict(item) for item in self._strategy_trade_positions.values()
            if item.get('strategy_id') == strategy_id
        ]
        realized_rows = [row for row in rows if row.get('audit_eligible')]
        entry_basis = sum(float(row.get('entry_amount') or 0.0) + float(row.get('entry_commission') or 0.0) for row in realized_rows)
        realized_pnl_total = sum(float(row.get('realized_pnl') or 0.0) for row in realized_rows)
        trade_expectancy = realized_pnl_total / entry_basis if entry_basis > 0 else 0.0
        execution_conversion_efficiency = (
            sum(float(row.get('execution_conversion_efficiency') or 0.0) for row in realized_rows) / len(realized_rows)
            if realized_rows
            else 0.0
        )
        execution_win_rate = (
            sum(1 for row in realized_rows if float(row.get('realized_pnl') or 0.0) > 0) / len(realized_rows)
            if realized_rows
            else 0.0
        )
        wins = [float(row.get('realized_pnl') or 0.0) for row in realized_rows if float(row.get('realized_pnl') or 0.0) > 0]
        losses = [abs(float(row.get('realized_pnl') or 0.0)) for row in realized_rows if float(row.get('realized_pnl') or 0.0) < 0]
        avg_win_loss_ratio = (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if wins and losses else 0.0
        pnl_conversion_efficiency = realized_pnl_total / entry_basis if entry_basis > 0 else 0.0
        realized_trade_count = len(realized_rows)
        summary = {
            'approximate': False,
            'audit_grade': realized_trade_count > 0,
            'method': 'position_id_round_trip_v1',
            'source_tables': ['paper_orders', 'paper_trades', 'strategy_trade_positions', 'strategy_trade_position_fills'],
            'mapped_position_count': len(rows),
            'realized_trade_count': realized_trade_count,
            'incomplete_position_count': len([row for row in rows if not row.get('audit_eligible')]),
            'trade_expectancy': round(trade_expectancy, 6),
            'pnl_conversion_efficiency': round(pnl_conversion_efficiency, 6),
            'execution_conversion_efficiency': round(execution_conversion_efficiency, 6),
            'execution_win_rate': round(execution_win_rate, 6),
            'avg_win_loss_ratio': round(avg_win_loss_ratio, 6),
            'realized_pnl_total': round(realized_pnl_total, 4),
            'audit_ready_for_hard_gate': (
                realized_trade_count >= 20
                and trade_expectancy > 0.0
                and pnl_conversion_efficiency > 0.0
                and execution_conversion_efficiency >= 0.20
            ),
        }
        from akshare_mcp.services.strategy_lifecycle_shared import evaluate_execution_audit_gate

        gate_status, gate_reasons, metric_passes, gate_metrics = evaluate_execution_audit_gate(summary)
        summary['execution_audit_gate_status'] = gate_status
        summary['execution_audit_gate_reasons'] = gate_reasons
        summary['hard_gate_metric_passes'] = metric_passes
        summary['hard_gate_metrics'] = gate_metrics
        summary['audit_ready_for_hard_gate'] = gate_status == 'passed'
        return summary

    async def get_execution_audit_verification(self, strategy_id=None):
        strategy_filter = str(strategy_id or '').strip() or None
        table_presence = {
            table_name: hasattr(self, f"_{table_name}")
            for table_name in _EXECUTION_AUDIT_REQUIRED_TABLES
        }
        column_presence = {
            table_name: {
                column_name: True
                for column_name in required_columns
            }
            for table_name, required_columns in _EXECUTION_AUDIT_REQUIRED_COLUMNS.items()
        }
        migration_presence = {
            migration_key: migration_key in getattr(self, "_market_schema_migrations", set())
            for migration_key in _EXECUTION_AUDIT_REQUIRED_MIGRATIONS
        }

        orders = [
            dict(item) for item in self._paper_orders
            if strategy_filter is None or item.get("strategy_id") == strategy_filter
        ]
        trades = [
            dict(item) for item in self._paper_trades
            if strategy_filter is None or item.get("strategy_id") == strategy_filter
        ]
        candidate_evidence_rows = [
            dict(item) for item in self._strategy_candidate_evidence
            if strategy_filter is None or item.get("strategy_id") == strategy_filter
        ]
        signal_evidence_rows = [
            dict(item) for item in self._strategy_signal_evidence
            if strategy_filter is None or item.get("strategy_id") == strategy_filter
        ]
        fills = [
            dict(item) for item in self._strategy_trade_position_fills
            if strategy_filter is None or item.get("strategy_id") == strategy_filter
        ]
        positions = [
            dict(item) for item in self._strategy_trade_positions.values()
            if strategy_filter is None or item.get("strategy_id") == strategy_filter
        ]
        position_status_counts = {}
        for row in positions:
            status = str(row.get("status") or "unknown")
            position_status_counts[status] = position_status_counts.get(status, 0) + 1

        schema_ok = all(table_presence.values()) and all(
            present
            for table_columns in column_presence.values()
            for present in table_columns.values()
        )
        audit_summary = None
        if strategy_filter and schema_ok:
            audit_summary = await self.get_strategy_trade_audit_summary(strategy_filter)
            positions = await self.list_strategy_trade_positions(
                strategy_id=strategy_filter,
                limit=5000,
            )
            fills = await self.list_strategy_trade_position_fills(
                strategy_id=strategy_filter,
                limit=5000,
            )
            position_status_counts = {}
            for row in positions:
                status = str(row.get("status") or "unknown")
                position_status_counts[status] = position_status_counts.get(status, 0) + 1

        recommendations = []
        missing_tables = [
            table_name for table_name, present in table_presence.items() if not present
        ]
        if missing_tables:
            recommendations.append(
                "missing required execution-audit tables: " + ", ".join(missing_tables)
            )
        missing_migrations = [
            migration_key for migration_key, present in migration_presence.items() if not present
        ]
        if missing_migrations:
            recommendations.append(
                "missing migration/backfill markers: " + ", ".join(missing_migrations)
            )
        orders_with_signal = sum(1 for item in orders if str(item.get("signal_id") or "").strip())
        orders_with_position = sum(1 for item in orders if str(item.get("position_id") or "").strip())
        trades_with_signal = sum(1 for item in trades if str(item.get("signal_id") or "").strip())
        trades_with_position = sum(1 for item in trades if str(item.get("position_id") or "").strip())
        signal_evidence_trade_step_count = sum(
            1 for item in signal_evidence_rows if str(item.get("applied_trade_step_id") or "").strip()
        )
        runtime_action_signal_count = sum(
            1 for item in signal_evidence_rows if str(item.get("runtime_action_reason") or "").strip()
        )
        legacy_evidence_count = len(
            [
                dict(item) for item in self._factory_task_evidence
                if strategy_filter is None
                or str(dict(item.get("evidence_payload") or {}).get("strategy_id") or "").strip() == strategy_filter
            ]
        )
        if orders and orders_with_position < len(orders):
            recommendations.append(
                "paper_orders position_id coverage is incomplete; verify phase_5/6 backfill on production data"
            )
        if trades and trades_with_position < len(trades):
            recommendations.append(
                "paper_trades position_id coverage is incomplete; rerun round-trip linkage/backfill verification"
            )
        if audit_summary and int(audit_summary.get("incomplete_position_count") or 0) > 0:
            recommendations.append(
                "round-trip aggregation still has incomplete positions; inspect refresh_strategy_trade_position/backfill outputs"
            )

        if missing_tables:
            status = "missing_schema"
        elif missing_migrations:
            status = "pending_migration_verification"
        elif recommendations:
            status = "needs_attention"
        else:
            status = "ok"

        def _ratio(numerator, denominator):
            if denominator <= 0:
                return None
            return round(float(numerator) / float(denominator), 6)

        return {
            "status": status,
            "strategy_id": strategy_filter,
            "method": "execution_audit_verification_v1",
            "schema": {
                "required_tables": {
                    table_name: {"present": present}
                    for table_name, present in table_presence.items()
                },
                "required_columns": {
                    table_name: {
                        column_name: {"present": present}
                        for column_name, present in columns.items()
                    }
                    for table_name, columns in column_presence.items()
                },
                "all_required_tables_present": all(table_presence.values()),
                "all_required_columns_present": all(
                    present
                    for table_columns in column_presence.values()
                    for present in table_columns.values()
                ),
            },
            "migrations": {
                "tracking_table_present": True,
                "required_keys": {
                    migration_key: {"applied": present}
                    for migration_key, present in migration_presence.items()
                },
                "all_required_keys_applied": all(migration_presence.values()),
            },
            "coverage": {
                "paper_orders": {
                    "total": len(orders),
                    "signal_id_linked": orders_with_signal,
                    "position_id_linked": orders_with_position,
                    "signal_id_ratio": _ratio(orders_with_signal, len(orders)),
                    "position_id_ratio": _ratio(orders_with_position, len(orders)),
                },
                "paper_trades": {
                    "total": len(trades),
                    "signal_id_linked": trades_with_signal,
                    "position_id_linked": trades_with_position,
                    "signal_id_ratio": _ratio(trades_with_signal, len(trades)),
                    "position_id_ratio": _ratio(trades_with_position, len(trades)),
                },
                "strategy_candidate_evidence_count": len(candidate_evidence_rows),
                "strategy_signal_evidence_count": len(signal_evidence_rows),
                "strategy_signal_step_lineage_count": signal_evidence_trade_step_count,
                "runtime_action_signal_count": runtime_action_signal_count,
            },
            "lineage_source": {
                "status": (
                    "native_ready"
                    if len(candidate_evidence_rows) > 0 or len(signal_evidence_rows) > 0
                    else "legacy_only"
                    if legacy_evidence_count > 0
                    else "missing"
                ),
                "native_candidate_evidence_count": len(candidate_evidence_rows),
                "native_signal_evidence_count": len(signal_evidence_rows),
                "native_trade_step_lineage_count": signal_evidence_trade_step_count,
                "runtime_action_signal_count": runtime_action_signal_count,
                "legacy_evidence_count": legacy_evidence_count,
            },
            "trade_round_trip": {
                "position_count": len(positions),
                "fill_count": len(fills),
                "position_status_counts": position_status_counts,
                "audit_summary": audit_summary,
            },
            "recommendations": recommendations,
        }

    async def save_paper_nav(self, nav):
        item = dict(nav)
        rows = [row for row in self._paper_nav.get(item['account_id'], []) if str(row.get('nav_date')) != str(item.get('nav_date'))]
        rows.append(item)
        self._paper_nav[item['account_id']] = rows
        return dict(item)

    async def get_paper_nav_rows(self, account_id, limit=60):
        rows = list(self._paper_nav.get(account_id, []))
        rows.sort(key=lambda row: row.get('nav_date') or '', reverse=True)
        return rows[:limit]

    async def get_paper_order_summary(self, account_id):
        orders = [item for item in self._paper_orders if item.get('account_id') == account_id]
        trades = [item for item in self._paper_trades if item.get('account_id') == account_id]
        return {
            'total_orders': len(orders),
            'filled_orders': len([item for item in orders if item.get('status') == 'filled']),
            'total_trades': len(trades),
            'trade_amount': float(sum(item.get('amount') or 0 for item in trades)),
        }

    async def save_strategy_incubation_account(self, strategy_id, account_id, stage='warmup', status='active', source_run_id=None, metadata=None):
        item = {
            'id': len(self._incubation_accounts) + 1,
            'strategy_id': strategy_id,
            'account_id': account_id,
            'stage': stage,
            'status': status,
            'source_run_id': source_run_id,
            'metadata': metadata or {},
        }
        self._incubation_accounts = [row for row in self._incubation_accounts if not (row.get('strategy_id') == strategy_id and row.get('account_id') == account_id)]
        self._incubation_accounts.append(item)
        return dict(item)

    async def get_strategy_incubation_account(self, strategy_id, account_id=None):
        rows = [row for row in self._incubation_accounts if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        return dict(rows[-1]) if rows else None

    async def list_strategy_incubation_accounts(self, strategy_id=None, status=None, limit=20):
        rows = list(self._incubation_accounts)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_incubation_metric(self, strategy_id, metric_date, metric):
        item = {'strategy_id': strategy_id, 'metric_date': str(metric_date), **dict(metric)}
        self._incubation_metrics = [row for row in self._incubation_metrics if not (row.get('strategy_id') == strategy_id and row.get('metric_date') == str(metric_date))]
        self._incubation_metrics.append(item)
        self._incubation_metrics.sort(key=lambda row: row.get('metric_date') or '', reverse=True)
        return dict(item)

    async def get_latest_strategy_incubation_metric(self, strategy_id):
        rows = await self.list_strategy_incubation_metrics(strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_metrics(self, strategy_id, limit=30, start_date=None, end_date=None):
        rows = [row for row in self._incubation_metrics if row.get('strategy_id') == strategy_id]
        if start_date:
            rows = [row for row in rows if row.get('metric_date') >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row.get('metric_date') <= str(end_date)]
        rows.sort(key=lambda row: row.get('metric_date') or '', reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_incubation_pipeline_snapshot(self, snapshot):
        item = {'id': len(self._incubation_pipeline_snapshots) + 1, **dict(snapshot)}
        self._incubation_pipeline_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_incubation_pipeline_snapshot(self, strategy_id):
        rows = await self.list_strategy_incubation_pipeline_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_pipeline_snapshots(self, strategy_id=None, pipeline_stage=None, pipeline_status=None, limit=20):
        rows = list(self._incubation_pipeline_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if pipeline_stage:
            rows = [row for row in rows if row.get('pipeline_stage') == pipeline_stage]
        if pipeline_status:
            rows = [row for row in rows if row.get('pipeline_status') == pipeline_status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_risk_event(self, event):
        item = {'id': len(self._risk_events) + 1, **dict(event)}
        self._risk_events.append(item)
        return dict(item)

    async def list_strategy_runtime_risk_events(self, strategy_id=None, account_id=None, status=None, severity=None, limit=50):
        rows = list(self._risk_events)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        if status:
            rows = [row for row in rows if row.get('status', 'open') == status]
        if severity:
            rows = [row for row in rows if row.get('severity') == severity]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_risk_snapshot(self, snapshot):
        item = {'id': len(self._runtime_risk_snapshots) + 1, **dict(snapshot)}
        self._runtime_risk_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_runtime_risk_snapshot(self, strategy_id):
        rows = await self.list_strategy_runtime_risk_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_risk_snapshots(self, strategy_id=None, posture_level=None, control_mode=None, limit=20):
        rows = list(self._runtime_risk_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if posture_level:
            rows = [row for row in rows if row.get('posture_level') == posture_level]
        if control_mode:
            rows = [row for row in rows if row.get('control_mode') == control_mode]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_runtime_alert(self, alert):
        existing = None
        alert_id = alert.get('alert_id')
        if alert_id is not None:
            for item in self._runtime_alerts:
                if int(item.get('alert_id')) == int(alert_id):
                    existing = item
                    break
        now = datetime.now(timezone.utc).isoformat()
        if existing is not None:
            existing.update(dict(alert))
            existing['updated_at'] = now
            if existing.get('status') == 'resolved' and not existing.get('resolved_at'):
                existing['resolved_at'] = now
            return dict(existing)
        item = {
            'status': 'open',
            'channels': [],
            'related_event_ids': [],
            'metadata': {},
            'created_at': now,
            'updated_at': now,
            **{k: v for k, v in dict(alert).items() if not (k == 'alert_id' and v is None)},
            'alert_id': len(self._runtime_alerts) + 1,
        }
        self._runtime_alerts.insert(0, item)
        return dict(item)

    async def get_latest_strategy_runtime_alert(self, strategy_id, alert_key=None, category=None, status='open_or_ack'):
        rows = await self.list_strategy_runtime_alerts(strategy_id=strategy_id, alert_key=alert_key, category=category, status=status, limit=1)
        return rows[0] if rows else None

    async def list_strategy_runtime_alerts(self, strategy_id=None, account_id=None, category=None, severity=None, status=None, alert_key=None, limit=50):
        rows = list(self._runtime_alerts)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if account_id:
            rows = [row for row in rows if row.get('account_id') == account_id]
        if category:
            rows = [row for row in rows if row.get('category') == category]
        if severity:
            rows = [row for row in rows if row.get('severity') == severity]
        if alert_key:
            rows = [row for row in rows if row.get('alert_key') == alert_key]
        if status:
            if status == 'open_or_ack':
                rows = [row for row in rows if row.get('status', 'open') in {'open', 'acknowledged'}]
            else:
                rows = [row for row in rows if row.get('status', 'open') == status]
        rows = sorted(rows, key=lambda row: row.get('updated_at') or row.get('created_at') or '', reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def acknowledge_strategy_runtime_alert(self, alert_id, acknowledged_by=None, source='runtime_alerts'):
        now = datetime.now(timezone.utc).isoformat()
        for item in self._runtime_alerts:
            if int(item.get('alert_id')) == int(alert_id):
                if item.get('status') != 'resolved':
                    item['status'] = 'acknowledged'
                item['acknowledged_by'] = acknowledged_by
                item['acknowledged_at'] = item.get('acknowledged_at') or now
                item['updated_at'] = now
                item['metadata'] = {**dict(item.get('metadata') or {}), 'ack_source': source}
                return dict(item)
        return None

    async def resolve_strategy_runtime_alerts(self, strategy_id=None, alert_id=None, alert_key=None, category=None, resolution=None, source='runtime_alerts'):
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for item in self._runtime_alerts:
            if item.get('status', 'open') == 'resolved':
                continue
            if strategy_id and item.get('strategy_id') != strategy_id:
                continue
            if alert_id is not None and int(item.get('alert_id')) != int(alert_id):
                continue
            if alert_key and item.get('alert_key') != alert_key:
                continue
            if category and item.get('category') != category:
                continue
            item['status'] = 'resolved'
            item['resolved_at'] = item.get('resolved_at') or now
            item['updated_at'] = now
            item['metadata'] = {**dict(item.get('metadata') or {}), 'resolution': resolution or {}, 'resolution_source': source}
            rows.append(dict(item))
        return rows

    async def save_strategy_runtime_control(self, control):
        existing = self._runtime_controls.get(control['strategy_id'])
        item = {
            'id': (existing or {}).get('id', len(self._runtime_controls) + 1),
            **dict(existing or {}),
            **dict(control),
        }
        self._runtime_controls[item['strategy_id']] = item
        return dict(item)

    async def get_strategy_runtime_control(self, strategy_id):
        item = self._runtime_controls.get(strategy_id)
        return dict(item) if item else None

    async def list_strategy_runtime_controls(self, strategy_id=None, control_mode=None, status=None, limit=50):
        rows = list(self._runtime_controls.values())
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if control_mode:
            rows = [row for row in rows if row.get('control_mode') == control_mode]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_promotion_review(self, review):
        item = {'id': len(self._promotion_reviews) + 1, **dict(review)}
        self._promotion_reviews.append(item)
        return dict(item)

    async def get_latest_strategy_promotion_review(self, strategy_id):
        rows = [row for row in self._promotion_reviews if row.get('strategy_id') == strategy_id]
        return dict(rows[-1]) if rows else None

    async def list_strategy_promotion_reviews(self, strategy_id=None, status=None, limit=50):
        rows = list(self._promotion_reviews)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        rows = list(reversed(rows))
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_projection_snapshot(self, snapshot):
        item = {'id': len(self._projection_snapshots) + 1, **dict(snapshot)}
        self._projection_snapshots.append(item)
        return dict(item)

    async def get_latest_strategy_projection_snapshot(self, strategy_id, projection_type='strategy_state'):
        rows = [row for row in self._projection_snapshots if row.get('strategy_id') == strategy_id and row.get('projection_type', 'strategy_state') == projection_type]
        return dict(rows[-1]) if rows else None

    async def list_strategy_projection_snapshots(self, strategy_id=None, projection_type=None, limit=50):
        rows = list(self._projection_snapshots)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if projection_type:
            rows = [row for row in rows if row.get('projection_type') == projection_type]
        rows = list(reversed(rows))
        return [dict(row) for row in rows[:limit]]

    async def resolve_strategy_runtime_risk_event(self, event_id, resolution=None):
        for item in self._risk_events:
            if int(item.get('id')) == int(event_id):
                item['status'] = 'resolved'
                item['resolution'] = resolution or {}
                return dict(item)
        return None
