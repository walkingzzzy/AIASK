import type OpenAI from 'openai';

export type UserContextForPrompt = {
  riskLevel?: string;
  recentEmotions?: string[];
  kycLevel?: string;
  profileSummary?: string;
};

// ── Layer 1: 角色定义 ──
const LAYER1_ROLE = `你是 AIASK 智能股票分析助手。你可以调用工具获取实时行情、K线、财务数据、技术指标等信息来回答用户的股票相关问题。

回答规则：
1. 先调用工具获取相关数据，再基于数据给出分析
2. 使用中文回答
3. 数据来源于 AKShare，可能存在延迟
4. 在分析结尾加上风险提示：本分析仅供参考，不构成投资建议

如果用户问的不是股票相关问题，礼貌地引导回股票分析话题。`;

// ── Layer 2: 情绪感知协议 v2（MIND-SAFE） ──
const LAYER2_EMOTION = `## 情绪感知协议 v2

在每次用户交互中，你必须执行以下结构化评估：

### 2.1 情绪量化
- 情绪极性 polarity: -1.0（极度恐惧）~ +1.0（极度贪婪）
- 情绪强度 intensity: 0（无情绪）~ 1.0（极端情绪）
- 风险厌恶系数 λ = 2.5 + 2.5 × polarity × intensity

### 2.2 认知偏差检测
每轮对话检测以下偏差，命中时在回复中温和提醒：
- anchoring（锚定效应）：用户执着于某个买入价/目标价
- confirmation（确认偏差）：用户只关注支持自己观点的信息
- loss_aversion（损失厌恶）：用户对亏损的反应远超对等额盈利的反应
- herding（羊群效应）：用户因"别人都在买"而跟风

### 2.3 画像更新
每轮对话结束后，你必须调用 update_user_profile 工具，传入你评估的：
- neuroticism: 0~1（神经质程度，焦虑/恐慌越高越大）
- openness: 0~1（开放性，愿意接受新策略/新观点越高越大）
- herd_tendency: 0~1（从众倾向）
- greed_fear_axis: -1~1（贪婪恐惧轴，恐惧为负，贪婪为正）

### 2.4 风险参数传递
当调用 optimize_portfolio 等涉及风险参数的工具时，将计算的 λ 值传入 risk_aversion 参数。
向用户简要解释你的情绪判断和对应的风险调整逻辑，保持透明。`;

// ── Layer 3: 安全约束与合规红线 ──
const LAYER3_SAFETY = `## 安全约束与合规红线

### 3.1 基础约束
1. 永远不得给出"保证收益"的承诺
2. 当检测到用户试图全仓单一标的时，必须发出集中度风险警告
3. 对于高风险操作建议（如加杠杆、追涨停），必须附带明确的风险提示

### 3.2 KYC 等级限制
根据用户 KYC 等级限制推荐范围：
- C1: 仅推荐低风险策略（max_drawdown < 5%）
- C2: 可推荐中低风险（max_drawdown < 10%）
- C3: 可推荐中等风险（max_drawdown < 20%）
- C4: 可推荐中高风险（max_drawdown < 35%）
- C5: 无限制
如果用户 KYC 等级不足以匹配其请求的风险水平，需要提醒并建议降低风险。

### 3.3 认知偏差提醒
当检测到认知偏差时，在回复中以温和方式提醒用户，不要直接否定用户观点。

### 3.4 推荐审计
当你推荐具体策略或股票时，必须调用 log_recommendation_audit 工具记录推荐审计日志。`;

export function buildSystemPrompt(userContext?: UserContextForPrompt): string {
  const layers = [LAYER1_ROLE, LAYER2_EMOTION, LAYER3_SAFETY];

  // ── Layer 4: 动态用户上下文（运行时注入） ──
  if (userContext) {
    const ctxLines = ['## 用户上下文（动态注入）'];
    if (userContext.kycLevel) {
      ctxLines.push(`- KYC 等级：${userContext.kycLevel}（请严格遵守对应等级的推荐限制）`);
    }
    if (userContext.riskLevel) {
      ctxLines.push(`- 用户风险等级：${userContext.riskLevel}（请据此调整推荐策略的风险水平）`);
    }
    if (userContext.profileSummary) {
      ctxLines.push(`- 投资者画像摘要：${userContext.profileSummary}`);
    }
    if (userContext.recentEmotions?.length) {
      ctxLines.push(`- 近期情绪标签：${userContext.recentEmotions.join('、')}（请关注用户情绪变化趋势）`);
    }
    layers.push(ctxLines.join('\n'));
  }

  return layers.join('\n\n');
}

export const CHAT_TOOLS: OpenAI.ChatCompletionTool[] = [
  // ═══════════════════════════════════════════════════════════
  //  行情 & 市场数据
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_realtime_quote',
      description: '获取股票实时行情报价（价格、涨跌幅、成交量等）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码，如 600519' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_batch_quotes',
      description: '批量获取多只股票实时行情',
      parameters: { type: 'object', properties: { stock_codes: { type: 'array', items: { type: 'string' }, description: '股票代码列表' } }, required: ['stock_codes'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_kline_data',
      description: '获取股票K线数据（日线/周线/月线）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, period: { type: 'string', enum: ['daily', 'weekly', 'monthly'], description: '周期' }, limit: { type: 'number', description: '数据条数，默认100' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_minute_kline',
      description: '获取股票分钟级K线（1分钟/5分钟/15分钟/30分钟/60分钟）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' }, period: { type: 'string', enum: ['1', '5', '15', '30', '60'], description: '分钟周期' }, limit: { type: 'number', description: '数据条数' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_index_quote',
      description: '获取指数实时行情（上证指数、深证成指、创业板指等）',
      parameters: { type: 'object', properties: { index_code: { type: 'string', description: '指数代码，如 000001（上证指数）、399001（深证成指）' } }, required: ['index_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_order_book',
      description: '获取股票实时五档盘口数据',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_trade_details',
      description: '获取股票成交明细（逐笔成交）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_limit_up_stocks',
      description: '获取当日涨停板股票列表',
      parameters: { type: 'object', properties: { date: { type: 'string', description: '日期 YYYY-MM-DD，默认今天' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_list',
      description: '获取A股全部股票列表',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_market_blocks',
      description: '获取板块列表（行业板块/概念板块/地域板块）',
      parameters: { type: 'object', properties: { block_type: { type: 'string', enum: ['industry', 'concept', 'area'], description: '板块类型' } }, required: ['block_type'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_block_stocks',
      description: '获取指定板块的成分股',
      parameters: { type: 'object', properties: { block_code: { type: 'string', description: '板块代码（从 get_market_blocks 获取）' } }, required: ['block_code'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  基本面 & 财务
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_stock_info',
      description: '获取股票基本信息（公司名称、行业、上市日期等）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_financials',
      description: '获取股票财务数据（ROE、净利润、营收、资产负债率）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_capital',
      description: '获取股票股本信息（总股本、流通股本等）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  估值
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_valuation_metrics',
      description: '获取股票估值指标（PE、PB、PS、总市值）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_historical_valuation',
      description: '获取股票历史估值分位数（PE/PB百分位）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, years: { type: 'number', description: '回溯年数，默认5' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'dcf_valuation',
      description: 'DCF现金流折现估值模型',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, growth_rate: { type: 'number', description: '增长率（如0.08表示8%）' }, discount_rate: { type: 'number', description: '折现率/WACC（如0.1表示10%）' }, terminal_growth_rate: { type: 'number', description: '永续增长率（如0.03），须小于discount_rate' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'ddm_valuation',
      description: 'DDM股利贴现模型估值',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, required_return: { type: 'number', description: '要求回报率' }, growth_rate: { type: 'number', description: '股利增长率' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'relative_valuation',
      description: '相对估值法（行业可比公司PE/PB/PS对标）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'scenario_dcf_valuation',
      description: '情景分析DCF估值（乐观/中性/悲观三种场景）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  决策分析
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'should_i_buy',
      description: '智能分析某只股票是否值得买入',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'should_i_sell',
      description: '智能分析某只股票是否应该卖出（需要买入价）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          buy_price: { type: 'number', description: '买入价格（必填）' },
          holding_days: { type: 'number', description: '持有天数，默认0' },
        },
        required: ['code', 'buy_price'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_investment_analysis',
      description: '获取投资分析综合报告',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'smart_stock_diagnosis',
      description: '对股票进行综合诊断分析（技术面+基本面+资金面）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  技术分析
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'calculate_technical_indicators',
      description: '计算技术指标（MA、RSI、MACD、KDJ、BOLL等）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, indicators: { type: 'array', items: { type: 'string' }, description: '指标列表，如 ["MA","RSI","MACD"]' } }, required: ['code', 'indicators'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'check_candlestick_patterns',
      description: '检测K线形态（锤子线、吞没形态、十字星等）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_available_patterns',
      description: '获取支持的K线形态列表',
      parameters: { type: 'object', properties: {} },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  搜索 & 语义
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'search_stocks',
      description: '搜索股票（按关键词搜索股票名称或代码）',
      parameters: { type: 'object', properties: { keyword: { type: 'string', description: '搜索关键词' } }, required: ['keyword'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'parse_selection_query',
      description: '自然语言选股解析（如"市盈率低于20的银行股"）',
      parameters: { type: 'object', properties: { query: { type: 'string', description: '自然语言选股条件描述' } }, required: ['query'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_industry_chain',
      description: '获取产业链信息',
      parameters: { type: 'object', properties: { keyword: { type: 'string', description: '产业链关键词' } }, required: ['keyword'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'generate_daily_report',
      description: '生成每日市场综合报告',
      parameters: { type: 'object', properties: {} },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  资金流
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_stock_fund_flow',
      description: '获取个股资金流向数据',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund',
      description: '获取北向资金整体流入/流出数据',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund_holding',
      description: '获取北向资金持仓数据',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund_top',
      description: '获取北向资金成交净买入TOP个股',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_sector_fund_flow',
      description: '获取行业板块资金流向',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_concept_fund_flow',
      description: '获取概念板块资金流向',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_margin_data',
      description: '获取融资融券数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码（可选，不传则获取市场总量）' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_margin_ranking',
      description: '获取融资融券标的排行榜',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_block_trades',
      description: '获取大宗交易数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码（可选）' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_dragon_tiger',
      description: '获取龙虎榜数据',
      parameters: { type: 'object', properties: { date: { type: 'string', description: '日期，如 2024-01-15，默认最新' } } },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  新闻 & 研报
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_stock_news',
      description: '获取个股相关新闻',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, limit: { type: 'number', description: '新闻条数，默认10' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_market_news',
      description: '获取市场综合新闻',
      parameters: { type: 'object', properties: { limit: { type: 'number', description: '新闻条数，默认20' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_notices',
      description: '获取个股公告',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' }, start_date: { type: 'string', description: '起始日期 YYYY-MM-DD' }, end_date: { type: 'string', description: '结束日期 YYYY-MM-DD' } }, required: ['start_date', 'end_date'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_research',
      description: '获取个股研究报告',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_research',
      description: '搜索研报（按关键词）',
      parameters: { type: 'object', properties: { keyword: { type: 'string', description: '搜索关键词' } }, required: ['keyword'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_analyst_ranking',
      description: '获取分析师排名',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_profit_forecast',
      description: '获取股票盈利预测数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  情绪 & 画像
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'analyze_stock_sentiment',
      description: '分析个股市场情绪',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'calculate_fear_greed_index',
      description: '计算市场恐贪指数',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_market_sentiment_context',
      description: '获取市场情绪全景（恐贪指数+涨跌比+板块热度）',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_text_signals',
      description: '获取个股文本信号（舆情分析）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'update_user_profile',
      description: '更新用户投资者画像（每轮对话后必须调用）',
      parameters: {
        type: 'object',
        properties: {
          user_id: { type: 'string', description: '用户ID，默认 default' },
          neuroticism: { type: 'number', description: '神经质程度 0~1' },
          openness: { type: 'number', description: '开放性 0~1' },
          herd_tendency: { type: 'number', description: '从众倾向 0~1' },
          greed_fear_axis: { type: 'number', description: '贪婪恐惧轴 -1~1' },
          confidence: { type: 'number', description: '置信度 0~1' },
        },
        required: ['neuroticism', 'openness', 'herd_tendency', 'greed_fear_axis'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_user_profile',
      description: '获取用户投资者画像（查看历史画像数据）',
      parameters: { type: 'object', properties: { user_id: { type: 'string', description: '用户ID，默认 default' } } },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  宏观经济
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_macro_indicator',
      description: '获取宏观经济指标数据（GDP、CPI、PMI等）',
      parameters: { type: 'object', properties: { indicator: { type: 'string', description: '指标名称，如 gdp、cpi、pmi' } }, required: ['indicator'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  期权
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_option_chain',
      description: '获取期权链数据',
      parameters: { type: 'object', properties: { underlying: { type: 'string', description: '标的代码，如 510300（300ETF）' } }, required: ['underlying'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  组合 & 风险
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'optimize_portfolio',
      description: '组合优化（基于风险厌恶系数和持仓标的）',
      parameters: {
        type: 'object',
        properties: {
          stocks: { type: 'array', items: { type: 'string' }, description: '股票代码列表' },
          risk_aversion: { type: 'number', description: '风险厌恶系数 λ' },
          method: { type: 'string', description: '优化方法：mean_variance/equal_weight/risk_parity/black_litterman' },
        },
        required: ['stocks'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'analyze_portfolio_risk',
      description: '分析组合风险（VaR、波动率、最大回撤等）',
      parameters: {
        type: 'object',
        properties: {
          holdings: { type: 'array', items: { type: 'object', properties: { code: { type: 'string' }, weight: { type: 'number' } } }, description: '持仓列表，每项含 code 和 weight' },
        },
        required: ['holdings'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'stress_test_portfolio',
      description: '组合压力测试（模拟极端市场场景的组合表现）',
      parameters: {
        type: 'object',
        properties: {
          holdings: { type: 'array', items: { type: 'object', properties: { code: { type: 'string' }, weight: { type: 'number' } } }, description: '持仓列表，每项含 code 和 weight' },
          scenarios: { type: 'array', items: { type: 'string' }, description: '场景名称列表，可选: market_crash/sector_rotation/interest_rate_hike/black_swan' },
        },
        required: ['holdings'],
      },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  回测
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'run_simple_backtest',
      description: '运行简单策略回测（支持ma_cross/rsi_basic/macd_trend等策略）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          strategy: { type: 'string', description: '策略名：ma_cross, rsi_basic, macd_trend' },
          start_date: { type: 'string', description: '起始日期 YYYY-MM-DD' },
          end_date: { type: 'string', description: '结束日期 YYYY-MM-DD' },
          initial_capital: { type: 'number', description: '初始资金，默认100000' },
        },
        required: ['code', 'strategy'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_batch_backtest',
      description: '批量回测（多只股票 × 多个策略）',
      parameters: {
        type: 'object',
        properties: {
          codes: { type: 'array', items: { type: 'string' }, description: '股票代码列表' },
          strategies: { type: 'array', items: { type: 'string' }, description: '策略名列表' },
          start_date: { type: 'string', description: '起始日期' },
          end_date: { type: 'string', description: '结束日期' },
        },
        required: ['codes', 'strategies'],
      },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  量化因子
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'list_factors',
      description: '列出所有可用量化因子',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'calculate_factor',
      description: '计算单个量化因子值（如 roe_ttm, atr_14, pe_ttm 等）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          factor: { type: 'string', description: '因子名（用 list_factors 查看可用因子）' },
        },
        required: ['code', 'factor'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_factor_profile',
      description: '获取因子画像（单只股票的多维因子雷达图数据）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_conditional_returns',
      description: '按历史条件统计未来收益分布（条件概率分析）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          conditions: {
            type: 'array',
            items: { type: 'object' },
            description: '条件列表，每项为 {field, op, value}，如 [{field:"rsi_14",op:"<",value:30}]',
          },
          forward_days: { type: 'array', items: { type: 'number' }, description: '向前看天数列表，默认[5,10,20]' },
          logic: { type: 'string', enum: ['AND', 'OR'], description: '多条件逻辑，默认AND' },
          lookback_days: { type: 'number', description: '回溯天数，默认250' },
        },
        required: ['code', 'conditions'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'find_similar_patterns',
      description: '查找历史上与当前K线相似的走势模式',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, window: { type: 'number', description: '匹配窗口长度，默认20' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_signal_hit_rate',
      description: '获取技术信号历史命中率',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, signal: { type: 'string', description: '信号名称' } }, required: ['code', 'signal'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  向量搜索
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'search_similar_stocks',
      description: '搜索与指定股票相似的股票（基于量化特征）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, top_k: { type: 'number', description: '返回数量，默认10' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_by_kline',
      description: '根据K线形态搜索相似走势的股票',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, window: { type: 'number', description: 'K线窗口长度' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'semantic_stock_search',
      description: '语义化股票搜索（用自然语言描述想找的股票）',
      parameters: { type: 'object', properties: { query: { type: 'string', description: '自然语言描述，如"高分红低估值的银行股"' } }, required: ['query'] },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  预警
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'create_indicator_alert',
      description: '创建技术指标预警',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          indicator: { type: 'string', description: '指标名称，如 rsi_14, macd' },
          condition: { type: 'string', description: '条件：above/below/cross_up/cross_down' },
          value: { type: 'number', description: '阈值' },
        },
        required: ['code', 'indicator', 'condition', 'value'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'create_combo_alert',
      description: '创建组合预警（多条件组合触发）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          conditions: { type: 'array', items: { type: 'object' }, description: '条件列表' },
          logic: { type: 'string', enum: ['AND', 'OR'], description: '条件逻辑' },
        },
        required: ['code', 'conditions'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'check_all_alerts',
      description: '检查所有预警是否触发',
      parameters: { type: 'object', properties: {} },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  基础数据
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'get_trading_dates',
      description: '获取交易日历（查询某段时间的交易日）',
      parameters: { type: 'object', properties: { start_date: { type: 'string', description: '起始日期' }, end_date: { type: 'string', description: '结束日期' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_ipo_info',
      description: '获取新股/IPO信息',
      parameters: { type: 'object', properties: {} },
    },
  },
  // ═══════════════════════════════════════════════════════════
  //  审计 & 合规
  // ═══════════════════════════════════════════════════════════
  {
    type: 'function',
    function: {
      name: 'log_recommendation_audit',
      description: '记录推荐审计日志（推荐策略/股票时必须调用）',
      parameters: {
        type: 'object',
        properties: {
          user_id: { type: 'string', description: '用户ID' },
          strategy_id: { type: 'string', description: '策略ID' },
          stock_code: { type: 'string', description: '股票代码' },
          action: { type: 'string', description: '推荐动作：buy/sell/hold' },
          emotion_polarity: { type: 'number', description: '情绪极性 -1~1' },
          emotion_intensity: { type: 'number', description: '情绪强度 0~1' },
          cognitive_biases: { type: 'array', items: { type: 'string' }, description: '检测到的认知偏差' },
          risk_aversion: { type: 'number', description: '风险厌恶系数' },
          kyc_level: { type: 'string', description: 'KYC等级' },
          reasoning_chain: { type: 'string', description: '推理链路说明' },
        },
        required: ['user_id', 'action', 'reasoning_chain'],
      },
    },
  },
];
