"""产业链信息 — get_industry_chain"""

from typing import Optional
from ...utils import ok, fail


# 预置产业链数据
_PRESET_CHAINS = [
    {
        'id': 'new_energy',
        'name': '新能源产业链',
        'upstream': ['锂矿', '钴矿', '镍矿'],
        'midstream': ['电池材料', '电池制造'],
        'downstream': ['新能源汽车', '储能']
    },
    {
        'id': 'semiconductor',
        'name': '半导体产业链',
        'upstream': ['硅片', '光刻胶'],
        'midstream': ['芯片设计', '芯片制造'],
        'downstream': ['封装测试', '终端应用']
    },
    {
        'id': 'pv',
        'name': '光伏产业链',
        'upstream': ['硅料', '硅片'],
        'midstream': ['电池片', '组件'],
        'downstream': ['电站', '运维']
    },
    {
        'id': 'liquor',
        'name': '白酒产业链',
        'upstream': ['粮食', '包装'],
        'midstream': ['酿造', '灌装'],
        'downstream': ['经销', '零售']
    },
    {
        'id': 'pharma',
        'name': '医药产业链',
        'upstream': ['原料药', '中间体'],
        'midstream': ['制剂', '研发'],
        'downstream': ['流通', '医院与零售']
    },
]


def get_industry_chain(keyword: Optional[str] = None, chain_id: Optional[str] = None):
    """
    获取产业链信息（上中下游环节及关联行业）

    Args:
        keyword (str, optional): 关键词，匹配产业链名称或上中下游环节（如 "锂矿"、"新能源"）
        chain_id (str, optional): 产业链ID（如 "new_energy"、"semiconductor"）

    Returns:
        dict: {"success": bool, "data": {"chains": list[dict], "count": int, "message": str|null}}
        每条 chain 包含: id(str), name(str), upstream(list[str]), midstream(list[str]), downstream(list[str])

    Errors:
        - keyword 和 chain_id 均为空时返回全部预置产业链
        - 未匹配到时先尝试知识图谱扩展，仍无结果则返回全部预置产业链并附提示

    Examples:
        get_industry_chain(keyword="锂矿")
        get_industry_chain(chain_id="semiconductor")
    """
    try:
        chains = _PRESET_CHAINS
        message = None

        def _keyword_match(c, kw):
            if not kw:
                return False
            if kw in c.get('name', ''):
                return True
            for seg in ('upstream', 'midstream', 'downstream'):
                for item in c.get(seg, []):
                    if kw in item:
                        return True
            return False

        if chain_id:
            result = [c for c in chains if c['id'] == chain_id]
        elif keyword:
            kw = (keyword or '').strip()
            result = [c for c in chains if _keyword_match(c, kw)]
            if not result:
                try:
                    from ...services.industry_knowledge_graph import industry_kg
                    kg_res = industry_kg.analyze_chain(kw)
                    if not kg_res.get('error') and kg_res.get('chains'):
                        result = []
                        for i, ch in enumerate(kg_res['chains']):
                            up = [n.get('name', '') for n in ch.get('upstream', [])]
                            down = [n.get('name', '') for n in ch.get('downstream', [])]
                            cur = ch.get('current', {})
                            result.append({
                                'id': f"kg_{i}",
                                'name': cur.get('name', kw) + ' 产业链',
                                'upstream': up,
                                'midstream': [],
                                'downstream': down,
                            })
                except Exception:
                    pass
            if not result:
                result = chains
                message = f'未找到与「{keyword}」匹配的产业链，已返回全部预置产业链（共{len(chains)}条）'
        else:
            result = chains

        out = {'chains': result, 'count': len(result)}
        if message:
            out['message'] = message
        return ok(out)

    except Exception as e:
        return fail(str(e))
