"""
用户画像模块
提供用户画像管理、行为追踪、偏好学习、个性化推荐等功能
"""
from .models import UserProfile, BehaviorEvent, LearningProgress, BehaviorType
from .profile_service import ProfileService
from .behavior_tracker import BehaviorTracker
from .preference_learner import PreferenceLearner
from .recommendation_engine import RecommendationEngine

__all__ = [
    'UserProfile',
    'BehaviorEvent',
    'BehaviorType',
    'LearningProgress',
    'ProfileService',
    'BehaviorTracker',
    'PreferenceLearner',
    'RecommendationEngine',
]
