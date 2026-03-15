import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { PreferencesService } from '../auth/preferences.service';
import { UserContextService } from './user-context.service';
import { CHAT_TOOLS, buildSystemPrompt } from './chat.tools';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'error'; message: string }
  | { type: 'done' };

type ChatMessage = { role: 'user' | 'assistant' | 'system'; content: string };
type ToolCallRecord = { name: string; args: Record<string, unknown>; result: unknown };

const MAX_TOOL_ROUNDS = 10;

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly preferencesService: PreferencesService,
    private readonly userContextService: UserContextService,
  ) {}

  async *streamChat(userId: string, messages: ChatMessage[]): AsyncGenerator<ChatEvent> {
    const config = await this.preferencesService.getLlmConfig(userId);
    if (!config) throw new BadRequestException('请先在设置中配置 LLM API Key');

    const openai = new OpenAI({ apiKey: config.apiKey, baseURL: config.baseUrl });

    const userContext = await this.userContextService.getUserContext(userId);
    const systemPrompt = buildSystemPrompt(userContext);

    const conversationMessages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
      { role: 'system', content: systemPrompt },
      ...messages.map((m) => ({ role: m.role, content: m.content }) as OpenAI.Chat.Completions.ChatCompletionMessageParam),
    ];
    const calledTools = new Set<string>();
    let lastProfileArgs: Record<string, unknown> | null = null;

    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      const stream = await openai.chat.completions.create({
        model: config.model,
        messages: conversationMessages,
        tools: CHAT_TOOLS,
        stream: true,
      });

      let assistantContent = '';
      const toolCallFragments: Map<number, { id: string; name: string; arguments: string }> = new Map();

      for await (const chunk of stream) {
        const choice = chunk.choices[0];
        if (!choice) continue;

        const delta = choice.delta;
        if (delta?.content) {
          assistantContent += delta.content;
          yield { type: 'delta', content: delta.content };
        }

        if (delta?.tool_calls) {
          for (const tc of delta.tool_calls) {
            const idx = tc.index;
            if (!toolCallFragments.has(idx)) {
              toolCallFragments.set(idx, { id: tc.id ?? '', name: tc.function?.name ?? '', arguments: '' });
            }
            const frag = toolCallFragments.get(idx)!;
            if (tc.id) frag.id = tc.id;
            if (tc.function?.name) frag.name = tc.function.name;
            if (tc.function?.arguments) frag.arguments += tc.function.arguments;
          }
        }
      }

      if (toolCallFragments.size === 0) {
        const enforcedCalls = await this.enforceRequiredToolCalls(
          userId,
          userContext,
          messages,
          assistantContent,
          calledTools,
          lastProfileArgs,
        );
        for (const enforced of enforcedCalls) {
          yield { type: 'tool_call', name: enforced.name, args: enforced.args };
          yield { type: 'tool_result', name: enforced.name, result: enforced.result };
        }
        yield { type: 'done' };
        return;
      }

      // Build assistant message with tool_calls
      const toolCalls: Array<{ id: string; type: 'function'; function: { name: string; arguments: string } }> = [];
      for (const [, frag] of toolCallFragments) {
        toolCalls.push({
          id: frag.id,
          type: 'function',
          function: { name: frag.name, arguments: frag.arguments },
        });
      }

      conversationMessages.push({
        role: 'assistant',
        content: assistantContent || null,
        tool_calls: toolCalls,
      } as OpenAI.Chat.Completions.ChatCompletionMessageParam);

      // Execute each tool call via MCP
      for (const tc of toolCalls) {
        let args: Record<string, unknown> = {};
        try { args = JSON.parse(tc.function.arguments); } catch { /* empty */ }
        args = this.bindComplianceToolArgs(userId, tc.function.name, args);
        yield { type: 'tool_call', name: tc.function.name, args };

        let result: unknown;
        try {
          result = await this.mcp.callTool(tc.function.name, args);
        } catch (err) {
          result = { error: err instanceof Error ? err.message : String(err) };
        }

        calledTools.add(tc.function.name);
        if (tc.function.name === 'update_user_profile') {
          lastProfileArgs = args;
          this.recordEmotionFromProfile(userId, args);
        }

        yield { type: 'tool_result', name: tc.function.name, result };

        conversationMessages.push({
          role: 'tool',
          tool_call_id: tc.id,
          content: typeof result === 'string' ? result : JSON.stringify(result),
        } as OpenAI.Chat.Completions.ChatCompletionMessageParam);
      }
      // Loop back for LLM to process tool results
    }

    yield { type: 'error', message: '工具调用轮次超限' };
    yield { type: 'done' };
  }

  private async enforceRequiredToolCalls(
    userId: string,
    userContext: Awaited<ReturnType<UserContextService['getUserContext']>>,
    messages: ChatMessage[],
    assistantContent: string,
    calledTools: Set<string>,
    lastProfileArgs: Record<string, unknown> | null,
  ): Promise<ToolCallRecord[]> {
    const enforced: ToolCallRecord[] = [];
    let profileArgs = lastProfileArgs;

    if (!calledTools.has('update_user_profile')) {
      profileArgs = this.buildFallbackUserProfileArgs(userId, userContext, messages);
      const result = await this.callToolSafely('update_user_profile', profileArgs);
      this.logger.warn(`chat compliance enforced update_user_profile for user=${userId}`);
      this.recordEmotionFromProfile(userId, profileArgs);
      calledTools.add('update_user_profile');
      enforced.push({ name: 'update_user_profile', args: profileArgs, result });
    }

    if (this.shouldAuditRecommendation(assistantContent) && !calledTools.has('log_recommendation_audit')) {
      const auditArgs = this.buildFallbackRecommendationAuditArgs(
        userId,
        userContext,
        messages,
        assistantContent,
        profileArgs,
      );
      const result = await this.callToolSafely('log_recommendation_audit', auditArgs);
      this.logger.warn(`chat compliance enforced log_recommendation_audit for user=${userId}`);
      calledTools.add('log_recommendation_audit');
      enforced.push({ name: 'log_recommendation_audit', args: auditArgs, result });
    }

    return enforced;
  }

  private async callToolSafely(name: string, args: Record<string, unknown>): Promise<unknown> {
    try {
      return await this.mcp.callTool(name, args);
    } catch (err) {
      return { error: err instanceof Error ? err.message : String(err) };
    }
  }

  private bindComplianceToolArgs(
    userId: string,
    toolName: string,
    args: Record<string, unknown>,
  ): Record<string, unknown> {
    if (toolName === 'update_user_profile' || toolName === 'get_user_profile' || toolName === 'log_recommendation_audit') {
      return {
        ...args,
        user_id: userId,
      };
    }
    return args;
  }

  private recordEmotionFromProfile(userId: string, args: Record<string, unknown>) {
    try {
      const gfa = Number(args.greed_fear_axis ?? 0);
      let label: string;
      if (gfa < -0.6) label = '极度焦虑';
      else if (gfa < -0.2) label = '偏焦虑';
      else if (gfa < 0.2) label = '理性';
      else if (gfa < 0.6) label = '偏乐观';
      else label = '极度贪婪';
      this.userContextService.recordEmotion(userId, label);
    } catch {
      /* best-effort */
    }
  }

  private buildFallbackUserProfileArgs(
    userId: string,
    userContext: Awaited<ReturnType<UserContextService['getUserContext']>>,
    messages: ChatMessage[],
  ): Record<string, unknown> {
    const userText = messages
      .filter((message) => message.role === 'user')
      .map((message) => message.content)
      .join('\n');

    let neuroticism = 0.5;
    let openness = 0.5;
    let herdTendency = 0.4;
    let greedFearAxis = 0.0;
    let confidence = 0.35;

    if (/(恐慌|害怕|担心|亏损|暴跌|套牢|回撤)/.test(userText)) {
      neuroticism = 0.72;
      greedFearAxis = -0.45;
      confidence = 0.45;
    }
    if (/(梭哈|满仓|追涨|翻倍|暴赚|起飞)/.test(userText)) {
      greedFearAxis = 0.55;
      neuroticism = Math.max(neuroticism, 0.58);
      confidence = 0.4;
    }
    if (/(别人都在买|大家都在买|跟风|抄作业|群里都说)/.test(userText)) {
      herdTendency = 0.75;
    }
    if (/(还有什么思路|新策略|别的策略|可以试试)/.test(userText)) {
      openness = 0.68;
    }
    if (userContext.recentEmotions?.includes('极度焦虑')) {
      neuroticism = Math.max(neuroticism, 0.8);
      greedFearAxis = Math.min(greedFearAxis, -0.6);
    }
    if (userContext.recentEmotions?.includes('极度贪婪')) {
      greedFearAxis = Math.max(greedFearAxis, 0.6);
    }

    return {
      user_id: userId,
      neuroticism: Number(neuroticism.toFixed(4)),
      openness: Number(openness.toFixed(4)),
      herd_tendency: Number(herdTendency.toFixed(4)),
      greed_fear_axis: Number(greedFearAxis.toFixed(4)),
      confidence: Number(confidence.toFixed(4)),
    };
  }

  private shouldAuditRecommendation(assistantContent: string): boolean {
    if (!assistantContent.trim()) return false;
    const hasActionVerb = /(建议|推荐|买入|卖出|持有|加仓|减仓|关注)/.test(assistantContent);
    if (!hasActionVerb) return false;

    return /(?:\b\d{6}\b|strat_[a-zA-Z0-9_]+)/.test(assistantContent) || /策略/.test(assistantContent);
  }

  private buildFallbackRecommendationAuditArgs(
    userId: string,
    userContext: Awaited<ReturnType<UserContextService['getUserContext']>>,
    messages: ChatMessage[],
    assistantContent: string,
    profileArgs: Record<string, unknown> | null,
  ): Record<string, unknown> {
    const stockCodeMatch = assistantContent.match(/\b(\d{6})\b/);
    const strategyIdMatch = assistantContent.match(/\b(strat_[a-zA-Z0-9_]+)\b/);
    const action = this.extractRecommendationAction(assistantContent);
    const greedFearAxis = Number(profileArgs?.greed_fear_axis ?? 0);
    const neuroticism = Number(profileArgs?.neuroticism ?? 0.5);
    const intensity = Math.min(1, Math.max(Math.abs(greedFearAxis), neuroticism));

    return {
      user_id: userId,
      strategy_id: strategyIdMatch?.[1] ?? '',
      stock_code: stockCodeMatch?.[1] ?? '',
      action,
      emotion_polarity: Number(greedFearAxis.toFixed(4)),
      emotion_intensity: Number(intensity.toFixed(4)),
      cognitive_biases: this.detectCognitiveBiases(messages).join(','),
      risk_aversion: Number((2.5 + 2.5 * greedFearAxis * intensity).toFixed(4)),
      kyc_level: userContext.kycLevel ?? '',
      reasoning_chain: assistantContent.slice(0, 1500),
    };
  }

  private extractRecommendationAction(assistantContent: string): 'buy' | 'sell' | 'hold' {
    if (/(卖出|减仓|止盈|止损|离场)/.test(assistantContent)) return 'sell';
    if (/(持有|观望|等待|继续持仓)/.test(assistantContent)) return 'hold';
    return 'buy';
  }

  private detectCognitiveBiases(messages: ChatMessage[]): string[] {
    const userText = messages
      .filter((message) => message.role === 'user')
      .map((message) => message.content)
      .join('\n');

    const biases: string[] = [];
    if (/(成本|买入价|回本价|目标价)/.test(userText)) biases.push('anchoring');
    if (/(只想找|证明|肯定会涨|已经说明)/.test(userText)) biases.push('confirmation');
    if (/(亏不起|不能亏|回本再说|套牢)/.test(userText)) biases.push('loss_aversion');
    if (/(别人都在买|大家都在买|跟风|抄作业|群里都说)/.test(userText)) biases.push('herding');
    return biases;
  }
}
