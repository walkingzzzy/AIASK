"""
对话管理器
支持多轮对话和上下文管理
"""
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """对话消息"""
    role: str  # user, assistant, system
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    def to_llm_message(self) -> Dict:
        """转换为LLM消息格式"""
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass
class ConversationSession:
    """对话会话"""
    session_id: str
    messages: List[ConversationMessage] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """添加消息"""
        message = ConversationMessage(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat()

    def get_recent_messages(self, limit: int = 10) -> List[ConversationMessage]:
        """获取最近的消息"""
        return self.messages[-limit:]

    def get_llm_context(self, limit: int = 6) -> List[Dict]:
        """
        获取LLM上下文

        Args:
            limit: 最多返回的消息数量（user+assistant成对计算）

        Returns:
            List[Dict]: LLM消息列表
        """
        recent = self.get_recent_messages(limit)
        return [msg.to_llm_message() for msg in recent]

    def update_context(self, key: str, value: Any):
        """更新上下文"""
        self.context[key] = value
        self.updated_at = datetime.now().isoformat()

    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文"""
        return self.context.get(key, default)

    def clear_messages(self):
        """清空消息历史"""
        self.messages = []
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "context": self.context,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class ConversationManager:
    """
    对话管理器

    管理多个对话会话，支持：
    1. 会话创建和管理
    2. 消息历史记录
    3. 上下文维护
    4. 会话持久化
    """

    def __init__(self, max_sessions: int = 100):
        """
        初始化对话管理器

        Args:
            max_sessions: 最大会话数量
        """
        self.max_sessions = max_sessions
        self.sessions: Dict[str, ConversationSession] = {}

    def create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        """
        创建新会话

        Args:
            session_id: 会话ID，如果为None则自动生成

        Returns:
            ConversationSession: 新会话
        """
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())

        if session_id in self.sessions:
            logger.warning(f"会话 {session_id} 已存在，将覆盖")

        session = ConversationSession(session_id=session_id)
        self.sessions[session_id] = session

        # 限制会话数量
        if len(self.sessions) > self.max_sessions:
            self._cleanup_old_sessions()

        logger.info(f"创建新会话: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """
        获取会话

        Args:
            session_id: 会话ID

        Returns:
            Optional[ConversationSession]: 会话，不存在返回None
        """
        return self.sessions.get(session_id)

    def get_or_create_session(self, session_id: str) -> ConversationSession:
        """
        获取或创建会话

        Args:
            session_id: 会话ID

        Returns:
            ConversationSession: 会话
        """
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id)
        return session

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否删除成功
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"删除会话: {session_id}")
            return True
        return False

    def add_user_message(self, session_id: str, content: str, metadata: Optional[Dict] = None):
        """
        添加用户消息

        Args:
            session_id: 会话ID
            content: 消息内容
            metadata: 元数据
        """
        session = self.get_or_create_session(session_id)
        session.add_message("user", content, metadata)

    def add_assistant_message(self, session_id: str, content: str, metadata: Optional[Dict] = None):
        """
        添加助手消息

        Args:
            session_id: 会话ID
            content: 消息内容
            metadata: 元数据
        """
        session = self.get_or_create_session(session_id)
        session.add_message("assistant", content, metadata)

    def get_conversation_context(self, session_id: str, limit: int = 6) -> List[Dict]:
        """
        获取对话上下文

        Args:
            session_id: 会话ID
            limit: 最多返回的消息数量

        Returns:
            List[Dict]: LLM消息列表
        """
        session = self.get_session(session_id)
        if session is None:
            return []
        return session.get_llm_context(limit)

    def update_session_context(self, session_id: str, key: str, value: Any):
        """
        更新会话上下文

        Args:
            session_id: 会话ID
            key: 键
            value: 值
        """
        session = self.get_or_create_session(session_id)
        session.update_context(key, value)

    def get_session_context(self, session_id: str, key: str, default: Any = None) -> Any:
        """
        获取会话上下文

        Args:
            session_id: 会话ID
            key: 键
            default: 默认值

        Returns:
            Any: 值
        """
        session = self.get_session(session_id)
        if session is None:
            return default
        return session.get_context(key, default)

    def clear_session_messages(self, session_id: str):
        """
        清空会话消息

        Args:
            session_id: 会话ID
        """
        session = self.get_session(session_id)
        if session:
            session.clear_messages()
            logger.info(f"清空会话消息: {session_id}")

    def _cleanup_old_sessions(self):
        """清理旧会话"""
        # 按更新时间排序，删除最旧的会话
        sorted_sessions = sorted(
            self.sessions.items(),
            key=lambda x: x[1].updated_at
        )

        # 删除超出限制的会话
        to_delete = len(self.sessions) - self.max_sessions + 10
        for session_id, _ in sorted_sessions[:to_delete]:
            del self.sessions[session_id]
            logger.info(f"清理旧会话: {session_id}")

    def save_to_file(self, filepath: str):
        """
        保存会话到文件

        Args:
            filepath: 文件路径
        """
        try:
            data = {
                session_id: session.to_dict()
                for session_id, session in self.sessions.items()
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"保存会话到文件: {filepath}")
        except Exception as e:
            logger.error(f"保存会话失败: {e}")

    def load_from_file(self, filepath: str):
        """
        从文件加载会话

        Args:
            filepath: 文件路径
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for session_id, session_data in data.items():
                session = ConversationSession(
                    session_id=session_id,
                    context=session_data.get("context", {}),
                    created_at=session_data.get("created_at", ""),
                    updated_at=session_data.get("updated_at", "")
                )

                # 恢复消息
                for msg_data in session_data.get("messages", []):
                    message = ConversationMessage(
                        role=msg_data["role"],
                        content=msg_data["content"],
                        timestamp=msg_data.get("timestamp", ""),
                        metadata=msg_data.get("metadata", {})
                    )
                    session.messages.append(message)

                self.sessions[session_id] = session

            logger.info(f"从文件加载会话: {filepath}, 共{len(self.sessions)}个会话")
        except Exception as e:
            logger.error(f"加载会话失败: {e}")


# 全局单例
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """
    获取对话管理器单例

    Returns:
        ConversationManager: 对话管理器实例
    """
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager