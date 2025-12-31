# AI评分模块
from .score_calculator import AIScoreCalculator
from .score_components import (
    TechnicalScore, FundamentalScore, FundFlowScore, SentimentScore, RiskScore
)

# 指标基类和注册器
from .indicator_registry import (
    IndicatorBase,IndicatorCategory,
    IndicatorRegistry,
    auto_register,
    get_registry
)

#扩展技术指标 (18个)
from .technical_extended import (
    FibonacciRetracementIndicator,
    FibonacciExtensionIndicator,
    SupportDistanceIndicator,
    ResistanceDistanceIndicator,
    MomentumIndicator,
    ROCIndicator,
    CCIIndicator,
    SARIndicator,
    ADXIndicator,
    DMIIndicator,
    TRIXIndicator,
    EMVIndicator,
    WRVariantIndicator,
    BIASIndicator,
    PSYIndicator,
    VRIndicator,
    ARBRIndicator,
    CRIndicator,
    get_all_technical_extended_indicators
)

# 扩展基本面指标 (12个)
from .fundamental_extended import (
    EBITDAMarginIndicator,
    DividendYieldIndicator,
    DividendPayoutRatioIndicator,
    OperatingProfitMarginIndicator,
    GrossMarginChangeIndicator,
    RDExpenseRatioIndicator,
    GoodwillRatioIndicator,
    InventoryTurnoverDaysIndicator,
    ReceivableTurnoverDaysIndicator,
    OperatingCashFlowRatioIndicator,
    InterestCoverageRatioIndicator,
    ROEGrowthRateIndicator,
    get_all_fundamental_extended_indicators
)

# 扩展资金面指标 (6个)
from .fund_flow_extended import (
    SocialSecurityHoldingChangeIndicator,
    ShareholderChangeIndicator,
    LockupExpiryPressureIndicator,
    LargeOrderNetInflowRatioIndicator,
    SuperLargeOrderNetInflowRatioIndicator,
    MainForceControlIndicator,
    get_all_fund_flow_extended_indicators
)

# 扩展情绪面指标 (6个)
from .sentiment_extended import (
    GubaSentimentIndicator,
    XueqiuSentimentIndicator,
    WeiboHeatIndicator,
    BaiduSearchIndicator,
    InstitutionAttentionIndicator,
    MarketPopularityIndicator,
    get_all_sentiment_extended_indicators
)

# 扩展风险指标 (2个)
from .risk_extended import (
    CalmarRatioIndicator,
    MaxConsecutiveLossDaysIndicator,
    get_all_risk_extended_indicators
)

# 补充基本面指标 (5个)
from .additional_fundamental import (
    AltmanZScoreIndicator,
    DuPontROEIndicator,
    FreeCashFlowYieldIndicator,
    AssetTurnoverRatioIndicator,
    PiotroskiFScoreIndicator,
    get_all_additional_fundamental_indicators
)

# 补充技术面指标 (10个)
from .additional_technical import (
    RSISlopeIndicator,
    RSIDivergenceIndicator,
    MACDDivergenceIndicator,
    MACDHistogramAreaIndicator,
    KDJCrossIndicator,
    KDJDivergenceIndicator,
    GapAnalysisIndicator,
    BollingerBandWidthIndicator,
    OBVTrendIndicator,
    IchimokuCloudIndicator,
    get_all_additional_technical_indicators
)

# 补充资金面指标 (3个)
from .additional_fund_flow import (
    ETFFundFlowIndicator,
    QFIIHoldingChangeIndicator,
    TurnoverRatePercentileIndicator,
    get_all_additional_fund_flow_indicators
)

# 补充情绪面指标 (3个)
from .additional_sentiment import (
    AnalystConsensusChangeIndicator,
    NewsSentimentTrendIndicator,
    ConceptHotRankIndicator,
    get_all_additional_sentiment_indicators
)

# 补充风险面指标 (4个)
from .additional_risk import (
    VaRIndicator,
    CVaRIndicator,
    InformationRatioIndicator,
    VolatilityTrendIndicator,
    get_all_additional_risk_indicators
)

__all__ = [
    #原有导出
    'AIScoreCalculator',
    'TechnicalScore',
    'FundamentalScore',
    'FundFlowScore',
    'SentimentScore',
    'RiskScore',
    
    # 指标基类和注册器
    'IndicatorBase',
    'IndicatorCategory',
    'IndicatorRegistry',
    'auto_register',
    'get_registry',
    
    # 技术指标
    'FibonacciRetracementIndicator',
    'FibonacciExtensionIndicator',
    'SupportDistanceIndicator',
    'ResistanceDistanceIndicator',
    'MomentumIndicator',
    'ROCIndicator',
    'CCIIndicator',
    'SARIndicator',
    'ADXIndicator',
    'DMIIndicator',
    'TRIXIndicator',
    'EMVIndicator',
    'WRVariantIndicator',
    'BIASIndicator',
    'PSYIndicator',
    'VRIndicator',
    'ARBRIndicator',
    'CRIndicator',
    'get_all_technical_extended_indicators',
    
    # 基本面指标
    'EBITDAMarginIndicator',
    'DividendYieldIndicator',
    'DividendPayoutRatioIndicator',
    'OperatingProfitMarginIndicator',
    'GrossMarginChangeIndicator',
    'RDExpenseRatioIndicator',
    'GoodwillRatioIndicator',
    'InventoryTurnoverDaysIndicator',
    'ReceivableTurnoverDaysIndicator',
    'OperatingCashFlowRatioIndicator',
    'InterestCoverageRatioIndicator',
    'ROEGrowthRateIndicator',
    'get_all_fundamental_extended_indicators',
    
    # 资金面指标
    'SocialSecurityHoldingChangeIndicator',
    'ShareholderChangeIndicator',
    'LockupExpiryPressureIndicator',
    'LargeOrderNetInflowRatioIndicator',
    'SuperLargeOrderNetInflowRatioIndicator',
    'MainForceControlIndicator',
    'get_all_fund_flow_extended_indicators',
    
    # 情绪面指标
    'GubaSentimentIndicator',
    'XueqiuSentimentIndicator',
    'WeiboHeatIndicator',
    'BaiduSearchIndicator',
    'InstitutionAttentionIndicator',
    'MarketPopularityIndicator',
    'get_all_sentiment_extended_indicators',
    
    # 风险指标
    'CalmarRatioIndicator',
    'MaxConsecutiveLossDaysIndicator',
    'get_all_risk_extended_indicators',
    
    # 补充基本面指标
    'AltmanZScoreIndicator',
    'DuPontROEIndicator',
    'FreeCashFlowYieldIndicator',
    'AssetTurnoverRatioIndicator',
    'PiotroskiFScoreIndicator',
    'get_all_additional_fundamental_indicators',
    
    # 补充技术面指标
    'RSISlopeIndicator',
    'RSIDivergenceIndicator',
    'MACDDivergenceIndicator',
    'MACDHistogramAreaIndicator',
    'KDJCrossIndicator',
    'KDJDivergenceIndicator',
    'GapAnalysisIndicator',
    'BollingerBandWidthIndicator',
    'OBVTrendIndicator',
    'IchimokuCloudIndicator',
    'get_all_additional_technical_indicators',
    
    # 补充资金面指标
    'ETFFundFlowIndicator',
    'QFIIHoldingChangeIndicator',
    'TurnoverRatePercentileIndicator',
    'get_all_additional_fund_flow_indicators',
    
    # 补充情绪面指标
    'AnalystConsensusChangeIndicator',
    'NewsSentimentTrendIndicator',
    'ConceptHotRankIndicator',
    'get_all_additional_sentiment_indicators',
    
    # 补充风险面指标
    'VaRIndicator',
    'CVaRIndicator',
    'InformationRatioIndicator',
    'VolatilityTrendIndicator',
    'get_all_additional_risk_indicators',
]
