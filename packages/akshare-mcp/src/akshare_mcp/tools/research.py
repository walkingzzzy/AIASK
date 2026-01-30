"""研究工具"""
from ..utils import ok, fail

def register(mcp):
    @mcp.tool()
    async def search_research(keyword: str = None, stock_code: str = None, days: int = 30):
        try:
            reports = []
            return ok({'reports': reports, 'keyword': keyword, 'stock_code': stock_code})
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def analyze_research_report(code: str):
        try:
            analysis = {
                'code': code,
                'summary': '',
                'signals': [],
                'target_price': None
            }
            return ok(analysis)
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def get_research_summary(code: str, limit: int = 10):
        try:
            summaries = []
            return ok({'code': code, 'summaries': summaries})
        except Exception as e:
            return fail(str(e))
