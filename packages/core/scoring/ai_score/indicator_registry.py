"""
指标注册器模块
提供统一的指标基类和注册机制
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass
from enum import Enum


class IndicatorCategory(Enum):
    """指标类别"""
    TECHNICAL = "technical"  # 技术面
    FUNDAMENTAL = "fundamental"  # 基本面
    FUND_FLOW = "fund_flow"  # 资金面
    SENTIMENT = "sentiment"  # 情绪面
    RISK = "risk"  # 风险面


@dataclass
class IndicatorResult:
    """统一的指标计算结果"""
    name: str  # 指标名称
    value: Any  # 指标值
    score: float  # 标准化分数 (0-100)
    signal: str  # 信号:'bullish', 'bearish', 'neutral'
    strength: float  # 信号强度 (0-1)
    description: str  # 描述
    category: IndicatorCategory  # 类别
    extra_data: Optional[Dict[str, Any]] = None  # 额外数据


class IndicatorBase(ABC):
    """指标基类
    
    所有指标都需要继承此基类并实现相应的方法。
    """
    
    # 子类需要定义这些类属性
    name: str = "BaseIndicator"
    display_name: str = "基础指标"
    category: IndicatorCategory = IndicatorCategory.TECHNICAL
    description: str = "指标描述"
    
    @abstractmethod
    def calculate(self, **kwargs) -> Dict[str, Any]:
        """计算指标值
        
        Args:
            **kwargs: 计算所需的数据参数
            
        Returns:
            包含指标值的字典
        """
        pass
    
    @abstractmethod
    def get_score(self, value: Any) -> float:
        """将指标值转换为0-100的标准化分数
        
        Args:
            value: 指标原始值
            
        Returns:
            0-100的标准化分数
        """
        pass
    
    def get_signal(self, value: Any) -> str:
        """根据指标值判断信号
        
        Args:
            value: 指标原始值
            
        Returns:
            'bullish', 'bearish', 或 'neutral'
        """
        score = self.get_score(value)
        if score >= 60:
            return 'bullish'
        elif score <= 40:
            return 'bearish'
        else:
            return 'neutral'
    
    def get_strength(self, value: Any) -> float:
        """获取信号强度
        
        Args:
            value: 指标原始值
            
        Returns:
            0-1的信号强度
        """
        score = self.get_score(value)
        # 分数偏离50的程度决定强度
        return min(abs(score - 50) / 50, 1.0)
    
    def get_result(self, **kwargs) -> IndicatorResult:
        """获取完整的指标结果
        
        Args:
            **kwargs: 计算所需的数据参数
            
        Returns:
            IndicatorResult对象
        """
        try:
            calc_result = self.calculate(**kwargs)
            value = calc_result.get('value')
            score = self.get_score(value)
            signal = self.get_signal(value)
            strength = self.get_strength(value)
            desc = calc_result.get('description', self.description)
            
            return IndicatorResult(
                name=self.name,
                value=value,
                score=score,
                signal=signal,
                strength=strength,
                description=desc,
                category=self.category,
                extra_data=calc_result.get('extra_data')
            )
        except Exception as e:
            # 错误处理：返回中性结果
            return IndicatorResult(
                name=self.name,
                value=None,
                score=50.0,
                signal='neutral',
                strength=0.0,
                description=f"计算错误: {str(e)}",
                category=self.category,
                extra_data={'error': str(e)}
            )


class IndicatorRegistry:
    """指标注册器
    
    管理所有指标的注册和获取。
    使用示例:registry = IndicatorRegistry()
        registry.register(MyIndicator())
        
        # 获取所有指标
        all_indicators = registry.get_all_indicators()
        
        # 获取特定类别的指标
        technical_indicators = registry.get_by_category(IndicatorCategory.TECHNICAL)
    """
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._indicators: Dict[str, IndicatorBase] = {}
            cls._instance._categories: Dict[IndicatorCategory, List[str]] = {
                cat: [] for cat in IndicatorCategory
            }
        return cls._instance
    
    def register(self, indicator: IndicatorBase) -> None:
        """注册一个指标
        
        Args:
            indicator: 指标实例
        """
        name = indicator.name
        if name in self._indicators:
            # 如果已存在，覆盖
            old_category = self._indicators[name].category
            if name in self._categories[old_category]:
                self._categories[old_category].remove(name)
        
        self._indicators[name] = indicator
        self._categories[indicator.category].append(name)
    def register_class(self, indicator_class: Type[IndicatorBase]) -> None:
        """注册一个指标类（自动实例化）
        
        Args:
            indicator_class: 指标类
        """
        self.register(indicator_class())
    
    def unregister(self, name: str) -> bool:
        """取消注册一个指标
        
        Args:
            name: 指标名称
            
        Returns:
            是否成功取消注册
        """
        if name in self._indicators:
            category = self._indicators[name].category
            del self._indicators[name]
            if name in self._categories[category]:
                self._categories[category].remove(name)
            return True
        return False
    
    def get(self, name: str) -> Optional[IndicatorBase]:
        """获取一个指标
        
        Args:
            name: 指标名称
            
        Returns:
            指标实例或None
        """
        return self._indicators.get(name)
    
    def get_all_indicators(self) -> List[IndicatorBase]:
        """获取所有已注册的指标
        
        Returns:
            指标列表
        """
        return list(self._indicators.values())
    
    def get_by_category(self, category: IndicatorCategory) -> List[IndicatorBase]:
        """获取指定类别的所有指标
        
        Args:
            category: 指标类别
            
        Returns:
            该类别的指标列表
        """
        return [self._indicators[name] for name in self._categories[category]
                if name in self._indicators]
    
    def get_all_names(self) -> List[str]:
        """获取所有指标名称
        
        Returns:
            指标名称列表
        """
        return list(self._indicators.keys())
    
    def get_names_by_category(self, category: IndicatorCategory) -> List[str]:
        """获取指定类别的所有指标名称
        
        Args:
            category: 指标类别
            
        Returns:
            该类别的指标名称列表
        """
        return self._categories[category].copy()
    
    def count(self) -> int:
        """获取已注册的指标总数
        
        Returns:
            指标总数
        """
        return len(self._indicators)
    
    def count_by_category(self) -> Dict[str, int]:
        """获取各类别的指标数量
        
        Returns:
            类别名称到数量的映射
        """
        return {cat.value: len(names) for cat, names in self._categories.items()}
    
    def clear(self) -> None:
        """清空所有注册的指标"""
        self._indicators.clear()
        for cat in self._categories:
            self._categories[cat].clear()
    
    def calculate_all(self, **kwargs) -> Dict[str, IndicatorResult]:
        """计算所有指标
        
        Args:
            **kwargs: 计算所需的数据参数
            
        Returns:
            指标名称到结果的映射
        """
        results = {}
        for name, indicator in self._indicators.items():
            try:
                results[name] = indicator.get_result(**kwargs)
            except Exception as e:
                results[name] = IndicatorResult(
                    name=name,
                    value=None,
                    score=50.0,
                    signal='neutral',
                    strength=0.0,
                    description=f"计算错误: {str(e)}",
                    category=indicator.category,
                    extra_data={'error': str(e)}
                )
        return results
    def calculate_by_category(
        self, 
        category: IndicatorCategory, 
        **kwargs
    ) -> Dict[str, IndicatorResult]:
        """计算指定类别的所有指标
        
        Args:
            category: 指标类别
            **kwargs: 计算所需的数据参数
            
        Returns:
            指标名称到结果的映射
        """
        results = {}
        for indicator in self.get_by_category(category):
            try:
                results[indicator.name] = indicator.get_result(**kwargs)
            except Exception as e:
                results[indicator.name] = IndicatorResult(
                    name=indicator.name,
                    value=None,
                    score=50.0,
                    signal='neutral',
                    strength=0.0,
                    description=f"计算错误: {str(e)}",
                    category=category,
                    extra_data={'error': str(e)}
                )
        return results


# 全局注册器实例
_global_registry = None


def get_registry() -> IndicatorRegistry:
    """获取全局指标注册器
    
    Returns:
        全局IndicatorRegistry实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = IndicatorRegistry()
    return _global_registry


def register_indicator(indicator: IndicatorBase) -> None:
    """便捷函数：注册一个指标到全局注册器
    
    Args:
        indicator: 指标实例
    """
    get_registry().register(indicator)


def register_indicator_class(indicator_class: Type[IndicatorBase]) -> None:
    """便捷函数：注册一个指标类到全局注册器
    
    Args:
        indicator_class: 指标类
    """
    get_registry().register_class(indicator_class)


# 装饰器：用于自动注册指标类
def auto_register(cls: Type[IndicatorBase]) -> Type[IndicatorBase]:
    """装饰器：自动注册指标类到全局注册器
    
    使用示例:
        @auto_register
        class MyIndicator(IndicatorBase):
            name = "my_indicator"
            ...
    """
    register_indicator_class(cls)
    return cls