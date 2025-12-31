"""
配置管理模块
从环境变量和.env文件加载配置
"""
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def load_env_file(env_path: Optional[str] = None):
    """
    加载.env文件

    Args:
        env_path: .env文件路径，默认为项目根目录的.env
    """
    if env_path is None:
        # 查找项目根目录的.env文件
        current_dir = Path(__file__).parent
        while current_dir != current_dir.parent:
            env_file = current_dir / ".env"
            if env_file.exists():
                env_path = str(env_file)
                break
            current_dir = current_dir.parent

    if env_path and os.path.exists(env_path):
        logger.info(f"加载环境配置: {env_path}")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue
                # 解析键值对
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 只在环境变量不存在时设置
                    if key and not os.getenv(key):
                        os.environ[key] = value
        logger.info("环境配置加载完成")
    else:
        logger.warning("未找到.env文件，使用默认配置")


class Config:
    """配置类"""

    def __init__(self):
        # 加载.env文件
        load_env_file()

        # OpenAI配置
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "text-embedding-3-small")

        # 数据库配置
        self.VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./data/stock_vectors.db")

        # 向量化模型配置
        self.EMBEDDING_MODEL_TYPE = os.getenv("EMBEDDING_MODEL_TYPE", "openai")
        self.LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

        # 后端服务配置
        self.BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
        self.BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

        # 日志配置
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE", "./logs/app.log")

        # 缓存配置
        self.CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        self.CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))

        # 其他配置
        self.DEBUG = os.getenv("DEBUG", "false").lower() == "true"
        self.CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

    def validate(self) -> bool:
        """验证配置"""
        errors = []

        # 检查必需的配置
        if self.EMBEDDING_MODEL_TYPE == "openai" and not self.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY未设置")

        if errors:
            logger.error("配置验证失败:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        return True

    def print_config(self):
        """打印配置信息（隐藏敏感信息）"""
        logger.info("=" * 60)
        logger.info("当前配置:")
        logger.info("=" * 60)
        logger.info(f"OpenAI Base URL: {self.OPENAI_BASE_URL}")
        logger.info(f"OpenAI Model: {self.OPENAI_MODEL}")
        logger.info(f"OpenAI API Key: {'*' * 20 if self.OPENAI_API_KEY else '未设置'}")
        logger.info(f"Embedding Model Type: {self.EMBEDDING_MODEL_TYPE}")
        logger.info(f"Vector DB Path: {self.VECTOR_DB_PATH}")
        logger.info(f"Backend: {self.BACKEND_HOST}:{self.BACKEND_PORT}")
        logger.info(f"Debug Mode: {self.DEBUG}")
        logger.info("=" * 60)


# 全局配置实例
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """获取配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


# 在模块导入时自动加载配置
load_env_file()
