"""
AI评分系统使用示例
演示如何使用P0阶段开发的核心功能
"""
from packages.core.services.stock_data_service import get_stock_service
from packages.core.nlp_query.intent_parser import parse_query
from packages.core.nlp_query.query_executor import execute_query


def demo_ai_score():
    """演示AI评分功能"""
    print("=" * 60)
    print("AI评分系统演示")
    print("=" * 60)
    
    service = get_stock_service()
    
    # 获取单只股票AI评分
    stock_code = "600519"
    stock_name = "贵州茅台"
    
    print(f"\n获取 {stock_name}({stock_code}) 的AI评分...")
    score_result = service.get_ai_score(stock_code, stock_name)
    
    if score_result:
        print(f"\n综合评分: {score_result.ai_score}/10")
        print(f"买卖信号: {score_result.signal}")
        print(f"跑赢市场概率: {score_result.beat_market_probability*100:.0f}%")
        print(f"置信度: {score_result.confidence*100:.0f}%")
        
        print("\n分项评分:")
        for name, data in score_result.subscores.items():
            print(f"  - {name}: {data['score']}分 (权重{int(data['weight']*100)}%)")
        
        if score_result.risks:
            print("\n风险提示:")
            for risk in score_result.risks:
                print(f"  ⚠️ {risk}")
    else:
        print("获取评分失败")


def demo_technical_indicators():
    """演示技术指标计算"""
    print("\n" + "=" * 60)
    print("技术指标计算演示")
    print("=" * 60)
    
    service = get_stock_service()
    stock_code = "600519"
    
    print(f"\n计算 {stock_code} 的技术指标...")
    indicators = service.calculate_indicators(stock_code)
    
    if indicators:
        print(f"\n当前价格: {indicators.get('close', 'N/A')}")
        print(f"MA5: {indicators.get('ma5', 'N/A')}")
        print(f"MA10: {indicators.get('ma10', 'N/A')}")
        print(f"MA20: {indicators.get('ma20', 'N/A')}")
        print(f"MACD DIF: {indicators.get('macd_dif', 'N/A')}")
        print(f"MACD DEA: {indicators.get('macd_dea', 'N/A')}")
        print(f"RSI: {indicators.get('rsi', 'N/A')}")
        print(f"量比: {indicators.get('volume_ratio', 'N/A')}")
    else:
        print("计算指标失败")


def demo_nlp_query():
    """演示自然语言查询"""
    print("\n" + "=" * 60)
    print("自然语言查询演示")
    print("=" * 60)
    
    queries = [
        "分析贵州茅台",
        "找出PE低于20的股票",
        "茅台的PE是多少",
    ]
    
    for query in queries:
        print(f"\n查询: {query}")
        print("-" * 40)
        
        intent = parse_query(query)
        print(f"识别意图: {intent.intent_type.value}")
        print(f"置信度: {intent.confidence*100:.0f}%")
        
        if intent.entities.get('stock_codes'):
            print(f"股票代码: {intent.entities['stock_codes']}")
        if intent.entities.get('conditions'):
            print(f"筛选条件: {intent.entities['conditions']}")
        
        result = execute_query(intent)
        print(f"执行结果: {result.message}")


def demo_score_explanation():
    """演示评分解释"""
    print("\n" + "=" * 60)
    print("评分解释演示")
    print("=" * 60)
    
    service = get_stock_service()
    stock_code = "600519"
    stock_name = "贵州茅台"
    
    print(f"\n获取 {stock_name} 的评分解释...")
    explanation = service.get_score_explanation(stock_code, stock_name)
    
    if explanation:
        print(f"\n摘要: {explanation.summary}")
        
        print("\n评分分解:")
        for name, value in explanation.score_breakdown.items():
            print(f"  - {name}: {value}")
        
        if explanation.top_positive_factors:
            print("\n利好因素:")
            for f in explanation.top_positive_factors:
                print(f"  ✅ {f.description} (贡献+{f.score_contribution})")
        
        if explanation.top_negative_factors:
            print("\n风险因素:")
            for f in explanation.top_negative_factors:
                print(f"  ⚠️ {f.description} (影响{f.score_contribution})")
        
        if explanation.suggestions:
            print("\n投资建议:")
            for s in explanation.suggestions:
                print(f"  💡 {s}")
    else:
        print("获取解释失败")


if __name__ == "__main__":
    print("A股智能分析系统 - P0功能演示")
    print("注意: 需要网络连接获取实时数据\n")
    
    try:
        demo_ai_score()
        demo_technical_indicators()
        demo_nlp_query()
        demo_score_explanation()
        
        print("\n" + "=" * 60)
        print("演示完成!")
        print("=" * 60)
    except Exception as e:
        print(f"\n演示过程中出错: {e}")
        print("请确保网络连接正常，并已安装所需依赖")
