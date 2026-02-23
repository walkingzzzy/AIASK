"""情绪分析与用户画像工具"""
import math
from datetime import datetime, timezone
from ..services.sentiment import sentiment_analyzer
from ..storage import get_db
from ..utils import ok, fail

def register(mcp):
    @mcp.tool()
    async def analyze_stock_sentiment(code: str):
        """分析个股市场情绪（三分量复合评分：价量动量+新闻情绪+资金流向）"""
        try:
            db = get_db()
            klines = await db.get_klines(code, limit=100)

            if not klines:
                return fail('No data')

            # Best-effort: fetch news headlines
            news_headlines = []
            try:
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT content FROM vector_documents WHERE stock_code = $1 AND doc_type = 'news' ORDER BY date DESC LIMIT 20",
                        code,
                    )
                    news_headlines = [r['content'][:200] for r in rows if r.get('content')]
            except Exception:
                pass

            # Best-effort: fetch fund flow data
            fund_flow_data = None
            try:
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM stock_fund_flow WHERE code = $1 ORDER BY trade_date DESC LIMIT 1",
                        code,
                    )
                    if row:
                        fund_flow_data = dict(row)
            except Exception:
                pass

            result = sentiment_analyzer.analyze_sentiment(klines, news_headlines, fund_flow_data)
            result['code'] = code

            return ok(result)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def calculate_fear_greed_index():
        """计算市场恐惧贪婪指数（基于上证指数K线和涨跌停统计）"""
        try:
            db = get_db()
            index_klines = await db.get_klines('sh000001', limit=60)
            breadth_data = None
            try:
                limit_up = await db.get_limit_up_stats()
                if limit_up:
                    breadth_data = limit_up
            except Exception:
                pass
            result = sentiment_analyzer.calculate_fear_greed_index(
                index_klines=index_klines or None,
                breadth_data=breadth_data,
            )
            return ok(result)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def update_user_profile(
        user_id: str = 'default',
        neuroticism: float = 0.5,
        openness: float = 0.5,
        herd_tendency: float = 0.5,
        greed_fear_axis: float = 0.0,
        confidence: float = 0.5,
    ):
        """更新用户投资者画像快照（AI推断的大五人格维度）

        Args:
            user_id: 用户ID
            neuroticism: 神经质程度 0~1
            openness: 开放性 0~1
            herd_tendency: 从众倾向 0~1
            greed_fear_axis: 贪婪恐惧轴 -1~1
            confidence: 置信度 0~1
        """
        try:
            db = get_db()
            async with db.acquire() as conn:
                await conn.execute(
                    """INSERT INTO user_profile_snapshots
                       (user_id, neuroticism, openness, herd_tendency, greed_fear_axis, confidence, source)
                       VALUES ($1, $2, $3, $4, $5, $6, 'ai_inference')""",
                    user_id,
                    max(0.0, min(1.0, neuroticism)),
                    max(0.0, min(1.0, openness)),
                    max(0.0, min(1.0, herd_tendency)),
                    max(-1.0, min(1.0, greed_fear_axis)),
                    max(0.0, min(1.0, confidence)),
                )
            return ok({'user_id': user_id, 'recorded': True})
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_user_profile(user_id: str = 'default'):
        """获取用户投资者画像（指数衰减加权平均，半衰期7天）

        Args:
            user_id: 用户ID
        """
        try:
            db = get_db()
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT neuroticism, openness, herd_tendency, greed_fear_axis, confidence, created_at
                       FROM user_profile_snapshots
                       WHERE user_id = $1
                       ORDER BY created_at DESC
                       LIMIT 50""",
                    user_id,
                )
            if not rows:
                return ok({'user_id': user_id, 'profile': None, 'message': 'No profile data'})

            now = datetime.now(timezone.utc)
            half_life_days = 7.0
            decay_rate = math.log(2) / half_life_days

            total_weight = 0.0
            weighted = {'neuroticism': 0.0, 'openness': 0.0, 'herd_tendency': 0.0, 'greed_fear_axis': 0.0, 'confidence': 0.0}

            for row in rows:
                age_days = (now - row['created_at'].replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
                w = math.exp(-decay_rate * age_days)
                total_weight += w
                for key in weighted:
                    weighted[key] += w * float(row[key] or 0)

            if total_weight > 0:
                for key in weighted:
                    weighted[key] = round(weighted[key] / total_weight, 4)

            latest = dict(rows[0])
            latest['created_at'] = str(latest['created_at'])

            return ok({
                'user_id': user_id,
                'weighted_profile': weighted,
                'latest_snapshot': latest,
                'snapshot_count': len(rows),
            })
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def log_recommendation_audit(
        user_id: str = 'default',
        strategy_id: str = '',
        stock_code: str = '',
        action: str = '',
        emotion_polarity: float = 0.0,
        emotion_intensity: float = 0.0,
        cognitive_biases: str = '',
        risk_aversion: float = 2.5,
        kyc_level: str = '',
        reasoning_chain: str = '',
    ):
        """记录推荐审计日志（推荐策略/股票时必须调用）

        Args:
            user_id: 用户ID
            strategy_id: 策略ID
            stock_code: 股票代码
            action: 推荐动作 buy/sell/hold
            emotion_polarity: 情绪极性 -1~1
            emotion_intensity: 情绪强度 0~1
            cognitive_biases: 逗号分隔的认知偏差列表
            risk_aversion: 风险厌恶系数
            kyc_level: KYC等级
            reasoning_chain: 推理链路说明
        """
        try:
            db = get_db()
            biases_list = [b.strip() for b in cognitive_biases.split(',') if b.strip()] if cognitive_biases else []

            async with db.acquire() as conn:
                await conn.execute(
                    """INSERT INTO recommendation_audit_log
                       (user_id, strategy_id, stock_code, action,
                        emotion_polarity, emotion_intensity, cognitive_biases,
                        risk_aversion, kyc_level, reasoning_chain)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    user_id, strategy_id or None, stock_code or None, action,
                    emotion_polarity, emotion_intensity, biases_list,
                    risk_aversion, kyc_level or None, reasoning_chain,
                )
            return ok({'logged': True})
        except Exception as e:
            return fail(str(e))
