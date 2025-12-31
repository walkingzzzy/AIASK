"""
向量化模型
支持多种向量化模型，包括OpenAI和本地模型
"""
import os
import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """向量化结果"""
    text: str
    embedding: List[float]
    model: str
    dimensions: int


class BaseEmbedding(ABC):
    """向量化模型基类"""
    
    def __init__(self, model_name: str, dimensions: int):
        self.model_name = model_name
        self.dimensions = dimensions
        self._cache: Dict[str, List[float]] = {}
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """向量化单个文本"""
        pass
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        return [self.embed(text) for text in texts]
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def _get_cached(self, text: str) -> Optional[List[float]]:
        """获取缓存的向量"""
        key = self._get_cache_key(text)
        return self._cache.get(key)
    
    def _set_cache(self, text: str, embedding: List[float]):
        """缓存向量"""
        key = self._get_cache_key(text)
        self._cache[key] = embedding


class OpenAIEmbedding(BaseEmbedding):
    """
    OpenAI向量化模型
    使用text-embedding-3-small或text-embedding-ada-002
    """
    
    def __init__(self,
                 model_name: str = "text-embedding-3-small",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None):
        # text-embedding-3-small: 1536维
        # text-embedding-ada-002: 1536维
        dimensions = 1536
        super().__init__(model_name, dimensions)
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._client = None
        self._is_configured = False
        self._using_mock = False
        self._last_error: Optional[str] = None
    
    @property
    def client(self):
        """延迟初始化OpenAI客户端"""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
            except ImportError:
                logger.warning("OpenAI库未安装，使用模拟向量")
                return None
        return self._client
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取向量模型配置状态
        
        Returns:
            包含配置状态的字典
        """
        api_key_configured = bool(self.api_key and not self.api_key.startswith("your_"))
        
        return {
            "model_type": "openai",
            "model_name": self.model_name,
            "is_configured": api_key_configured,
            "using_mock": self._using_mock,
            "last_error": self._last_error,
            "status": "正常" if (api_key_configured and not self._using_mock) else "降级模式",
            "message": self._get_status_message(api_key_configured)
        }
    
    def _get_status_message(self, api_key_configured: bool) -> str:
        """生成状态消息"""
        if not api_key_configured:
            return "OpenAI API Key 未配置，RAG功能使用模拟向量（搜索精度可能降低）"
        if self._using_mock:
            return f"OpenAI API 调用失败，已降级为模拟向量。错误: {self._last_error}"
        return "向量模型正常工作"
    
    def embed(self, text: str) -> List[float]:
        """向量化文本"""
        # 检查缓存
        cached = self._get_cached(text)
        if cached:
            return cached
        
        # 检查API Key配置
        if not self.api_key or self.api_key.startswith("your_"):
            self._using_mock = True
            self._is_configured = False
            embedding = self._mock_embedding(text)
            self._set_cache(text, embedding)
            return embedding
        
        # 如果没有OpenAI客户端，返回模拟向量
        if self.client is None:
            self._using_mock = True
            embedding = self._mock_embedding(text)
        else:
            try:
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=text
                )
                # 处理不同的响应格式
                if hasattr(response, 'data') and len(response.data) > 0:
                    embedding = response.data[0].embedding
                    self._is_configured = True
                    self._using_mock = False
                    self._last_error = None
                elif isinstance(response, dict) and 'data' in response:
                    embedding = response['data'][0]['embedding']
                    self._is_configured = True
                    self._using_mock = False
                    self._last_error = None
                else:
                    logger.warning(f"未知的响应格式，使用模拟向量")
                    self._using_mock = True
                    self._last_error = "未知的响应格式"
                    embedding = self._mock_embedding(text)
            except Exception as e:
                logger.error(f"OpenAI向量化失败: {e}")
                self._using_mock = True
                self._last_error = str(e)
                embedding = self._mock_embedding(text)
        
        self._set_cache(text, embedding)
        return embedding
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        if self.client is None:
            return [self._mock_embedding(t) for t in texts]

        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=texts
            )
            # 处理不同的响应格式
            if hasattr(response, 'data') and len(response.data) > 0:
                return [item.embedding for item in response.data]
            elif isinstance(response, dict) and 'data' in response:
                return [item['embedding'] for item in response['data']]
            else:
                logger.warning(f"未知的响应格式，使用模拟向量")
                return [self._mock_embedding(t) for t in texts]
        except Exception as e:
            logger.error(f"批量向量化失败: {e}")
            return [self._mock_embedding(t) for t in texts]
    
    def _mock_embedding(self, text: str) -> List[float]:
        """生成模拟向量（用于测试）"""
        # 基于文本哈希生成确定性的模拟向量
        np.random.seed(hash(text) % (2**32))
        embedding = np.random.randn(self.dimensions).tolist()
        # 归一化
        norm = np.linalg.norm(embedding)
        return [x / norm for x in embedding]


class LocalEmbedding(BaseEmbedding):
    """
    本地向量化模型
    使用sentence-transformers库
    推荐模型：BAAI/bge-large-zh-v1.5
    """
    
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        # bge-small-zh: 512维
        # bge-large-zh: 1024维
        dimensions = 512 if "small" in model_name else 1024
        super().__init__(model_name, dimensions)
        self._model = None
        self._using_mock = False
        self._last_error: Optional[str] = None
    
    @property
    def model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._using_mock = False
            except ImportError:
                logger.warning("sentence-transformers未安装")
                self._using_mock = True
                self._last_error = "sentence-transformers未安装"
                return None
            except Exception as e:
                logger.warning(f"加载本地模型失败: {e}")
                self._using_mock = True
                self._last_error = str(e)
                return None
        return self._model
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取向量模型配置状态
        
        Returns:
            包含配置状态的字典
        """
        model_loaded = self._model is not None
        
        return {
            "model_type": "local",
            "model_name": self.model_name,
            "is_configured": model_loaded,
            "using_mock": self._using_mock,
            "last_error": self._last_error,
            "status": "正常" if model_loaded else "降级模式",
            "message": self._get_status_message(model_loaded)
        }
    
    def _get_status_message(self, model_loaded: bool) -> str:
        """生成状态消息"""
        if model_loaded:
            return "本地向量模型正常工作"
        if self._last_error:
            return f"本地模型加载失败，使用模拟向量。错误: {self._last_error}"
        return "本地模型未加载，使用模拟向量"
    
    def embed(self, text: str) -> List[float]:
        """向量化文本"""
        cached = self._get_cached(text)
        if cached:
            return cached
        
        if self.model is None:
            self._using_mock = True
            embedding = self._mock_embedding(text)
        else:
            embedding = self.model.encode(text).tolist()
            self._using_mock = False
        
        self._set_cache(text, embedding)
        return embedding
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        if self.model is None:
            self._using_mock = True
            return [self._mock_embedding(t) for t in texts]
        
        self._using_mock = False
        embeddings = self.model.encode(texts)
        return [e.tolist() for e in embeddings]
    
    def _mock_embedding(self, text: str) -> List[float]:
        """生成模拟向量"""
        np.random.seed(hash(text) % (2**32))
        embedding = np.random.randn(self.dimensions).tolist()
        norm = np.linalg.norm(embedding)
        return [x / norm for x in embedding]


# 全局单例
_embedding_instance: Optional[BaseEmbedding] = None


def get_embedding_model(model_type: str = None) -> BaseEmbedding:
    """
    获取向量化模型

    Args:
        model_type: 模型类型 "openai" 或 "local"，默认从环境变量读取
    """
    global _embedding_instance

    if _embedding_instance is None:
        # 从环境变量读取配置
        if model_type is None:
            model_type = os.getenv("EMBEDDING_MODEL_TYPE", "openai")

        if model_type == "openai":
            # 从环境变量读取模型名称
            model_name = os.getenv("OPENAI_MODEL", "text-embedding-3-small")
            _embedding_instance = OpenAIEmbedding(model_name=model_name)
        else:
            model_name = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
            _embedding_instance = LocalEmbedding(model_name=model_name)

    return _embedding_instance


def get_embedding_status() -> Dict[str, Any]:
    """
    获取当前向量模型的配置状态
    
    用于在API响应中返回RAG功能的配置状态，让用户知道RAG是否正常工作。
    
    Returns:
        Dict containing:
        - model_type: 模型类型 ("openai" 或 "local")
        - model_name: 模型名称
        - is_configured: 是否已正确配置
        - using_mock: 是否正在使用模拟向量
        - status: 状态描述 ("正常" 或 "降级模式")
        - message: 详细状态消息
    """
    model = get_embedding_model()
    
    if hasattr(model, 'get_status'):
        return model.get_status()
    
    # 回退：基础状态信息
    return {
        "model_type": "unknown",
        "model_name": model.model_name if hasattr(model, 'model_name') else "unknown",
        "is_configured": False,
        "using_mock": True,
        "status": "未知",
        "message": "无法获取向量模型状态"
    }
