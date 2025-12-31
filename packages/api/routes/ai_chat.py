"""
AI对话API路由
提供增强的AI对话功能，包括人格化响应、情绪响应、流式输出等
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio
import json
import logging

from packages.core.personality import (
    AI_CHARACTER,
    ResponseEnhancer,
    EmotionResponder,
    MemoryNarrator
)
from packages.core.personality.emotion_responder import EmotionContext
from packages.core.personality.memory_narrator import MemoryData

logger = logging.getLogger(__name__)
from packages.core.user_profile import ProfileService

router = APIRouter(prefix="/ai", tags=["AI对话"])

# 初始化服务
profile_service = ProfileService()
response_enhancer = ResponseEnhancer()
emotion_responder = EmotionResponder()
memory_narrator = MemoryNarrator()


# ==================== 请求模型 ====================

class ChatRequest(BaseModel):
    """对话请求"""
    message: str
    context: Dict[str, Any] = {}
    stream: bool = False


class EmotionContextRequest(BaseModel):
    """情绪上下文请求"""
    market_change: float = 0.0
    user_profit: float = 0.0
    consecutive_days: int = 0
    win_streak: int = 0
    loss_streak: int = 0
    concepts_learned: int = 0
    days_since_last_visit: int = 0
    stock_name: Optional[str] = None
    stock_code: Optional[str] = None


class EnhanceRequest(BaseModel):
    """响应增强请求"""
    response: str
    context: Dict[str, Any] = {}


# ==================== 问候与人格 ====================

@router.get("/greeting")
async def get_greeting(user_id: str = Query("default", description="用户ID")):
    """
    获取个性化问候语
    """
    try:
        profile = profile_service.get_profile(user_id)
        
        # 构建上下文
        context = {
            'consecutive_days': profile.usage_stats.consecutive_days,
            'days_absent': 0  # 可以从last_active_date计算
        }
        
        if profile.usage_stats.last_active_date:
            from datetime import datetime
            last_date = datetime.strptime(profile.usage_stats.last_active_date, "%Y-%m-%d")
            days_absent = (datetime.now() - last_date).days
            context['days_absent'] = days_absent
        
        greeting = AI_CHARACTER.get_greeting(context)
        
        # 如果有昵称，添加称呼
        if profile.nickname:
            greeting = f"{profile.nickname}，" + greeting
        
        return {
            "success": True,
            "data": {
                "greeting": greeting,
                "ai_name": AI_CHARACTER.name,
                "consecutive_days": profile.usage_stats.consecutive_days
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/character")
async def get_character():
    """
    获取AI人格配置
    """
    return {
        "success": True,
        "data": {
            "name": AI_CHARACTER.name,
            "avatar": AI_CHARACTER.avatar,
            "traits": AI_CHARACTER.traits
        }
    }


# ==================== 响应增强 ====================

@router.post("/enhance")
async def enhance_response(
    request: EnhanceRequest,
    user_id: str = Query("default", description="用户ID")
):
    """
    增强AI响应
    
    根据用户画像和上下文增强响应内容
    """
    try:
        profile = profile_service.get_profile(user_id)
        
        user_profile_dict = {
            'knowledge_level': profile.knowledge_level.value,
            'nickname': profile.nickname,
            'ai_personality': profile.ai_personality
        }
        
        enhanced = response_enhancer.enhance(
            response=request.response,
            user_profile=user_profile_dict,
            context=request.context
        )
        
        return {
            "success": True,
            "data": {
                "original": request.response,
                "enhanced": enhanced
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 情绪响应 ====================

@router.post("/emotion")
async def get_emotion_response(
    request: EmotionContextRequest,
    user_id: str = Query("default", description="用户ID")
):
    """
    获取情绪响应
    
    根据市场状况和用户情况生成情绪化响应
    """
    try:
        context = EmotionContext(
            market_change=request.market_change,
            user_profit=request.user_profit,
            consecutive_days=request.consecutive_days,
            win_streak=request.win_streak,
            loss_streak=request.loss_streak,
            concepts_learned=request.concepts_learned,
            days_since_last_visit=request.days_since_last_visit,
            stock_name=request.stock_name,
            stock_code=request.stock_code
        )
        
        # 检测触发器
        triggers = emotion_responder.detect_emotion_triggers(context)
        
        # 生成响应
        responses = emotion_responder.generate_all_responses(context)
        
        return {
            "success": True,
            "data": {
                "triggers": triggers,
                "responses": responses
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comfort")
async def get_comfort_message(
    loss_percent: float = Query(..., description="亏损百分比"),
    stock_name: Optional[str] = Query(None, description="股票名称")
):
    """
    获取安慰消息
    """
    try:
        message = emotion_responder.get_comfort_message(loss_percent, stock_name)
        
        return {
            "success": True,
            "data": {"message": message}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/encouragement")
async def get_encouragement(
    achievement: str = Query(..., description="成就类型"),
    days: Optional[int] = Query(None, description="天数"),
    count: Optional[int] = Query(None, description="数量"),
    improvement: Optional[float] = Query(None, description="提升百分比")
):
    """
    获取鼓励消息
    """
    try:
        context = {}
        if days:
            context['days'] = days
        if count:
            context['count'] = count
        if improvement:
            context['improvement'] = improvement
        
        message = emotion_responder.get_encouragement_message(achievement, context)
        
        return {
            "success": True,
            "data": {"message": message}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warning")
async def get_warning(
    warning_type: str = Query(..., description="警示类型")
):
    """
    获取警示消息
    """
    try:
        message = emotion_responder.get_warning_message(warning_type)
        
        return {
            "success": True,
            "data": {"message": message}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 记忆叙述 ====================

@router.get("/memory")
async def get_memory_narrative(
    user_id: str = Query("default", description="用户ID"),
    narrative_type: str = Query("summary", description="叙述类型")
):
    """
    获取记忆叙述
    """
    try:
        profile = profile_service.get_profile(user_id)
        
        # 构建记忆数据
        memory = MemoryData(
            user_id=user_id,
            first_active_date=profile.usage_stats.first_active_date,
            total_days=profile.usage_stats.consecutive_days,
            total_queries=profile.usage_stats.total_queries,
            concepts_learned=len(profile.learning_progress.learned_concepts)
        )
        
        # 计算总天数
        if profile.usage_stats.first_active_date:
            first_date = datetime.strptime(profile.usage_stats.first_active_date, "%Y-%m-%d")
            memory.total_days = (datetime.now() - first_date).days + 1
        
        result = {}
        
        if narrative_type == "summary":
            result = memory_narrator.get_memory_summary(memory)
        elif narrative_type == "shared_experience":
            result = {"narrative": memory_narrator.generate_shared_experience(memory)}
        elif narrative_type == "learning_progress":
            result = {"narrative": memory_narrator.generate_learning_progress(memory)}
        elif narrative_type == "anniversary":
            result = {"narrative": memory_narrator.generate_anniversary_narrative(memory)}
        elif narrative_type == "greeting":
            result = {"greeting": memory_narrator.generate_personalized_greeting(memory)}
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 流式对话 ====================

@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: str = Query("default", description="用户ID")
):
    """
    流式对话接口
    
    返回Server-Sent Events格式的流式响应
    """
    try:
        profile = profile_service.get_profile(user_id)
        
        async def generate():
            # 模拟流式响应（实际应该调用LLM服务）
            response = await _generate_chat_response(request.message, profile, request.context)
            
            # 逐字输出
            for char in response:
                yield f"data: {json.dumps({'content': char})}\n\n"
                await asyncio.sleep(0.02)  # 模拟打字效果
            
            yield f"data: {json.dumps({'done': True})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Query("default", description="用户ID")
):
    """
    普通对话接口
    """
    try:
        profile = profile_service.get_profile(user_id)
        
        # 获取LLM配置状态
        llm_status = _get_llm_config_status()
        
        response = await _generate_chat_response(request.message, profile, request.context)
        
        # 增强响应
        user_profile_dict = {
            'knowledge_level': profile.knowledge_level.value,
            'nickname': profile.nickname,
            'ai_personality': profile.ai_personality
        }
        
        enhanced = response_enhancer.enhance(
            response=response,
            user_profile=user_profile_dict,
            context=request.context
        )
        
        result = {
            "success": True,
            "data": {
                "response": enhanced,
                "ai_name": AI_CHARACTER.name,
                "config_status": llm_status
            }
        }
        
        # 如果使用降级模式，在响应中添加提示
        if not llm_status.get("is_configured"):
            result["data"]["degraded_mode"] = True
            result["data"]["degraded_notice"] = llm_status.get("message", "AI对话正在使用降级模式")
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _generate_chat_response(message: str, profile, context: Dict) -> str:
    """
    生成对话响应
    
    优先使用LLM服务，如果不可用则降级为关键词匹配
    """
    # 尝试使用LLM服务
    try:
        llm_response = await _call_llm_service(message, profile, context)
        if llm_response:
            return llm_response
    except Exception as e:
        logger.warning(f"LLM服务调用失败，降级为关键词匹配: {e}")
    
    # 降级：简单的关键词匹配响应
    message_lower = message.lower()
    
    if any(kw in message_lower for kw in ['你好', 'hi', 'hello', '嗨']):
        return AI_CHARACTER.get_greeting({
            'consecutive_days': profile.usage_stats.consecutive_days
        })
    
    if any(kw in message_lower for kw in ['你是谁', '介绍', '自我介绍']):
        return f"我是{AI_CHARACTER.name}，您的AI投资助手。我可以帮您分析股票、解读市场、学习投资知识。有什么我可以帮您的吗？"
    
    if any(kw in message_lower for kw in ['谢谢', '感谢', 'thanks']):
        return "不客气！能帮到您是我的荣幸。还有其他问题吗？"
    
    if any(kw in message_lower for kw in ['再见', 'bye', '拜拜']):
        return "再见！祝您投资顺利，有问题随时找我！"
    
    if any(kw in message_lower for kw in ['大盘', '市场', '行情']):
        return "让我为您分析一下当前市场情况。今日A股三大指数表现分化，成交量较昨日有所变化。建议关注北向资金流向和板块轮动情况。"
    
    if any(kw in message_lower for kw in ['推荐', '买什么', '选股']):
        return "投资建议需要根据您的风险偏好和投资目标来定制。我可以帮您分析具体的股票，或者根据您的偏好筛选潜在标的。请告诉我您感兴趣的方向？"
    
    # 默认响应
    return f"我理解您的问题是关于「{message[:20]}...」。让我为您分析一下。作为您的AI投资助手，我会尽力提供专业的分析和建议。请问您想了解哪方面的具体信息？"


async def _call_llm_service(message: str, profile, context: Dict) -> Optional[str]:
    """
    调用LLM服务生成响应
    
    支持OpenAI兼容的API
    """
    import os
    import httpx
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    if not api_key or api_key.startswith("your_"):
        logger.debug("OpenAI API Key未配置，跳过LLM调用")
        return None
    
    # 构建系统提示
    system_prompt = f"""你是{AI_CHARACTER.name}，一个专业的A股投资分析助手。

你的特点：
- 专业：精通A股市场分析、技术指标、基本面分析
- 友好：用通俗易懂的语言解释复杂概念
- 谨慎：始终提醒投资风险，不做绝对的买卖建议

用户信息：
- 投资风格：{profile.investment_style.value if hasattr(profile, 'investment_style') else '未知'}
- 知识水平：{profile.knowledge_level.value if hasattr(profile, 'knowledge_level') else '中级'}

请根据用户的问题提供专业、有价值的回答。回答要简洁明了，避免过长。"""

    # 构建消息
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message}
    ]
    
    # 如果有上下文，添加到消息中
    if context.get("stock_code"):
        messages.insert(1, {
            "role": "system", 
            "content": f"当前讨论的股票：{context.get('stock_name', '')}({context.get('stock_code')})"
        })
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo"),
                    "messages": messages,
                    "max_tokens": 500,
                    "temperature": 0.7
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.warning(f"LLM API返回错误: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"LLM API调用异常: {e}")
        return None


def _get_llm_config_status() -> Dict[str, Any]:
    """
    获取LLM配置状态
    
    Returns:
        Dict containing:
        - is_configured: 是否已配置LLM API
        - model: 使用的模型
        - status: 状态描述
        - message: 详细状态消息
    """
    import os
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-3.5-turbo")
    
    is_configured = bool(api_key and not api_key.startswith("your_"))
    
    if is_configured:
        return {
            "is_configured": True,
            "model": model,
            "base_url": base_url,
            "status": "正常",
            "message": f"AI对话服务正常运行，使用模型: {model}"
        }
    else:
        return {
            "is_configured": False,
            "model": None,
            "base_url": None,
            "status": "降级模式",
            "message": "OpenAI API Key 未配置，AI对话正在使用模板回复模式。如需完整AI功能，请在 .env 文件中配置 OPENAI_API_KEY"
        }


@router.get("/status")
async def get_ai_status():
    """
    获取AI服务配置状态
    
    返回LLM和向量模型的配置状态，帮助用户了解AI功能是否正常工作
    """
    try:
        llm_status = _get_llm_config_status()
        
        # 获取向量模型状态
        try:
            from packages.core.vector_store.embeddings.embedding_models import get_embedding_status
            embedding_status = get_embedding_status()
        except Exception as e:
            logger.warning(f"获取向量模型状态失败: {e}")
            embedding_status = {
                "is_configured": False,
                "status": "未知",
                "message": "无法获取向量模型状态"
            }
        
        # 综合状态
        all_configured = llm_status.get("is_configured") and embedding_status.get("is_configured")
        
        return {
            "success": True,
            "data": {
                "overall_status": "正常" if all_configured else "部分功能降级",
                "llm": llm_status,
                "embedding": embedding_status,
                "recommendations": _get_config_recommendations(llm_status, embedding_status)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_config_recommendations(llm_status: Dict, embedding_status: Dict) -> List[str]:
    """生成配置建议"""
    recommendations = []
    
    if not llm_status.get("is_configured"):
        recommendations.append("配置 OPENAI_API_KEY 以启用智能对话功能")
    
    if not embedding_status.get("is_configured") or embedding_status.get("using_mock"):
        recommendations.append("配置向量模型以提高知识库搜索精度")
    
    if not recommendations:
        recommendations.append("所有AI功能已正常配置")
    
    return recommendations
