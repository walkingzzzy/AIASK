"""
集合竞价分析测试
"""
import pytest
from packages.core.call_auction.auction_analyzer import CallAuctionAnalyzer


def test_get_auction_data():
    """测试获取竞价数据"""
    analyzer = CallAuctionAnalyzer()
    stocks = analyzer.get_auction_data()

    assert len(stocks) > 0
    assert stocks[0].stock_code is not None
    assert stocks[0].stock_name is not None


def test_get_auction_ranking():
    """测试竞价排行榜"""
    analyzer = CallAuctionAnalyzer()
    ranking = analyzer.get_auction_ranking(top_n=10)

    assert 'change_ranking' in ranking
    assert 'abnormal_stocks' in ranking
    assert len(ranking['change_ranking']) <= 10


def test_analyze_auction_stock():
    """测试个股竞价分析"""
    analyzer = CallAuctionAnalyzer()
    analysis = analyzer.analyze_auction_stock("000001")

    assert 'stock_info' in analysis or 'error' in analysis
    if 'stock_info' in analysis:
        assert 'auction_metrics' in analysis
        assert 'open_prediction' in analysis


if __name__ == "__main__":
    # 简单测试
    analyzer = CallAuctionAnalyzer()
    print("测试1: 获取竞价数据...")
    stocks = analyzer.get_auction_data()
    print(f"✓ 获取到 {len(stocks)} 只股票数据")

    print("\n测试2: 获取竞价排行榜...")
    ranking = analyzer.get_auction_ranking(top_n=5)
    print(f"✓ 涨幅榜前5:")
    for i, stock in enumerate(ranking['change_ranking'][:5], 1):
        print(f"  {i}. {stock.stock_name} {stock.auction_change:.2f}%")

    print(f"\n✓ 异动股票: {len(ranking['abnormal_stocks'])} 只")

    print("\n测试3: 分析个股...")
    analysis = analyzer.analyze_auction_stock("000001")
    if 'error' not in analysis:
        print(f"✓ {analysis['stock_info']['name']} 竞价涨幅: {analysis['stock_info']['auction_change']:.2f}%")
        print(f"  开盘预测: {analysis['open_prediction']}")
    else:
        print(f"  {analysis['error']}")

    print("\n所有测试完成！")
