"""技能工具"""
from ..utils import ok, fail

def register(mcp):
    @mcp.tool()
    def list_skills():
        skills = [
            {'id': 'momentum_screen', 'name': '动量选股', 'category': 'screening'},
            {'id': 'value_screen', 'name': '价值选股', 'category': 'screening'},
            {'id': 'trend_follow', 'name': '趋势跟踪', 'category': 'strategy'},
        ]
        return ok({'skills': skills})
    
    @mcp.tool()
    def search_skills(keyword: str):
        skills = [
            {'id': 'momentum_screen', 'name': '动量选股', 'category': 'screening'},
        ]
        return ok({'skills': skills, 'keyword': keyword})
    
    @mcp.tool()
    def run_skill(skill_id: str, params: dict = None):
        return ok({'skill_id': skill_id, 'result': {}})
