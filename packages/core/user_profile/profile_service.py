"""
用户画像服务
提供用户画像的CRUD操作
"""
import json
import logging
import tempfile
import os
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from .models import UserProfile, UsageStats, AIRelationship

logger = logging.getLogger(__name__)


class ProfileService:
    """
    用户画像服务
    
    负责用户画像的存储、读取、更新
    """
    
    def __init__(self, storage_path: str = "data/user_profiles"):
        """
        初始化画像服务
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, UserProfile] = {}
    
    def get_profile(self, user_id: str) -> UserProfile:
        """
        获取用户画像
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户画像，如果不存在则创建默认画像
        """
        # 先检查缓存
        if user_id in self._cache:
            return self._cache[user_id]
        
        # 从文件加载
        profile_path = self.storage_path / f"{user_id}.json"
        
        if profile_path.exists():
            try:
                with open(profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                profile = UserProfile.from_dict(data)
                self._cache[user_id] = profile
                return profile
            except Exception as e:
                logger.error(f"加载用户画像失败 {user_id}: {e}")
        
        # 创建默认画像
        profile = self._create_default_profile(user_id)
        self.save_profile(profile)
        return profile
    
    def save_profile(self, profile: UserProfile) -> bool:
        """
        保存用户画像（原子写入，先写临时文件再重命名）
        
        Args:
            profile: 用户画像
            
        Returns:
            是否保存成功
        """
        try:
            profile.updated_at = datetime.now()
            profile_path = self.storage_path / f"{profile.user_id}.json"
            
            # 原子写入：先写临时文件，再重命名
            fd, temp_path = tempfile.mkstemp(
                dir=self.storage_path,
                suffix='.tmp',
                prefix=f"{profile.user_id}_"
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
                # 原子重命名
                os.replace(temp_path, profile_path)
            except Exception:
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
            
            self._cache[profile.user_id] = profile
            return True
        except Exception as e:
            logger.error(f"保存用户画像失败 {profile.user_id}: {e}")
            return False
    
    def update_profile(self, user_id: str, updates: Dict[str, Any]) -> Optional[UserProfile]:
        """
        更新用户画像
        
        Args:
            user_id: 用户ID
            updates: 更新内容
            
        Returns:
            更新后的画像
        """
        profile = self.get_profile(user_id)
        
        # 更新基本字段
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        self.save_profile(profile)
        return profile
    
    def update_watchlist(self, user_id: str, watchlist: list) -> UserProfile:
        """更新自选股列表"""
        profile = self.get_profile(user_id)
        profile.watchlist = watchlist
        self.save_profile(profile)
        return profile
    
    def update_holdings(self, user_id: str, holdings: list) -> UserProfile:
        """更新持仓列表"""
        profile = self.get_profile(user_id)
        profile.holdings = holdings
        self.save_profile(profile)
        return profile
    
    def update_usage_stats(self, user_id: str, stats_update: Dict[str, Any]) -> UserProfile:
        """更新使用统计"""
        profile = self.get_profile(user_id)
        
        for key, value in stats_update.items():
            if hasattr(profile.usage_stats, key):
                setattr(profile.usage_stats, key, value)
        
        self.save_profile(profile)
        return profile
    
    def update_ai_relationship(self, user_id: str, 
                                followed_suggestion: bool = None,
                                feedback_positive: bool = None) -> UserProfile:
        """更新AI关系数据"""
        profile = self.get_profile(user_id)
        
        if followed_suggestion is not None:
            profile.ai_relationship.total_suggestions += 1
            if followed_suggestion:
                profile.ai_relationship.followed_suggestions += 1
            profile.ai_relationship.update_follow_rate()
            
            # 更新信任度
            if followed_suggestion:
                profile.ai_relationship.trust_level = min(100, 
                    profile.ai_relationship.trust_level + 1)
        
        if feedback_positive is not None:
            profile.ai_relationship.feedback_count += 1
            if feedback_positive:
                profile.ai_relationship.positive_feedback += 1
                profile.ai_relationship.trust_level = min(100,
                    profile.ai_relationship.trust_level + 2)
            else:
                profile.ai_relationship.trust_level = max(0,
                    profile.ai_relationship.trust_level - 1)
        
        self.save_profile(profile)
        return profile
    
    def record_daily_active(self, user_id: str) -> UserProfile:
        """记录每日活跃"""
        profile = self.get_profile(user_id)
        today = datetime.now().strftime("%Y-%m-%d")
        
        if profile.usage_stats.last_active_date != today:
            # 检查是否连续
            if profile.usage_stats.last_active_date:
                from datetime import timedelta
                last_date = datetime.strptime(profile.usage_stats.last_active_date, "%Y-%m-%d")
                if (datetime.now() - last_date).days == 1:
                    profile.usage_stats.consecutive_days += 1
                else:
                    profile.usage_stats.consecutive_days = 1
            else:
                profile.usage_stats.consecutive_days = 1
            
            # 更新最长连续天数
            if profile.usage_stats.consecutive_days > profile.usage_stats.longest_streak:
                profile.usage_stats.longest_streak = profile.usage_stats.consecutive_days
            
            profile.usage_stats.last_active_date = today
            
            if not profile.usage_stats.first_active_date:
                profile.usage_stats.first_active_date = today
            
            self.save_profile(profile)
        
        return profile
    
    def delete_profile(self, user_id: str) -> bool:
        """删除用户画像"""
        try:
            profile_path = self.storage_path / f"{user_id}.json"
            if profile_path.exists():
                profile_path.unlink()
            if user_id in self._cache:
                del self._cache[user_id]
            return True
        except Exception as e:
            logger.error(f"删除用户画像失败 {user_id}: {e}")
            return False
    
    def _create_default_profile(self, user_id: str) -> UserProfile:
        """创建默认用户画像"""
        return UserProfile(
            user_id=user_id,
            focus_sectors=["科技", "消费", "医药"],
            preferred_data_types=["technical", "fundamental", "fund_flow"],
            usage_stats=UsageStats(
                first_active_date=datetime.now().strftime("%Y-%m-%d"),
                last_active_date=datetime.now().strftime("%Y-%m-%d"),
                consecutive_days=1
            )
        )
