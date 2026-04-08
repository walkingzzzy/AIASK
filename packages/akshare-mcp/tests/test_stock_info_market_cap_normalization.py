import pytest

from akshare_mcp.storage.timescaledb.stock_info import StockInfoMixin


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, *, max_market_cap, stock_row=None, list_rows=None, count_total=0):
        self.max_market_cap = max_market_cap
        self.stock_row = stock_row or {}
        self.list_rows = list_rows or []
        self.count_total = count_total
        self.last_fetch_args = None
        self.last_fetchrow_args = None
        self.stock_list_args = None
        self.count_args = None

    async def fetch(self, query, *args):
        self.last_fetch_args = (query, args)
        if "information_schema.columns" in query:
            return [
                {"column_name": "code"},
                {"column_name": "stock_name"},
                {"column_name": "industry"},
                {"column_name": "market_cap"},
                {"column_name": "pe_ratio"},
                {"column_name": "pb_ratio"},
                {"column_name": "list_date"},
            ]
        if "FROM stocks" in query:
            self.stock_list_args = args
        return list(self.list_rows)

    async def fetchrow(self, query, *args):
        self.last_fetchrow_args = (query, args)
        if "MAX(market_cap)" in query:
            return {"max_market_cap": self.max_market_cap}
        if "COUNT(*) AS total" in query:
            self.count_args = args
            return {"total": self.count_total}
        return dict(self.stock_row)


class _Db(StockInfoMixin):
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


@pytest.mark.asyncio
async def test_market_cap_reads_normalize_wan_yuan_storage():
    conn = _Conn(
        max_market_cap=252_335_630.019,
        stock_row={
            "code": "601398",
            "stock_name": "工商银行",
            "industry": "银行",
            "market_cap": 252_335_630.019,
            "pe_ratio": 6.897,
            "pb_ratio": 0.6687,
            "list_date": None,
        },
        list_rows=[
            {
                "code": "601398",
                "stock_name": "工商银行",
                "industry": "银行",
                "market_cap": 252_335_630.019,
                "pe_ratio": 6.897,
                "pb_ratio": 0.6687,
                "list_date": None,
            }
        ],
        count_total=12,
    )
    db = _Db(conn)

    stock = await db.get_stock_info("601398")
    universe = await db.list_stock_universe(limit=1, min_market_cap=30_000_000_000)
    total = await db.count_stock_universe(min_market_cap=30_000_000_000)

    assert stock["market_cap"] == pytest.approx(2_523_356_300_190.0)
    assert universe[0]["market_cap"] == pytest.approx(2_523_356_300_190.0)
    assert total == 12
    assert conn.stock_list_args[0] == pytest.approx(3_000_000.0)
    assert conn.count_args[0] == pytest.approx(3_000_000.0)


@pytest.mark.asyncio
async def test_market_cap_reads_leave_yuan_storage_unchanged():
    conn = _Conn(
        max_market_cap=2_673_046_928_168.0,
        stock_row={
            "code": "601398",
            "stock_name": "工商银行",
            "industry": "银行",
            "market_cap": 2_673_046_928_168.0,
            "pe_ratio": 6.897,
            "pb_ratio": 0.6687,
            "list_date": None,
        },
    )
    db = _Db(conn)

    stock = await db.get_stock_info("601398")

    assert stock["market_cap"] == pytest.approx(2_673_046_928_168.0)
