"""
AI人格模块
提供AI人格配置、响应增强、情绪响应、记忆叙述等功能
"""
from .character_config import AICharacter, AI_CHARACTER
from .response_enhancer import ResponseEnhancer
from .emotion_responder import EmotionResponder
from .memory_narrator import MemoryNarrator

__all__ = [
    'AICharacter',
    'AI_CHARACTER',
    'ResponseEnhancer',
    'EmotionResponder',
    'MemoryNarrator',
]
