"""
MCP 功能测试 — 直接调用 FastMCP 工具进行端到端验证
"""
import sys, asyncio, json, os, traceback
from datetime import datetime
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ['TDX_ENABLED'] = 'false'

from mcp.server.fastmcp.exceptions import ToolError
from akshare_mcp.server import mcp as app

RESULTS = []

pytestmark = pytest.mark.asyncio

async def call_tool(name: str, args: dict = None):
    """调用 MCP 工具并返回结果"""
    tool = app._tool_manager._tools.get(name)
    if not tool:
        return {'success': False, 'error': f'Tool "{name}" not found'}
    try:
        result = await tool.run(args or {})
    except ToolError as e:
        return {'success': False, 'error': str(e)[:200]}
    except Exception as e:
        return {'success': False, 'error': f'{type(e).__name__}: {e}'}
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except Exception:
            return {'success': True, 'data': result}
    return {'success': True, 'data': str(result)}

def record(category: str, tool_name: str, result: dict):
    ok = result.get('success', False) if isinstance(result, dict) else bool(result)
    err = result.get('error', '') if isinstance(result, dict) else ''
    RESULTS.append({
        'category': category,
        'tool': tool_name,
        'success': ok,
        'error': str(err)[:150],
    })
    data_preview = ''
    if ok and isinstance(result, dict) and result.get('data'):
        d = result['data']
        if isinstance(d, list):
            data_preview = f' [{len(d)} items]'
        elif isinstance(d, dict):
            keys = list(d.keys())[:5]
            data_preview = f' {{{", ".join(keys)}}}'
        else:
            data_preview = f' {str(d)[:80]}'
    status = '\033[92m✅\033[0m' if ok else '\033[91m❌\033[0m'
    print(f'  {status} {tool_name}{data_preview}')
    if not ok:
        print(f'     \033[93mError: {str(err)[:150]}\033[0m')

# ========== 测试分组 ==========

async def test_search():
    print('\n📋 [Search & Discovery]')
    record('Search', 'available_tools', await call_tool('available_tools'))
    record('Search', 'get_available_categories', await call_tool('get_available_categories'))
    record('Search', 'search_stocks', await call_tool('search_stocks', {'keyword': '茅台'}))

async def test_market_data():
    print('\n📈 [Market Data]')
    record('Market', 'get_stock_list', await call_tool('get_stock_list'))
    record('Market', 'get_realtime_quote', await call_tool('get_realtime_quote', {'stock_code': '600519'}))
    record('Market', 'get_kline', await call_tool('get_kline', {'stock_code': '600519', 'period': 'daily', 'limit': 10}))
    record('Market', 'get_index_quote', await call_tool('get_index_quote', {'index_code': '000001'}))

async def test_finance():
    print('\n💰 [Finance]')
    record('Finance', 'get_financials', await call_tool('get_financials', {'stock_code': '600519'}))
    record('Finance', 'get_stock_info', await call_tool('get_stock_info', {'stock_code': '600519'}))

async def test_fund_flow():
    print('\n💸 [Fund Flow]')
    record('FundFlow', 'get_north_fund', await call_tool('get_north_fund'))
    record('FundFlow', 'get_sector_fund_flow', await call_tool('get_sector_fund_flow'))
    record('FundFlow', 'get_stock_fund_flow', await call_tool('get_stock_fund_flow', {'stock_code': '600519'}))

async def test_macro():
    print('\n🏛️ [Macro]')
    record('Macro', 'get_macro_indicator', await call_tool('get_macro_indicator', {'indicator': 'gdp'}))

async def test_news():
    print('\n📰 [News]')
    record('News', 'get_stock_news', await call_tool('get_stock_news', {'stock_code': '600519'}))
    record('News', 'get_market_news', await call_tool('get_market_news'))

async def test_technical():
    print('\n📊 [Technical Analysis]')
    record('Technical', 'calculate_technical_indicators',
           await call_tool('calculate_technical_indicators', {'code': '600519', 'indicators': ['MACD', 'RSI', 'KDJ']}))
    record('Technical', 'get_available_patterns', await call_tool('get_available_patterns'))

async def test_valuation():
    print('\n🏷️ [Valuation]')
    record('Valuation', 'get_valuation_metrics', await call_tool('get_valuation_metrics', {'code': '600519'}))
    record('Valuation', 'list_industry_templates', await call_tool('list_industry_templates'))

async def test_backtest():
    print('\n🔬 [Backtest]')
    record('Backtest', 'run_simple_backtest',
           await call_tool('run_simple_backtest', {'code': '600519', 'strategy': 'ma_cross', 'start_date': '2024-01-01', 'end_date': '2024-12-31'}))

async def test_decision():
    print('\n🤔 [Decision]')
    record('Decision', 'should_i_buy', await call_tool('should_i_buy', {'code': '600519'}))

async def test_semantic():
    print('\n🧠 [Semantic]')
    record('Semantic', 'smart_stock_diagnosis', await call_tool('smart_stock_diagnosis', {'stock_code': '600519'}))
    record('Semantic', 'get_industry_chain', await call_tool('get_industry_chain', {'keyword': '白酒'}))

async def test_quant():
    print('\n🔢 [Quant]')
    record('Quant', 'get_factor_library', await call_tool('get_factor_library'))
    record('Quant', 'calculate_factor', await call_tool('calculate_factor', {'code': '600519', 'factor': 'atr_14'}))

async def test_sentiment():
    print('\n😊 [Sentiment]')
    record('Sentiment', 'calculate_fear_greed_index', await call_tool('calculate_fear_greed_index'))

async def test_portfolio():
    print('\n📦 [Portfolio]')
    record('Portfolio', 'optimize_portfolio',
           await call_tool('optimize_portfolio', {'stocks': ['600519', '000858', '000333']}))

async def test_alerts():
    print('\n🔔 [Alerts]')
    record('Alerts', 'check_all_alerts', await call_tool('check_all_alerts'))

async def test_basic_data():
    print('\n📅 [Basic Data]')
    record('BasicData', 'get_trading_dates', await call_tool('get_trading_dates', {'start_date': '20250101', 'end_date': '20250301'}))

async def test_data_sync():
    print('\n🔄 [Data Sync]')
    record('DataSync', 'get_sync_status', await call_tool('get_sync_status'))
    record('DataSync', 'get_cache_stats', await call_tool('get_cache_stats'))

# ========== Main ==========

async def main():
    print('=' * 60)
    print(f'  MCP 功能测试 — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  Server: {app.name}')
    tools = app._tool_manager._tools
    print(f'  Registered tools: {len(tools)}')
    print('=' * 60)

    test_groups = [
        test_search, test_market_data, test_finance, test_fund_flow,
        test_macro, test_news, test_technical, test_valuation,
        test_backtest, test_decision, test_semantic, test_quant,
        test_sentiment, test_portfolio, test_alerts, test_basic_data,
        test_data_sync,
    ]

    for test_fn in test_groups:
        try:
            await test_fn()
        except Exception as e:
            print(f'  \033[91m❌ Group error: {e}\033[0m')
            traceback.print_exc()

    # Summary
    print('\n' + '=' * 60)
    print('  SUMMARY')
    print('=' * 60)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r['success'])
    failed = total - passed
    print(f'  Total: {total}  |  \033[92mPassed: {passed}\033[0m  |  \033[91mFailed: {failed}\033[0m')
    if total:
        rate = passed / total * 100
        color = '\033[92m' if rate >= 80 else '\033[93m' if rate >= 50 else '\033[91m'
        print(f'  Pass rate: {color}{rate:.1f}%\033[0m')

    if failed:
        print(f'\n  \033[91mFailed tests ({failed}):\033[0m')
        for r in RESULTS:
            if not r['success']:
                print(f'    ❌ [{r["category"]}] {r["tool"]}')
                print(f'       {r["error"]}')

    print()
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    exit(asyncio.run(main()))
