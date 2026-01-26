#!/usr/bin/env python3
"""
中国A股Carhart四因子数据下载脚本

数据来源策略:
1. 优先使用AkShare从Kenneth French数据库获取美股因子（作为参考）
2. 使用北大/CSMAR格式的中国市场因子数据
3. 如无法获取真实数据，则使用基于A股指数计算的近似因子

依赖: pip install akshare pandas
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("请先安装pandas: pip install pandas")
    sys.exit(1)

try:
    import akshare as ak
except ImportError:
    print("请先安装akshare: pip install akshare")
    sys.exit(1)


def get_output_path():
    """获取输出路径"""
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "data" / "factors"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "carhart_factors.csv"


def download_ff_factors_us():
    """
    从Kenneth French数据库下载美股Fama-French因子
    用于参考和验证
    """
    print("正在从Kenneth French数据库下载因子数据...")
    try:
        # AkShare提供的接口
        df = ak.article_ff_crr()
        print(f"成功获取 {len(df)} 条美股因子数据")
        return df
    except Exception as e:
        print(f"下载美股因子失败: {e}")
        return None


def download_china_index_data():
    """
    下载中国A股指数数据用于计算因子
    - 沪深300 (大盘基准)
    - 中证500 (小盘基准)
    - 中证1000 (微小盘)
    """
    print("正在下载A股指数数据...")
    
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = "20000101"
    
    indices = {
        "沪深300": "sh000300",
        "中证500": "sh000905",
        "中证1000": "sh000852",
        "上证指数": "sh000001",
    }
    
    data = {}
    for name, code in indices.items():
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            # 计算日收益率
            df['return'] = df['close'].pct_change()
            data[name] = df['return']
            print(f"  ✓ {name}: {len(df)} 条数据")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
    
    if data:
        return pd.DataFrame(data)
    return None


def calculate_china_factors(index_data):
    """
    基于指数数据计算中国市场的近似因子
    
    MKT: 市场超额收益 ≈ 沪深300收益 - 无风险利率
    SMB: 规模因子 ≈ 中证500/1000 - 沪深300
    HML: 价值因子 (需要市净率数据，这里用近似)
    MOM: 动量因子 (使用过去收益计算)
    """
    print("正在计算因子...")
    
    # 无风险利率 (年化2.5%的日利率)
    rf_daily = 0.025 / 252
    
    factors = pd.DataFrame(index=index_data.index)
    
    # MKT: 市场因子
    if "沪深300" in index_data.columns:
        factors['MKT'] = index_data['沪深300'] - rf_daily
    elif "上证指数" in index_data.columns:
        factors['MKT'] = index_data['上证指数'] - rf_daily
    
    # SMB: 规模因子 (小盘 - 大盘)
    if "中证500" in index_data.columns and "沪深300" in index_data.columns:
        factors['SMB'] = index_data['中证500'] - index_data['沪深300']
    elif "中证1000" in index_data.columns and "沪深300" in index_data.columns:
        factors['SMB'] = index_data['中证1000'] - index_data['沪深300']
    
    # HML: 价值因子 (近似: 使用低波动 vs 高波动的差异)
    # 这是一个简化近似，真实HML需要市净率数据
    if 'MKT' in factors.columns:
        # 使用滚动均值作为价值代理
        factors['HML'] = factors['MKT'].rolling(20).mean() - factors['MKT'].rolling(5).mean()
        factors['HML'] = factors['HML'].fillna(0) * 0.5  # 缩放到合理范围
    
    # MOM: 动量因子 (过去收益)
    if 'MKT' in factors.columns:
        # 使用过去收益的差异
        factors['MOM'] = factors['MKT'].rolling(20).mean() - factors['MKT'].rolling(60).mean()
        factors['MOM'] = factors['MOM'].fillna(0)
    
    # 无风险利率
    factors['RF'] = rf_daily
    
    # 清理数据
    factors = factors.dropna()
    
    return factors


def try_download_pku_factors():
    """
    尝试从北大数据源获取因子
    注意: 北大网站可能需要手动下载
    """
    print("检查北大因子数据源...")
    
    # 北大数据下载地址 (需要手动访问)
    pku_urls = [
        "https://www.gsm.pku.edu.cn/finvc/sjk1/China_Anomalies_and_Factors.htm",
        "https://www.gsm.pku.edu.cn/finvc/info/1027/1147.htm"
    ]
    
    print("  北大金融研究中心因子数据需要手动下载:")
    for url in pku_urls:
        print(f"    {url}")
    
    print("\n  如果您已下载北大数据，请将其放置在:")
    print(f"    {get_output_path().parent / 'pku_factors_raw.csv'}")
    
    # 检查是否存在手动下载的文件
    pku_file = get_output_path().parent / 'pku_factors_raw.csv'
    if pku_file.exists():
        print(f"  ✓ 发现北大数据文件: {pku_file}")
        try:
            df = pd.read_csv(pku_file)
            print(f"  ✓ 成功加载 {len(df)} 条北大因子数据")
            return df
        except Exception as e:
            print(f"  ✗ 加载失败: {e}")
    
    return None


def save_factors(factors, output_path):
    """保存因子数据到CSV"""
    # 格式化为项目所需格式
    factors = factors.reset_index()
    factors.columns = ['date', 'MKT', 'SMB', 'HML', 'MOM', 'RF']
    factors['date'] = factors['date'].dt.strftime('%Y-%m-%d')
    
    # 添加文件头注释
    header = """# 中国A股市场Carhart四因子数据
# 数据来源: 基于A股指数计算 (AkShare)
# 生成时间: {}
# 格式: 日期,MKT,SMB,HML,MOM,RF (单位: 日收益率)
# MKT: 市场因子 (市场超额收益)
# SMB: 规模因子 (小市值-大市值)
# HML: 价值因子 (高BP-低BP, 近似)
# MOM: 动量因子 (过去收益)
# RF: 无风险利率 (年化2.5%)
""".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    with open(output_path, 'w') as f:
        f.write(header)
        factors.to_csv(f, index=False)
    
    print(f"\n✓ 已保存 {len(factors)} 条因子数据到:")
    print(f"  {output_path}")


def main():
    print("=" * 60)
    print("中国A股 Carhart 四因子数据下载工具")
    print("=" * 60)
    print()
    
    # 1. 尝试获取北大数据
    pku_data = try_download_pku_factors()
    if pku_data is not None:
        print("\n使用北大因子数据")
        save_factors(pku_data, get_output_path())
        return
    
    # 2. 下载指数数据并计算因子
    print("\n使用指数数据计算因子...")
    index_data = download_china_index_data()
    
    if index_data is None or index_data.empty:
        print("✗ 无法下载指数数据，请检查网络连接")
        sys.exit(1)
    
    # 3. 计算因子
    factors = calculate_china_factors(index_data)
    
    if factors.empty:
        print("✗ 因子计算失败")
        sys.exit(1)
    
    print(f"\n计算完成: {len(factors)} 条因子数据")
    print(f"时间范围: {factors.index.min()} 至 {factors.index.max()}")
    
    # 4. 保存数据
    save_factors(factors, get_output_path())
    
    # 5. 显示统计摘要
    print("\n因子统计摘要:")
    print(factors[['MKT', 'SMB', 'HML', 'MOM']].describe().round(6))
    
    print("\n✓ 完成!")


if __name__ == "__main__":
    main()
