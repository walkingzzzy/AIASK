"""
洞察引擎模块
提供机会发现、风险预警、洞察生成等功能
"""
from .models import Opportunity, RiskAlert, Insight, UserProfile
from .opportunity_detector import OpportunityDetector
from .risk_detector import RiskDetector
from .insight_generator import InsightGenerator

__all__ = [
    'OpportunityDetector',
    'Opportunity',
    'RiskDetector', 
    'RiskAlert',
    'InsightGenerator',
    'Insight',
    'UserProfile',
]
