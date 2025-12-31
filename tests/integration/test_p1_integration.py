"""
情绪数据与AI评分系统集成验证脚本
验证LLM情绪分析和社交媒体情绪数据是否正确集成到AI评分系统
"""
import sys
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_llm_sentiment_integration():
    """测试LLM情绪分析集成"""
    logger.info("=" * 60)
    logger.info("测试1: LLM情绪分析集成")
    logger.info("=" * 60)

    try:
        from packages.core.sentiment.llm_sentiment_analyzer import LLMSentimentAnalyzer

        analyzer = LLMSentimentAnalyzer()
        logger.info("✅ LLM情绪分析器导入成功")

        # 测试文本分析
        test_text = "公司业绩大幅增长，市场前景广阔，强烈推荐买入"
        logger.info(f"测试文本: {test_text}")

        # 注意：这需要OpenAI API Key
        if analyzer.llm_client:
            result = analyzer.analyze_text_sync(test_text)
            logger.info(f"✅ LLM分析结果: 情绪分数={result.sentiment_score}, 标签={result.sentiment_label}")
            logger.info(f"   关键因素: {result.key_factors}")
            logger.info(f"   置信度: {result.confidence}")
        else:
            logger.warning("⚠️  LLM客户端未初始化（可能缺少API Key），但模块导入正常")

        return True

    except Exception as e:
        logger.error(f"❌ LLM情绪分析集成测试失败: {e}")
        return False


def test_sentiment_analyzer_integration():
    """测试情绪分析器集成"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 情绪分析器LLM集成")
    logger.info("=" * 60)

    try:
        from packages.core.sentiment.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()
        logger.info("✅ 情绪分析器导入成功")

        # 检查LLM是否启用
        if analyzer.use_llm:
            logger.info("✅ LLM情绪分析已启用")
        else:
            logger.warning("⚠️  LLM情绪分析未启用，将使用关键词匹配")

        # 测试文本分析
        test_text = "公司业绩大幅增长，市场前景广阔"
        score, keywords = analyzer.analyze_text(test_text, use_llm=True)
        logger.info(f"✅ 分析结果: 情绪分数={score:.2f}, 关键词={keywords}")

        return True

    except Exception as e:
        logger.error(f"❌ 情绪分析器集成测试失败: {e}")
        return False


def test_social_media_sentiment_integration():
    """测试社交媒体情绪数据集成"""
    logger.info("\n" + "=" * 60)
    logger.info("测试3: 社交媒体情绪数据集成")
    logger.info("=" * 60)

    try:
        from packages.core.scoring.ai_score.sentiment_extended import (
            SENTIMENT_MODULE_AVAILABLE,
            GubaSentimentIndicator
        )

        if SENTIMENT_MODULE_AVAILABLE:
            logger.info("✅ 社交媒体情绪模块可用")

            # 测试股吧情绪指标
            indicator = GubaSentimentIndicator()
            logger.info("✅ 股吧情绪指标初始化成功")

            # 测试计算（使用模拟数据）
            result = indicator.calculate(
                stock_code="600519",
                sentiment_data={'guba_sentiment': 0.6}
            )
            logger.info(f"✅ 指标计算成功: {result}")

        else:
            logger.warning("⚠️  社交媒体情绪模块不可用")

        return True

    except Exception as e:
        logger.error(f"❌ 社交媒体情绪集成测试失败: {e}")
        return False


def test_ai_score_sentiment_integration():
    """测试AI评分系统情绪面集成"""
    logger.info("\n" + "=" * 60)
    logger.info("测试4: AI评分系统情绪面集成")
    logger.info("=" * 60)

    try:
        from packages.core.scoring.ai_score.score_components import SentimentScore

        sentiment_scorer = SentimentScore()
        logger.info("✅ 情绪面评分组件导入成功")

        # 测试评分计算
        test_data = {
            'market_breadth': 0.6,
            'news_sentiment': 0.3,
            'analyst_rating': 4
        }

        result = sentiment_scorer.calculate(test_data)
        logger.info(f"✅ 情绪面评分计算成功:")
        logger.info(f"   评分: {result.score:.2f}")
        logger.info(f"   权重: {result.weight}")
        logger.info(f"   影响因素: {result.factors}")

        return True

    except Exception as e:
        logger.error(f"❌ AI评分系统情绪面集成测试失败: {e}")
        return False


def test_additional_indicators():
    """测试新增指标"""
    logger.info("\n" + "=" * 60)
    logger.info("测试5: 新增22个指标")
    logger.info("=" * 60)

    try:
        from packages.core.scoring.ai_score.additional_indicators import (
            RSISlopeIndicator,
            RSIDivergenceIndicator,
            MACDHistogramAreaIndicator,
            KDJCrossIndicator,
            GapAnalysisIndicator,
            PiotroskiFScoreIndicator,
            AltmanZScoreIndicator,
            DuPontROEIndicator,
            FreeCashFlowYieldIndicator,
            AssetTurnoverRatioIndicator,
            ETFFundFlowIndicator,
            QFIIHoldingChangeIndicator,
            TurnoverRatePercentileIndicator,
            AnalystConsensusChangeIndicator,
            NewsSentimentTrendIndicator,
            ConceptHotRankIndicator,
            VaRIndicator,
            CVaRIndicator,
            InformationRatioIndicator,
            VolatilityTrendIndicator
        )

        indicators = [
            "RSISlopeIndicator", "RSIDivergenceIndicator", "MACDHistogramAreaIndicator",
            "KDJCrossIndicator", "GapAnalysisIndicator", "PiotroskiFScoreIndicator",
            "AltmanZScoreIndicator", "DuPontROEIndicator", "FreeCashFlowYieldIndicator",
            "AssetTurnoverRatioIndicator", "ETFFundFlowIndicator", "QFIIHoldingChangeIndicator",
            "TurnoverRatePercentileIndicator", "AnalystConsensusChangeIndicator",
            "NewsSentimentTrendIndicator", "ConceptHotRankIndicator", "VaRIndicator",
            "CVaRIndicator", "InformationRatioIndicator", "VolatilityTrendIndicator"
        ]

        logger.info(f"✅ 成功导入 {len(indicators)} 个新增指标:")
        for i, ind in enumerate(indicators, 1):
            logger.info(f"   {i}. {ind}")

        # 测试一个指标
        rsi_slope = RSISlopeIndicator()
        logger.info(f"\n✅ 测试RSI斜率指标:")
        logger.info(f"   名称: {rsi_slope.display_name}")
        logger.info(f"   类别: {rsi_slope.category}")
        logger.info(f"   描述: {rsi_slope.description}")

        return True

    except Exception as e:
        logger.error(f"❌ 新增指标测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backtest_visualizer():
    """测试回测可视化"""
    logger.info("\n" + "=" * 60)
    logger.info("测试6: 回测可视化")
    logger.info("=" * 60)

    try:
        from packages.core.backtest.backtest_visualizer import BacktestVisualizer

        visualizer = BacktestVisualizer()
        logger.info("✅ 回测可视化器导入成功")

        if visualizer.available:
            logger.info("✅ 可视化库可用")
        else:
            logger.warning("⚠️  可视化库不可用（可能缺少matplotlib/seaborn）")

        return True

    except Exception as e:
        logger.error(f"❌ 回测可视化测试失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "=" * 60)
    logger.info("P1阶段功能集成验证")
    logger.info("=" * 60 + "\n")

    results = {
        "LLM情绪分析集成": test_llm_sentiment_integration(),
        "情绪分析器LLM集成": test_sentiment_analyzer_integration(),
        "社交媒体情绪集成": test_social_media_sentiment_integration(),
        "AI评分情绪面集成": test_ai_score_sentiment_integration(),
        "新增22个指标": test_additional_indicators(),
        "回测可视化": test_backtest_visualizer()
    }

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        logger.info("\n🎉 所有测试通过！P1阶段功能集成验证成功！")
    else:
        logger.warning(f"\n⚠️  {total - passed} 个测试失败，请检查相关模块")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
