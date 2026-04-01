from ._test_p0_regressions_support import *


@pytest.mark.asyncio
async def test_p0_10_search_similar_stocks_should_fallback_to_market_candidates(monkeypatch):
    class _VectorConn:
        def __init__(self):
            self.calls = []

        async def fetch(self, query, *args):
            self.calls.append(query)
            if 'WHERE industry = $1' in query:
                return []
            if 'WHERE code != $1' in query:
                return [{'code': '000001', 'stock_name': '平安银行'}]
            return []

    class _VectorDB:
        def __init__(self, conn):
            self.conn = conn

        def acquire(self):
            return _Acquire(self.conn)

        async def get_stock_info(self, code):
            if code == '600519':
                return {'name': '贵州茅台', 'industry': '白酒', 'pe_ratio': 20.0, 'pb_ratio': 5.0}
            if code == '000001':
                return {'name': '平安银行', 'industry': '银行', 'pe_ratio': 6.0, 'pb_ratio': 0.8}
            return None

        async def get_financials(self, code, limit=1):
            return []

        async def get_klines(self, code, limit=60):
            return []

    conn = _VectorConn()
    mcp = _DummyMCP()
    vector_mod.register(mcp)
    monkeypatch.setattr(vector_mod, 'get_db', lambda: _VectorDB(conn))

    result = await mcp.search_similar_stocks('600519', top_n=5, similarity_type='fundamental')
    assert result['success'] is True
    data = result['data']
    assert data['candidate_scope'] == 'market'
    assert data['total_candidates'] == 1
    assert data['similar_stocks'][0]['code'] == '000001'
    assert any('WHERE industry = $1' in query for query in conn.calls)
    assert any('WHERE code != $1' in query for query in conn.calls)


@pytest.mark.asyncio
async def test_p0_11_calculate_factor_should_accept_aliases(monkeypatch):
    class _QuantDB:
        async def get_klines(self, code, limit=100):
            return [{'close': float(i)} for i in range(1, 80)]

        async def get_financials(self, code, limit=1):
            return [{'roe': 18.0, 'debt_ratio': 30.0, 'profit_growth': 10.0}]

        async def get_stock_info(self, code):
            return {'market_cap': 1000000000.0}

    mcp = _DummyMCP()
    quant_mod.register(mcp)
    monkeypatch.setattr(quant_mod, 'get_db', lambda: _QuantDB())

    rsi_res = await mcp.calculate_factor('600519', 'rsi')
    assert rsi_res['success'] is True
    assert rsi_res['data']['factor'] == 'rsi_14'

    mom_res = await mcp.calculate_factor('600519', 'momentum_20d')
    assert mom_res['success'] is True
    assert mom_res['data']['factor'] == 'momentum'


@pytest.mark.asyncio
async def test_p0_12_research_manager_should_normalize_limit(monkeypatch):
    captured = {}

    def _fake_get_stock_research(code, limit=10):
        captured['limit'] = limit
        return {
            'success': True,
            'data': {
                'reports': [{'title': 'r1'}, {'title': 'r2'}][:limit],
                'total': min(limit, 2),
            },
        }

    mcp = _DummyMCP()
    research_manager_mod.register_research_manager(mcp)
    monkeypatch.setattr(research_manager_mod, 'get_db', lambda: object())
    monkeypatch.setattr(news_mod, 'get_stock_research', _fake_get_stock_research)

    result = await mcp.research_manager(action='get_reports', code='600519', kwargs='{"limit": "2"}')
    assert result['success'] is True
    assert captured['limit'] == 2
    assert result['data']['count'] == 2


@pytest.mark.asyncio
async def test_p0_13_sector_manager_should_accept_days_alias(monkeypatch):
    class _SectorConn:
        async def fetch(self, query, *args):
            if 'FROM market_blocks WHERE block_type' in query:
                return [{'block_code': 'BK001', 'block_name': '半导体'}]
            if 'FROM block_stocks WHERE block_code' in query:
                return [{'stock_code': '600519'}]
            return []

    class _SectorDB:
        def acquire(self):
            return _Acquire(_SectorConn())

        async def get_klines(self, code, limit=31):
            return [{'close': 100.0}, {'close': 110.0}]

    mcp = _DummyMCP()
    sector_manager_mod.register_sector_manager(mcp)
    monkeypatch.setattr(sector_manager_mod, 'get_db', lambda: _SectorDB())

    result = await mcp.sector_manager(action='sector_rotation', kwargs='{"days": "30"}')
    assert result['success'] is True
    assert result['data']['period'] == 30


@pytest.mark.asyncio
async def test_p0_14_market_insight_sector_analysis_should_filter_requested_sector(monkeypatch):
    mcp = _DummyMCP()
    market_insight_manager_mod.register_market_insight_manager(mcp)

    monkeypatch.setattr(fund_flow_mod, 'get_sector_fund_flow', lambda top_n=10: {
        'success': True,
        'data': [
            {'name': '半导体', 'mainNetInflow': 12.3},
            {'name': '银行', 'mainNetInflow': -2.0},
        ],
    })
    monkeypatch.setattr(fund_flow_mod, 'get_concept_fund_flow', lambda top_n=5: {
        'success': True,
        'data': [
            {'name': 'AI芯片', 'mainNetInflow': 8.8},
            {'name': '白酒', 'mainNetInflow': -1.0},
        ],
    })

    result = await mcp.market_insight_manager(action='sector_analysis', kwargs='{"sector": "半导体"}')
    assert result['success'] is True
    data = result['data']
    assert data['requestedSector'] == '半导体'
    assert data['matchedCount'] == 1
    assert data['hotSectors'][0]['name'] == '半导体'


@pytest.mark.asyncio
async def test_p0_14b_data_warmup_should_accept_comma_separated_stock_string(monkeypatch):
    mcp = _DummyMCP()
    data_warmup_mod.register(mcp)

    captured = {}

    async def _fake_sync_stock_klines(*, codes, start_date, end_date, period):
        captured['codes'] = list(codes)
        captured['start_date'] = start_date
        captured['end_date'] = end_date
        captured['period'] = period
        return {'synced': len(codes), 'failed': 0, 'total': len(codes)}

    monkeypatch.setattr(data_warmup_mod.data_sync_service, 'sync_stock_klines', _fake_sync_stock_klines)

    result = await mcp.data_warmup(
        action='warmup',
        stocks='600519, 000001, 600519',
        lookback_days=30,
    )

    assert result['success'] is True
    assert result['data']['stocks_warmed'] == 2
    assert captured['codes'] == ['600519', '000001']
    assert captured['period'] == 'daily'


@pytest.mark.asyncio
async def test_p0_15_comprehensive_manager_quick_scan_should_honor_single_code(monkeypatch):
    class _ComprehensiveDB:
        async def get_klines(self, code, limit=1):
            if code == '600519':
                return [{'date': '2026-02-01', 'close': 100.0, 'change_pct': 1.2, 'volume': 12345}]
            return []

    mcp = _DummyMCP()
    comprehensive_manager_mod.register_comprehensive_manager(mcp)
    monkeypatch.setattr(comprehensive_manager_mod, 'get_db', lambda: _ComprehensiveDB())

    result = await mcp.comprehensive_manager(action='quick_scan', code='600519')
    assert result['success'] is True
    assert result['data']['scanned'] == 1
    assert result['data']['results'][0]['code'] == '600519'


@pytest.mark.asyncio
async def test_p0_16_alerts_manager_update_should_preserve_status_when_status_missing(monkeypatch):
    alerts_tool_mod._alerts_store.clear()
    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)

    created = await mcp.alerts_manager(action='create', code='600519', indicator='price', condition='>', value=1800)
    assert created['success'] is True
    alert_id = created['data']['alert_id']

    updated = await mcp.alerts_manager(action='update', alert_id=alert_id, value=1900)
    assert updated['success'] is True
    assert updated['data']['status'] == 'active'
    assert updated['data']['alert']['value'] == pytest.approx(1900.0)
    assert alerts_tool_mod._alerts_store[alert_id]['active'] is True


@pytest.mark.asyncio
async def test_p0_16a_alerts_manager_accepts_structured_params(monkeypatch):
    alerts_tool_mod._alerts_store.clear()
    mcp = _DummyMCP()
    alerts_manager_mod.register_alerts_manager(mcp)

    created = await mcp.alerts_manager(
        action='create',
        params={'code': '600519', 'indicator': 'price', 'condition': '>', 'value': 1800},
    )
    assert created['success'] is True

    listed = await mcp.alerts_manager(action='list', params={'status': 'active'})
    assert listed['success'] is True
    assert listed['data']['count'] >= 1


@pytest.mark.asyncio
async def test_p0_17_search_stocks_should_match_industry_keyword(monkeypatch):
    class _SearchConn:
        async def fetch(self, query, *args):
            assert 'industry IS NOT NULL' in query
            return [
                {'code': '600519', 'stock_name': '贵州茅台', 'industry': '白酒', 'market_cap': 123.0}
            ]

    class _SearchDB:
        def acquire(self):
            return _Acquire(_SearchConn())

    mcp = _DummyMCP()
    search_mod.register(mcp)
    monkeypatch.setattr(search_mod, 'get_db', lambda: _SearchDB())

    result = await mcp.search_stocks(keyword='白酒', limit=5)
    assert result['success'] is True
    assert result['data']['count'] == 1
    assert result['data']['results'][0]['industry'] == '白酒'


def test_p0_18_search_stocks_tushare_fallback_should_match_industry_keyword(monkeypatch):
    class _SimpleDF:
        empty = False

        def iterrows(self):
            yield 0, {'ts_code': '600519.SH', 'symbol': '600519', 'name': '贵州茅台', 'industry': '白酒'}

    class _FakePro:
        def stock_basic(self, **kwargs):
            return _SimpleDF()

    monkeypatch.setattr(search_mod.data_source, 'get_tushare_pro', lambda: _FakePro())
    results = search_mod._search_stocks_tushare_fallback('白酒', 5)
    assert len(results) == 1
    assert results[0]['code'] == '600519'


@pytest.mark.asyncio
async def test_p0_19_semantic_stock_search_should_prioritize_industry_match(monkeypatch):
    class _VectorConn:
        async def fetch(self, query, *args):
            if 'WHERE industry IS NOT NULL AND LOWER(industry) LIKE $1' in query:
                assert args[0] == '%白酒%'
                return [
                    {'code': '600519', 'stock_name': '贵州茅台', 'industry': '白酒', 'market_cap': 100.0, 'pe_ratio': 30.0, 'pb_ratio': 8.0},
                    {'code': '000858', 'stock_name': '五粮液', 'industry': '白酒', 'market_cap': 90.0, 'pe_ratio': 25.0, 'pb_ratio': 6.0},
                ]
            return [
                {'code': '600630', 'stock_name': '龙头股份', 'industry': '纺织服饰', 'market_cap': 10.0, 'pe_ratio': 10.0, 'pb_ratio': 1.0},
            ]

    class _VectorDB:
        def acquire(self):
            return _Acquire(_VectorConn())

    mcp = _DummyMCP()
    vector_mod.register(mcp)
    monkeypatch.setattr(vector_mod, 'get_db', lambda: _VectorDB())

    result = await mcp.semantic_stock_search(query='白酒龙头', limit=3)
    assert result['success'] is True
    assert result['data']['results'][0]['code'] == '600519'
    assert result['data']['results'][0]['industry'] == '白酒'
    returned_codes = [item['code'] for item in result['data']['results']]
    assert '000858' in returned_codes
    if '600630' in returned_codes:
        leader = next(item for item in result['data']['results'] if item['code'] == '600630')
        assert leader['score'] < result['data']['results'][0]['score']


@pytest.mark.asyncio
async def test_p0_19b_semantic_stock_search_should_not_match_single_char_sector_fallback(monkeypatch):
    class _EmptyConn:
        async def fetch(self, query, *args):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

        def head(self, count):
            return _Frame(self._rows[:count])

    def _stock_sector_detail(sector):
        if sector == 'new_whitewine':
            return _Frame([{'code': '600519', 'name': '贵州茅台'}])
        if sector == 'new_tourism':
            return _Frame([{'code': '600054', 'name': '黄山旅游'}])
        return _Frame([])

    monkeypatch.setattr(vector_mod, 'get_db', lambda: _EmptyDB())
    monkeypatch.setattr(
        akshare,
        'stock_sector_spot',
        lambda: _Frame([
            {'板块': '酒店旅游', 'label': 'new_tourism'},
            {'板块': '白酒概念', 'label': 'new_whitewine'},
        ]),
        raising=False,
    )
    monkeypatch.setattr(akshare, 'stock_board_industry_name_ths', lambda: _Frame([]), raising=False)
    monkeypatch.setattr(akshare, 'stock_sector_detail', _stock_sector_detail, raising=False)
    monkeypatch.setitem(sys.modules, 'akshare', akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query='白酒', limit=5)

    assert result['success'] is True
    returned_codes = [item['code'] for item in result['data']['results']]
    assert '600519' in returned_codes
    assert '600054' not in returned_codes
    assert result['data']['results'][0]['code'] == '600519'
    assert result['data']['results'][0]['match_type']


@pytest.mark.asyncio
async def test_p0_19c_semantic_stock_search_should_use_ths_concept_constituents(monkeypatch):
    class _EmptyConn:
        async def fetch(self, query, *args):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

    def _concept_rows(block_code, block_name):
        assert block_code == '301496'
        assert block_name == '白酒概念'
        return [
            {'stock_code': '600519', 'stock_name': '贵州茅台'},
            {'stock_code': '000858', 'stock_name': '五粮液'},
        ]

    monkeypatch.setattr(vector_mod, 'get_db', lambda: _EmptyDB())
    monkeypatch.setattr(akshare, 'stock_sector_spot', lambda: _Frame([]), raising=False)
    monkeypatch.setattr(akshare, 'stock_board_industry_name_ths', lambda: _Frame([]), raising=False)
    monkeypatch.setattr(
        akshare,
        'stock_board_concept_name_ths',
        lambda: _Frame([{'name': '白酒概念', 'code': '301496'}]),
        raising=False,
    )
    monkeypatch.setattr(market_blocks_mod, '_fetch_concept_stocks_from_ths', _concept_rows)
    monkeypatch.setitem(sys.modules, 'akshare', akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query='白酒', limit=5)

    assert result['success'] is True
    returned_codes = [item['code'] for item in result['data']['results']]
    assert returned_codes[:2] == ['600519', '000858']
    assert all('industry' in item for item in result['data']['results'])
    assert result['data']['results'][0]['industry'] == '白酒概念'


@pytest.mark.asyncio
async def test_p0_19d_semantic_stock_search_should_not_leak_akshare_stdout(monkeypatch, capsys):
    class _EmptyConn:
        async def fetch(self, query, *args):
            return []

    class _EmptyDB:
        def acquire(self):
            return _Acquire(_EmptyConn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

        def head(self, count):
            return _Frame(self._rows[:count])

    def _noisy_sector_spot():
        print("sector spot progress should not reach stdout")
        return _Frame([])

    def _noisy_industry_names():
        print("industry ths progress should not reach stdout")
        return _Frame([])

    def _noisy_concept_names():
        print("concept ths progress should not reach stdout")
        return _Frame([{'name': '白酒概念', 'code': '301496'}])

    def _concept_rows(block_code, block_name):
        return [{'stock_code': '600519', 'stock_name': '贵州茅台'}]

    monkeypatch.setattr(vector_mod, 'get_db', lambda: _EmptyDB())
    monkeypatch.setattr(akshare, 'stock_sector_spot', _noisy_sector_spot, raising=False)
    monkeypatch.setattr(akshare, 'stock_board_industry_name_ths', _noisy_industry_names, raising=False)
    monkeypatch.setattr(akshare, 'stock_board_concept_name_ths', _noisy_concept_names, raising=False)
    monkeypatch.setattr(market_blocks_mod, '_fetch_concept_stocks_from_ths', _concept_rows)
    monkeypatch.setitem(sys.modules, 'akshare', akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query='白酒', limit=5)
    captured = capsys.readouterr()

    assert result['success'] is True
    assert result['data']['results'][0]['code'] == '600519'
    assert captured.out == ''


def test_p0_19e_market_blocks_ths_should_not_leak_akshare_stdout(monkeypatch, capsys):
    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

    def _noisy_concept_names():
        print("market blocks concept progress should not reach stdout")
        return _Frame([{'name': '白酒概念', 'code': '301496'}])

    monkeypatch.setattr(market_blocks_mod.ak, 'stock_board_concept_name_ths', _noisy_concept_names, raising=False)

    result = market_blocks_mod._fetch_from_ths('concept')
    captured = capsys.readouterr()

    assert result
    assert result[0]['block_code'] == '301496'
    assert captured.out == ''


@pytest.mark.asyncio
async def test_p0_20_event_manager_should_fallback_to_content_sources(monkeypatch):
    class _EventConn:
        async def fetch(self, query, *args):
            return []

    class _EventDB:
        def acquire(self):
            return _Acquire(_EventConn())

    mcp = _DummyMCP()
    event_manager_mod.register_event_manager(mcp)
    monkeypatch.setattr(event_manager_mod, 'get_db', lambda: _EventDB())
    monkeypatch.setattr(event_manager_mod, 'get_stock_news', lambda code, limit=10: {
        'success': True,
        'data': [{'title': '宁德时代获机构关注', 'date': '2026-03-03', 'source': '新闻源'}],
    })
    monkeypatch.setattr(event_manager_mod, 'get_stock_notices', lambda **kwargs: {
        'success': True,
        'data': {'events': [{'title': '宁德时代年度报告', 'date': '2026-03-02', 'source': '公告'}]},
    })
    monkeypatch.setattr(event_manager_mod, 'get_stock_research', lambda code, limit=10: {
        'success': True,
        'data': {'reports': [{'title': '维持买入评级', 'date': '2026-03-01', 'institution': '机构A'}]},
    })
    monkeypatch.setattr(event_manager_mod, 'get_research_reports', lambda **kwargs: {'success': True, 'data': []})

    result = await mcp.event_manager(action='get_by_code', kwargs='{"code":"300750"}')
    assert result['success'] is True
    assert result['data']['source'] == 'aggregated_content'
    assert result['data']['fallback_used'] is True
    assert result['data']['count'] == 3
    assert {item['event_type'] for item in result['data']['events']} == {'news', 'notice', 'research'}


@pytest.mark.asyncio
async def test_p0_21_relative_valuation_should_fallback_to_market_peers_when_industry_missing(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, *args):
            if 'ORDER BY ABS(COALESCE(market_cap, 0) - $2) ASC' in query:
                return [
                    {'code': 'P1'}, {'code': 'P2'}, {'code': 'P3'}, {'code': 'P4'}, {'code': 'P5'}
                ]
            return []

    class _ValuationDB:
        def __init__(self):
            self.stock_info = {
                'TGT': {'name': '目标公司', 'industry': None, 'market_cap': 100.0, 'pe_ratio': 20.0, 'pb_ratio': 3.0},
                'P1': {'name': '同业1', 'market_cap': 95.0, 'pe_ratio': 15.0, 'pb_ratio': 2.0},
                'P2': {'name': '同业2', 'market_cap': 98.0, 'pe_ratio': 16.0, 'pb_ratio': 2.1},
                'P3': {'name': '同业3', 'market_cap': 102.0, 'pe_ratio': 17.0, 'pb_ratio': 2.2},
                'P4': {'name': '同业4', 'market_cap': 105.0, 'pe_ratio': 18.0, 'pb_ratio': 2.3},
                'P5': {'name': '同业5', 'market_cap': 110.0, 'pe_ratio': 19.0, 'pb_ratio': 2.4},
            }
            self.financials = {
                code: [{'roe': 0.15, 'debt_ratio': 0.4, 'revenue_yoy': 0.12, 'operating_cash_flow': 120.0, 'net_profit': 100.0}]
                for code in ['TGT', 'P1', 'P2', 'P3', 'P4', 'P5']
            }

        def acquire(self):
            return _Acquire(_ValuationConn())

        async def get_stock_info(self, code):
            return self.stock_info.get(code)

        async def get_financials(self, code, limit=1):
            rows = self.financials.get(code, [])
            return rows[:limit]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _ValuationDB())

    result = await mcp.relative_valuation('TGT')
    assert result['success'] is True
    assert result['data']['peer_count'] == 5
    assert result['data']['peer_pool_build']['peer_source'] == 'market_cap_fallback'
    assert 'industry_missing' in result['data']['peer_pool_build']['fallback_reasons']


@pytest.mark.asyncio
async def test_p0_21b_relative_valuation_tracks_invalid_metrics_and_alias_financials(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, *args):
            if 'WHERE industry = $1 AND code != $2' in query:
                return [
                    {'code': 'P1'}, {'code': 'P2'}, {'code': 'P3'}, {'code': 'P4'}, {'code': 'P5'}
                ]
            return []

    class _ValuationDB:
        def __init__(self):
            self.stock_info = {
                'TGT': {'name': '目标公司', 'industry': '白酒', 'market_cap': 100.0, 'pe_ratio': 0.0, 'pb_ratio': 3.0, 'ps_ratio': -1.0},
                'P1': {'name': '同业1', 'market_cap': 95.0, 'pe_ratio': 15.0, 'pb_ratio': 2.0, 'ps_ratio': 1.0},
                'P2': {'name': '同业2', 'market_cap': 98.0, 'pe_ratio': 16.0, 'pb_ratio': 2.1, 'ps_ratio': 1.1},
                'P3': {'name': '同业3', 'market_cap': 102.0, 'pe_ratio': 17.0, 'pb_ratio': 2.2, 'ps_ratio': 1.2},
                'P4': {'name': '同业4', 'market_cap': 105.0, 'pe_ratio': 18.0, 'pb_ratio': 2.3, 'ps_ratio': 1.3},
                'P5': {'name': '同业5', 'market_cap': 110.0, 'pe_ratio': 19.0, 'pb_ratio': 0.0, 'ps_ratio': 1.4},
            }
            self.financials = {
                'TGT': [{'roe': 0.15, 'debtRatio': 0.40, 'revenueGrowth': 0.12, 'operatingCashFlow': 120.0, 'net_profit': 100.0}],
                'P1': [{'roe': 0.16, 'debt_ratio': 0.35, 'revenue_yoy': 0.11, 'operating_cash_flow': 130.0, 'netProfit': 100.0}],
                'P2': [{'roe': 0.15, 'debt_ratio': 0.36, 'revenue_yoy': 0.12, 'operating_cash_flow': 125.0, 'netProfit': 100.0}],
                'P3': [{'roe': 0.14, 'debtRatio': 0.38, 'revenueGrowth': 0.13, 'operatingCashFlow': 140.0, 'netProfit': 100.0}],
                'P4': [{'roe': 0.17, 'debt_ratio': 0.39, 'revenue_growth': 0.14, 'operating_cash_flow': 150.0, 'net_profit': 100.0}],
                'P5': [{'roe': 0.16, 'debt_ratio': 0.41, 'revenue_growth': 0.10, 'operating_cash_flow': 135.0, 'net_profit': 100.0}],
            }

        def acquire(self):
            return _Acquire(_ValuationConn())

        async def get_stock_info(self, code):
            return self.stock_info.get(code)

        async def get_financials(self, code, limit=1):
            rows = self.financials.get(code, [])
            return rows[:limit]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _ValuationDB())

    result = await mcp.relative_valuation('TGT', metrics=['pe_ratio', 'pb_ratio', 'ps_ratio'])
    assert result['success'] is True
    assert result['data']['target_metrics'] == {'pb_ratio': 3.0}
    assert result['data']['invalid_target_metrics']['pe_ratio']['reason'] == 'non_positive'
    assert result['data']['invalid_target_metrics']['ps_ratio']['reason'] == 'non_positive'
    assert result['data']['invalid_peer_metrics']['pb_ratio']['non_positive'] == 1
    assert result['data']['peer_count'] == 5
    assert result['data']['peer_pool_build']['peer_source'] == 'industry'
    assert result['data']['peer_pool_build']['quality_thresholds']['debt_ratio_max'] == pytest.approx(0.65)


def test_p1_limit_up_statistics_should_handle_none_fields(monkeypatch):
    monkeypatch.setattr(
        limit_up_mod,
        'get_limit_up_stocks',
        lambda date='': {
            'success': True,
            'data': [
                {'tradeDate': '2026-01-15', 'continuousDays': None, 'openTimes': None},
                {'tradeDate': '2026-01-15', 'continuousDays': '2', 'openTimes': '1'},
                {'tradeDate': '2026-01-15', 'continuousDays': 4, 'openTimes': 0},
            ],
            'source': 'unit_test',
            'source_chain': ['unit_test'],
            'data_quality': {'missing_field_counts': {'openTimes': 1}},
        },
    )

    result = limit_up_mod.get_limit_up_statistics('2026-01-15')

    assert result['success'] is True
    assert result['data']['firstBoard'] == 0
    assert result['data']['secondBoard'] == 1
    assert result['data']['higherBoard'] == 1
    assert result['data']['failedBoard'] == 1


@pytest.mark.asyncio
async def test_p1_analyze_portfolio_risk_should_accept_codes_weights(monkeypatch):
    class _RiskDB:
        async def get_klines(self, code, limit=252):
            base = 10.0 if code == '600519' else 20.0
            return [
                {'close': base, 'volume': 1000},
                {'close': base * 1.02, 'volume': 1100},
                {'close': base * 1.03, 'volume': 1200},
            ]

    mcp = _DummyMCP()
    portfolio_mod.register(mcp)
    monkeypatch.setattr(portfolio_mod, 'get_db', lambda: _RiskDB())

    result = await mcp.analyze_portfolio_risk(codes=['600519', '000858'], weights=[0.6, 0.4])

    assert result['success'] is True
    assert result['data']['coverage']['requested'] == 2
    assert len(result['data']['analyzed_holdings']) == 2
    assert result['data']['portfolio_id'] is None


@pytest.mark.asyncio
async def test_p1_decision_manager_portfolio_advice_should_use_explicit_codes_weights(monkeypatch):
    class _DecisionDB:
        async def get_klines(self, code, limit=100):
            base = 10.0 if code == '600519' else 30.0
            return [
                {'close': base + i * 0.1, 'volume': 1000 + i * 10}
                for i in range(100)
            ]

        async def get_financials(self, code, limit=1):
            return [{
                'roe': 18.0,
                'pe_ratio': 20.0,
                'debt_ratio': 0.3,
                'pb_ratio': 2.0,
            }]

        async def save_klines(self, code, klines):
            return None

    mcp = _DummyMCP()
    decision_manager_mod.register_decision_manager(mcp)
    monkeypatch.setattr(decision_manager_mod, 'get_db', lambda: _DecisionDB())

    result = await mcp.decision_manager(
        action='portfolio_advice',
        codes=['600519', '000858'],
        weights=[0.4, 0.6],
    )

    assert result['success'] is True
    assert result['data']['codes'] == ['600519', '000858']
    assert len(result['data']['holdings_advice']) == 2
    assert result['data']['overall_score'] >= 0


@pytest.mark.asyncio
async def test_p1_scenario_dcf_should_auto_fill_base_revenue(monkeypatch):
    class _ScenarioDB:
        async def get_financials(self, code, limit=8):
            return [{
                'revenue': 5_000_000_000,
                'net_profit': 800_000_000,
            }]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, 'get_db', lambda: _ScenarioDB())

    result = await mcp.scenario_dcf_valuation(code='600519', industry='消费', years=3)

    assert result['success'] is True
    assert result['data']['base_revenue'] == pytest.approx(5_000_000_000.0)
    assert result['data']['base_revenue_source'] == 'financial_revenue'
    assert 'db.get_financials' in result['data']['source_chain']

__all__ = [name for name in globals() if name.startswith("test_")]
