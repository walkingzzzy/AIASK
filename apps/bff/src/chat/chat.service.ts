import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { PreferencesService } from '../auth/preferences.service';
import { UserContextService } from './user-context.service';
import { CHAT_TOOLS, buildSystemPrompt } from './chat.tools';
import { BehaviorService } from '../behavior/behavior.service';
import { LOCAL_CONTEXT_TOOL_NAMES, LOCAL_CONTEXT_TOOLS } from './tools/local-context';
import { sanitizeReasoningDelta } from './chat-safety';
import {
  addToolTraceItem,
  cloneToolTrace,
  createChatToolTrace,
  finalizeToolTrace,
  finishToolTraceItem,
  recordCompletedToolTraceItem,
  type ChatToolTraceDto,
  type ChatToolTraceItemDto,
  type ChatToolTraceItemKind,
} from './tool-trace';
import type {
  ChatEvent,
  ChatMessageInput,
  ChatPageContext,
  ChatRequestPayload,
  ClientActionDescriptor,
} from './chat.protocol';

type ToolCallRecord = {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  startedAt: Date;
  finishedAt: Date;
};
type ClientActionExecutionIntent = {
  latestUserMessage: string;
  explicitActionExecution: boolean;
  explicitPersonalStrategyWrite: boolean;
  explicitSuggestionOnly: boolean;
  hasWritablePersonalStrategyActions: boolean;
};

const MAX_TOOL_ROUNDS = 10;
const CLIENT_ACTION_TOOL_NAME = 'request_client_action';
const FIRST_RESPONSE_TIMEOUT_MS = 45_000;
const ROUND_TIMEOUT_MS = 75_000;
const TOOL_HEARTBEAT_INTERVAL_MS = 10_000;

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly preferencesService: PreferencesService,
    private readonly userContextService: UserContextService,
    private readonly behaviorService: BehaviorService,
  ) {}

  async *streamChat(userId: string, payload: ChatRequestPayload): AsyncGenerator<ChatEvent> {
    const messages = payload.messages ?? [];
    const pageContext = payload.pageContext ?? null;
    const availableActions = payload.availableActions ?? [];
    const clientActionIntent = this.analyzeClientActionIntent(messages, pageContext, availableActions);
    const toolTrace = createChatToolTrace({
      mode: payload.mode,
      pageKey: pageContext?.pageKey,
      objectType: pageContext?.objectType,
      objectId: pageContext?.objectId,
      stockCode: pageContext?.selectedCode ?? pageContext?.stockCode,
    });

    const config = await this.preferencesService.getLlmConfig(userId);
    if (!config) throw new BadRequestException('请先在设置中配置 LLM API Key');

    const openai = new OpenAI({ apiKey: config.apiKey, baseURL: config.baseUrl });
    const userContext = await this.userContextService.getUserContext(userId);
    const behaviorSummary = await this.behaviorService.getRecentSummary(userId, { limit: 20, days: 30 });
    const systemPrompt = buildSystemPrompt({
      ...userContext,
      behaviorSummary: behaviorSummary?.summary,
    });
    const clientActionTool = this.buildClientActionTool(availableActions);
    const tools = clientActionTool
      ? [...CHAT_TOOLS, ...LOCAL_CONTEXT_TOOLS, clientActionTool]
      : [...CHAT_TOOLS, ...LOCAL_CONTEXT_TOOLS];

    const conversationMessages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
      { role: 'system', content: systemPrompt },
      ...this.buildCopilotContextMessages(payload.mode, pageContext, availableActions, clientActionIntent),
      ...messages.map((message) => ({
        role: message.role,
        content: message.content,
      }) as OpenAI.Chat.Completions.ChatCompletionMessageParam),
    ];

    const calledTools = new Set<string>();
    let lastProfileArgs: Record<string, unknown> | null = null;

    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      const timeoutGuard = this.createRoundTimeoutGuard();
      let stream: Awaited<ReturnType<OpenAI['chat']['completions']['create']>>;
      try {
        stream = await openai.chat.completions.create({
          model: config.model,
          messages: conversationMessages,
          tools,
          stream: true,
        }, {
          signal: timeoutGuard.controller.signal,
        });
      } catch (error) {
        timeoutGuard.dispose();
        if (this.isAbortLikeError(error)) {
          const fallback = this.buildToolOnlyFallbackAnswer(toolTrace, pageContext);
          finalizeToolTrace(toolTrace, '', {
            hasPageContextEvidence: this.hasPageContextEvidence(pageContext),
          });
          yield this.buildToolTraceEvent(toolTrace);
          if (fallback.trim()) {
            yield { type: 'final_fallback', content: fallback };
          } else {
            yield { type: 'error', message: timeoutGuard.message };
          }
          yield { type: 'done' };
          return;
        }
        const fallback = this.buildToolOnlyFallbackAnswer(toolTrace, pageContext);
        finalizeToolTrace(toolTrace, fallback, {
          hasPageContextEvidence: this.hasPageContextEvidence(pageContext),
        });
        if (fallback.trim()) {
          yield { type: 'final_fallback', content: fallback };
        }
        yield this.buildToolTraceEvent(toolTrace);
        yield { type: 'error', message: this.formatUpstreamError(error) };
        yield { type: 'done' };
        return;
      }

      let assistantContent = '';
      let reasoningReplacementInserted = false;
      const toolCallFragments: Map<number, { id: string; name: string; arguments: string }> = new Map();
      try {
        const iterator = stream[Symbol.asyncIterator]();
        try {
          while (true) {
            const next = yield* this.nextWithHeartbeat(iterator, 'llm:stream');
            if (next.done) break;
            const chunk = next.value;
          const choice = chunk.choices[0];
          if (!choice) continue;

          const delta = choice.delta;
          if (
            !timeoutGuard.firstResponseSeen
            && (Boolean(delta?.content) || Boolean(delta?.tool_calls?.length) || Boolean(choice.finish_reason))
          ) {
            timeoutGuard.markFirstResponse();
          }

          if (delta?.content) {
            const sanitized = sanitizeReasoningDelta(delta.content, reasoningReplacementInserted);
            reasoningReplacementInserted = sanitized.replaced;
            assistantContent += sanitized.content;
            if (sanitized.content) {
              yield { type: 'delta', content: sanitized.content };
            }
          }

          if (delta?.tool_calls) {
            for (const toolCall of delta.tool_calls) {
              const index = toolCall.index;
              if (!toolCallFragments.has(index)) {
                toolCallFragments.set(index, {
                  id: toolCall.id ?? '',
                  name: toolCall.function?.name ?? '',
                  arguments: '',
                });
              }
              const fragment = toolCallFragments.get(index)!;
              if (toolCall.id) fragment.id = toolCall.id;
              if (toolCall.function?.name) fragment.name = toolCall.function.name;
              if (toolCall.function?.arguments) fragment.arguments += toolCall.function.arguments;
            }
          }
        }
        } finally {
          if (typeof iterator.return === 'function') {
            await iterator.return().catch(() => undefined);
          }
        }
      } catch (error) {
        timeoutGuard.dispose();
        if (this.isAbortLikeError(error)) {
          const fallback = assistantContent.trim()
            ? ''
            : this.buildToolOnlyFallbackAnswer(toolTrace, pageContext);
          finalizeToolTrace(toolTrace, assistantContent, {
            hasPageContextEvidence: this.hasPageContextEvidence(pageContext),
          });
          yield this.buildToolTraceEvent(toolTrace);
          if (fallback.trim()) {
            yield { type: 'final_fallback', content: fallback };
          } else {
            yield { type: 'error', message: timeoutGuard.message };
          }
          yield { type: 'done' };
          return;
        }
        throw error;
      } finally {
        timeoutGuard.dispose();
      }

      if (toolCallFragments.size === 0) {
        const finalContent = assistantContent.trim()
          ? assistantContent
          : this.buildToolOnlyFallbackAnswer(toolTrace, pageContext);
        if (!assistantContent.trim() && finalContent.trim()) {
          yield { type: 'final_fallback', content: finalContent };
        }
        const enforcedCalls = await this.enforceRequiredToolCalls(
          userId,
          userContext,
          messages,
          finalContent,
          calledTools,
          lastProfileArgs,
        );
        for (const enforced of enforcedCalls) {
          recordCompletedToolTraceItem(
            toolTrace,
            {
              kind: this.isComplianceTool(enforced.name) ? 'compliance' : 'mcp',
              toolName: enforced.name,
              args: enforced.args,
              startedAt: enforced.startedAt,
            },
            enforced.result,
            enforced.finishedAt,
          );
        }
        finalizeToolTrace(toolTrace, finalContent, {
          hasPageContextEvidence: this.hasPageContextEvidence(pageContext),
        });
        yield this.buildToolTraceEvent(toolTrace);
        yield { type: 'done' };
        return;
      }

      const toolCalls: Array<{ id: string; type: 'function'; function: { name: string; arguments: string } }> = [];
      for (const [, fragment] of toolCallFragments) {
        toolCalls.push({
          id: fragment.id,
          type: 'function',
          function: {
            name: fragment.name,
            arguments: fragment.arguments,
          },
        });
      }

      conversationMessages.push({
        role: 'assistant',
        content: assistantContent || null,
        tool_calls: toolCalls,
      } as OpenAI.Chat.Completions.ChatCompletionMessageParam);

      for (const toolCall of toolCalls) {
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(toolCall.function.arguments);
        } catch {
          args = {};
        }

        if (toolCall.function.name === CLIENT_ACTION_TOOL_NAME) {
          const traceItem = this.startTraceItem(toolTrace, 'client_action', toolCall.function.name, args);
          yield this.buildToolTraceEvent(toolTrace);
          const actionEvent = this.buildClientActionEvent(args, availableActions, clientActionIntent);
          const result = actionEvent
            ? {
                scheduled: true,
                actionId: actionEvent.actionId,
                autoExecute: actionEvent.autoExecute === true,
                status: actionEvent.autoExecute === true ? 'auto_executed' : 'pending',
              }
            : { scheduled: false, error: 'invalid action request' };
          finishToolTraceItem(toolTrace, traceItem.id, result);
          yield this.buildToolTraceEvent(toolTrace);

          if (actionEvent) {
            yield actionEvent;
          }

          conversationMessages.push({
            role: 'tool',
            tool_call_id: toolCall.id,
            content: this.buildToolResponseContent(toolCall.function.name, traceItem, result),
          } as OpenAI.Chat.Completions.ChatCompletionMessageParam);
          continue;
        }

        if (this.isLocalToolName(toolCall.function.name)) {
          const traceItem = this.startTraceItem(toolTrace, 'local_context', toolCall.function.name, args);
          yield this.buildToolTraceEvent(toolTrace);
          const result = await this.callLocalTool(userId, toolCall.function.name, args);
          finishToolTraceItem(toolTrace, traceItem.id, result);
          yield this.buildToolTraceEvent(toolTrace);
          conversationMessages.push({
            role: 'tool',
            tool_call_id: toolCall.id,
            content: this.buildToolResponseContent(toolCall.function.name, traceItem, result),
          } as OpenAI.Chat.Completions.ChatCompletionMessageParam);
          continue;
        }

        args = this.bindComplianceToolArgs(userId, toolCall.function.name, args);
        const traceItem = this.startTraceItem(
          toolTrace,
          this.isComplianceTool(toolCall.function.name) ? 'compliance' : 'mcp',
          toolCall.function.name,
          args,
        );
        yield this.buildToolTraceEvent(toolTrace);

        let result: unknown;
        try {
          result = yield* this.awaitWithHeartbeat(
            this.mcp.callTool(toolCall.function.name, args),
            `mcp:${toolCall.function.name}`,
          );
        } catch (error) {
          result = { error: error instanceof Error ? error.message : String(error) };
        }

        calledTools.add(toolCall.function.name);
        if (toolCall.function.name === 'update_user_profile') {
          lastProfileArgs = args;
          this.recordEmotionFromProfile(userId, args);
        }

        finishToolTraceItem(toolTrace, traceItem.id, result);
        yield this.buildToolTraceEvent(toolTrace);
        conversationMessages.push({
          role: 'tool',
          tool_call_id: toolCall.id,
          content: this.buildToolResponseContent(toolCall.function.name, traceItem, result),
        } as OpenAI.Chat.Completions.ChatCompletionMessageParam);
      }
    }

    finalizeToolTrace(toolTrace, '', {
      hasPageContextEvidence: this.hasPageContextEvidence(pageContext),
    });
    yield this.buildToolTraceEvent(toolTrace);
    yield { type: 'error', message: '工具调用轮次超限' };
    yield { type: 'done' };
  }

  private async *awaitWithHeartbeat<T>(
    promise: Promise<T>,
    scope: string,
  ): AsyncGenerator<ChatEvent, T, void> {
    const wrapped = promise.then(
      (value) => ({ ok: true as const, value }),
      (reason) => ({ ok: false as const, reason }),
    );

    while (true) {
      const result = await Promise.race([
        wrapped,
        this.sleep(TOOL_HEARTBEAT_INTERVAL_MS).then(() => null),
      ]);
      if (result == null) {
        yield { type: 'heartbeat', at: new Date().toISOString(), scope };
        continue;
      }
      if (!result.ok) {
        throw result.reason;
      }
      return result.value;
    }
  }

  private async *nextWithHeartbeat<T>(
    iterator: AsyncIterator<T>,
    scope: string,
  ): AsyncGenerator<ChatEvent, IteratorResult<T>, void> {
    const next = iterator.next();
    while (true) {
      const result = await Promise.race([
        next,
        this.sleep(TOOL_HEARTBEAT_INTERVAL_MS).then(() => null),
      ]);
      if (result == null) {
        yield { type: 'heartbeat', at: new Date().toISOString(), scope };
        continue;
      }
      return result;
    }
  }

  private sleep(ms: number) {
    return new Promise<void>((resolve) => setTimeout(resolve, ms));
  }

  private buildToolOnlyFallbackAnswer(toolTrace: ChatToolTraceDto, pageContext: ChatPageContext | null) {
    const completed = toolTrace.items.filter((item) => item.status === 'success');
    const failed = toolTrace.items.filter((item) => item.status === 'error');
    if (completed.length === 0 && failed.length === 0) {
      return this.buildPageContextFallbackAnswer(pageContext);
    }

    const scope = pageContext?.title ? `当前页面「${pageContext.title}」` : '当前上下文';
    const successSummary = completed
      .slice(0, 3)
      .map((item) => `[${item.referenceLabel}] ${item.toolName}: ${(item.outputSummary[0] ?? '已返回结果').slice(0, 120)}`)
      .join('\n');
    const failedSummary = failed.length
      ? `\n\n失败项：${failed.slice(0, 3).map((item) => `[${item.referenceLabel}] ${item.toolName}: ${item.errorMessage ?? '调用失败'}`).join('；')}`
      : '';
    return `基于工具结果生成：${scope}本轮已完成 ${completed.length} 项工具调用。由于模型没有返回最终正文，下面先给出可见的工具摘要：\n${successSummary}${failedSummary}\n\n可以根据上方工具轨迹继续追问，或重试生成完整结论。`;
  }

  private buildPageContextFallbackAnswer(pageContext: ChatPageContext | null) {
    if (!this.hasPageContextEvidence(pageContext)) return '';
    const scope = pageContext?.title ? `当前页面「${pageContext.title}」` : '当前页面上下文';
    const summary = pageContext?.summary?.trim();
    const evidence = (pageContext?.evidenceSummary ?? []).map((item) => item.trim()).filter(Boolean).slice(0, 3);
    const risks = (pageContext?.riskNotes ?? []).map((item) => item.trim()).filter(Boolean).slice(0, 3);
    const freshness = pageContext?.dataFreshness?.trim();
    const identity = [
      pageContext?.objectType ? `objectType=${pageContext.objectType}` : '',
      pageContext?.objectId ? `objectId=${pageContext.objectId}` : '',
      pageContext?.strategyId ? `strategyId=${pageContext.strategyId}` : '',
      pageContext?.stockCode ? `stockCode=${pageContext.stockCode}` : '',
      pageContext?.selectedCode && pageContext.selectedCode !== pageContext.stockCode ? `selectedCode=${pageContext.selectedCode}` : '',
      pageContext?.accountId ? `accountId=${pageContext.accountId}` : '',
      pageContext?.workspaceId ? `workspaceId=${pageContext.workspaceId}` : '',
    ].filter(Boolean).join('；');
    const rawSummary = this.buildRawContextSummary(pageContext?.raw);
    const lines = [
      `基于页面上下文生成：${scope}。模型没有返回可见正文，先展示可用上下文摘要。`,
      identity ? `对象：${identity}` : '',
      summary ? `摘要：${summary}` : '',
      evidence.length ? `证据：${evidence.join('；')}` : '',
      risks.length ? `风险关注：${risks.join('；')}` : '',
      rawSummary ? `上下文细节：${rawSummary}` : '',
      freshness ? `数据新鲜度：${freshness}` : '',
      '可以继续追问，或重试生成完整结论。',
    ].filter(Boolean);
    return lines.join('\n');
  }

  private startTraceItem(
    trace: ChatToolTraceDto,
    kind: ChatToolTraceItemKind,
    toolName: string,
    args: Record<string, unknown>,
  ) {
    return addToolTraceItem(trace, {
      kind,
      toolName,
      args,
      startedAt: new Date(),
    });
  }

  private buildToolTraceEvent(trace: ChatToolTraceDto): Extract<ChatEvent, { type: 'tool_trace' }> {
    return { type: 'tool_trace', trace: cloneToolTrace(trace) };
  }

  private buildToolResponseContent(toolName: string, traceItem: ChatToolTraceItemDto, result: unknown) {
    return JSON.stringify({
      tool_trace_reference: traceItem.referenceLabel,
      tool_name: toolName,
      result,
    });
  }

  private hasPageContextEvidence(pageContext: ChatPageContext | null) {
    if (!pageContext) return false;
    return Boolean(
      pageContext.summary?.trim()
      || pageContext.evidenceSummary?.length
      || pageContext.riskNotes?.length
      || pageContext.dataFreshness
      || pageContext.raw,
    );
  }

  private async enforceRequiredToolCalls(
    userId: string,
    userContext: Awaited<ReturnType<UserContextService['getUserContext']>>,
    messages: ChatMessageInput[],
    assistantContent: string,
    calledTools: Set<string>,
    lastProfileArgs: Record<string, unknown> | null,
  ): Promise<ToolCallRecord[]> {
    const enforced: ToolCallRecord[] = [];
    let profileArgs = lastProfileArgs;

    if (!calledTools.has('update_user_profile') && this.shouldUpdateUserProfile(messages, assistantContent)) {
      profileArgs = this.buildFallbackUserProfileArgs(userId, userContext, messages);
      const startedAt = new Date();
      const result = await this.callToolSafely('update_user_profile', profileArgs);
      const finishedAt = new Date();
      this.logger.warn(`chat compliance enforced update_user_profile for user=${userId}`);
      this.recordEmotionFromProfile(userId, profileArgs);
      calledTools.add('update_user_profile');
      enforced.push({ name: 'update_user_profile', args: profileArgs, result, startedAt, finishedAt });
    }

    if (this.shouldAuditRecommendation(assistantContent) && !calledTools.has('log_recommendation_audit')) {
      const auditArgs = this.buildFallbackRecommendationAuditArgs(
        userId,
        userContext,
        messages,
        assistantContent,
        profileArgs,
      );
      const startedAt = new Date();
      const result = await this.callToolSafely('log_recommendation_audit', auditArgs);
      const finishedAt = new Date();
      this.logger.warn(`chat compliance enforced log_recommendation_audit for user=${userId}`);
      calledTools.add('log_recommendation_audit');
      enforced.push({ name: 'log_recommendation_audit', args: auditArgs, result, startedAt, finishedAt });
    }

    return enforced;
  }

  private isComplianceTool(toolName: string) {
    return toolName === 'update_user_profile' || toolName === 'log_recommendation_audit';
  }

  private shouldUpdateUserProfile(messages: ChatMessageInput[], assistantContent: string): boolean {
    const latestUserText = [...messages].reverse().find((message) => message.role === 'user')?.content ?? '';
    if (!latestUserText.trim()) return false;
    if (/(恐慌|害怕|焦虑|担心|亏损|暴跌|套牢|回撤|睡不着|压力|上头|冲动)/.test(latestUserText)) return true;
    if (/(梭哈|满仓|加杠杆|融资|追涨|翻倍|暴赚|起飞|赌一把)/.test(latestUserText)) return true;
    if (/(别人都在买|大家都在买|跟风|抄作业|群里都说)/.test(latestUserText)) return true;
    if (/(风险偏好|风险承受|KYC|画像|投资风格|保守|激进|稳健)/.test(latestUserText)) return true;
    return this.shouldAuditRecommendation(assistantContent) && /(我的|适合我|我应该|帮我选|推荐给我)/.test(latestUserText);
  }

  private async callToolSafely(name: string, args: Record<string, unknown>): Promise<unknown> {
    try {
      return await this.mcp.callTool(name, args);
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error) };
    }
  }

  private bindComplianceToolArgs(
    userId: string,
    toolName: string,
    args: Record<string, unknown>,
  ): Record<string, unknown> {
    if (
      toolName === 'update_user_profile'
      || toolName === 'get_user_profile'
      || toolName === 'log_recommendation_audit'
    ) {
      return {
        ...args,
        user_id: userId,
      };
    }
    return args;
  }

  private recordEmotionFromProfile(userId: string, args: Record<string, unknown>) {
    try {
      const greedFearAxis = Number(args.greed_fear_axis ?? 0);
      let label: string;
      if (greedFearAxis < -0.6) label = '极度焦虑';
      else if (greedFearAxis < -0.2) label = '偏焦虑';
      else if (greedFearAxis < 0.2) label = '理性';
      else if (greedFearAxis < 0.6) label = '偏乐观';
      else label = '极度贪婪';
      this.userContextService.recordEmotion(userId, label);
    } catch {
      // best-effort
    }
  }

  private buildFallbackUserProfileArgs(
    userId: string,
    userContext: Awaited<ReturnType<UserContextService['getUserContext']>>,
    messages: ChatMessageInput[],
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
    messages: ChatMessageInput[],
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

  private detectCognitiveBiases(messages: ChatMessageInput[]): string[] {
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

  private buildCopilotContextMessages(
    mode: ChatRequestPayload['mode'],
    pageContext: ChatPageContext | null,
    availableActions: ClientActionDescriptor[],
    clientActionIntent: ClientActionExecutionIntent,
  ): OpenAI.Chat.Completions.ChatCompletionMessageParam[] {
    if (!pageContext && availableActions.length === 0 && mode !== 'copilot') {
      return [];
    }

    const lines: string[] = [];
    if (mode) {
      lines.push(`当前模式: ${mode}`);
    }
    if (pageContext) {
      lines.push('页面上下文:');
      lines.push(`- 页面: ${pageContext.pageKey} / ${pageContext.title}`);
      lines.push(`- 摘要: ${pageContext.summary}`);
      if (pageContext.primaryGoal) lines.push(`- 主要目标: ${pageContext.primaryGoal}`);
      if (pageContext.requiredInputs?.length) lines.push(`- 关键输入: ${pageContext.requiredInputs.join(' / ')}`);
      if (pageContext.stockCode) lines.push(`- 股票代码: ${pageContext.stockCode}`);
      if (pageContext.selectedCode && pageContext.selectedCode !== pageContext.stockCode) lines.push(`- 当前选中标的: ${pageContext.selectedCode}`);
      if (pageContext.accountId) lines.push(`- 账户 ID: ${pageContext.accountId}`);
      if (pageContext.strategyId) lines.push(`- 策略 ID: ${pageContext.strategyId}`);
      if (pageContext.workspaceId) lines.push(`- 工作区 ID: ${pageContext.workspaceId}`);
      if (pageContext.objectType) lines.push(`- 对象类型: ${pageContext.objectType}`);
      if (pageContext.objectId) lines.push(`- 对象 ID: ${pageContext.objectId}`);
      if (pageContext.resultType) lines.push(`- 结果类型: ${pageContext.resultType}`);
      if (pageContext.tags?.length) lines.push(`- 标签: ${pageContext.tags.join(' / ')}`);
      if (pageContext.suggestions?.length) lines.push(`- 建议问题: ${pageContext.suggestions.join('；')}`);
      if (pageContext.recommendedNextActions?.length) lines.push(`- 推荐下一步: ${pageContext.recommendedNextActions.join('；')}`);
      if (pageContext.evidenceSummary?.length) lines.push(`- 证据摘要: ${pageContext.evidenceSummary.join('；')}`);
      if (pageContext.riskNotes?.length) lines.push(`- 风险提示: ${pageContext.riskNotes.join('；')}`);
      if (pageContext.dataFreshness) lines.push(`- 数据时效: ${pageContext.dataFreshness}`);
      const personalStrategyContext = pageContext.raw && typeof pageContext.raw === 'object'
        ? (pageContext.raw as Record<string, unknown>).personalStrategyContext
        : null;
      if (personalStrategyContext && typeof personalStrategyContext === 'object' && !Array.isArray(personalStrategyContext)) {
        const ctx = personalStrategyContext as Record<string, unknown>;
        const strategyName = typeof ctx.strategy_name === 'string' ? ctx.strategy_name : '';
        const editable = Boolean(ctx.editable);
        const allowed = ctx.mutation_guard && typeof ctx.mutation_guard === 'object'
          ? Boolean((ctx.mutation_guard as Record<string, unknown>).allowed)
          : false;
        const reason = ctx.mutation_guard && typeof ctx.mutation_guard === 'object'
          ? String((ctx.mutation_guard as Record<string, unknown>).reason ?? '').trim()
          : '';
        lines.push(`- 个人策略上下文: ${strategyName || String(ctx.strategy_id ?? '')}，${editable ? '可编辑' : '只读'}，${allowed ? '允许 AI 建议与修改' : `禁止写入${reason ? `（${reason}）` : ''}`}`);
      }
      const rawContextSummary = this.buildRawContextSummary(pageContext.raw);
      if (rawContextSummary) lines.push(`- 原始上下文摘要: ${rawContextSummary}`);
    }
    if (pageContext || availableActions.length) {
      lines.push('页面联动协议:');
      lines.push(`- 只有用户明确要求执行、运行、打开、跳转、刷新、切换、提交、保存、应用、删除或清理页面动作时，才调用 ${CLIENT_ACTION_TOOL_NAME} 并允许自动执行。`);
      lines.push('- 如果用户是纯咨询型地询问“下一步做什么/给建议/分析/总结/说明/是否应该”，必须先直接回答；可以建议可点击动作，但不能自动执行。用户明确要求运行动作后再总结结果时，按执行型意图处理。');
      lines.push('- 没有合适动作时，必须明确说明当前页没有可执行动作，不能挂起或转去调用无关工具。');
      lines.push('- 回答当前页问题时，至少引用页面上下文中的具体事实，不要退化成泛 Copilot 话术。');
      lines.push('- `generate_update_suggestion` / `advisory` 只代表生成修改建议，不代表已经写库。');
      lines.push('- `optimize` 或 `persist_update` / `stateful` 会写入当前用户个人策略。');
      if (clientActionIntent.hasWritablePersonalStrategyActions) {
        lines.push(`- 服务端判定的最新用户写入意图: ${clientActionIntent.explicitPersonalStrategyWrite ? '明确要求修改/保存/优化，可自动执行 stateful 动作。' : '未明确要求写入；stateful 动作只能挂起等待人工点击。'}`);
      }
      lines.push(`- 服务端判定的最新用户动作执行意图: ${clientActionIntent.explicitActionExecution ? '明确要求执行页面动作。' : '未明确要求执行；动作只能挂起等待人工点击。'}`);
      if (clientActionIntent.explicitSuggestionOnly) {
        lines.push('- 最新用户意图更接近“先给建议不要落库”，优先选择 `generate_update_suggestion`，不要直接调用写入动作。');
      }
    }
    if (availableActions.length) {
      lines.push('客户端可执行动作:');
      availableActions.slice(0, 20).forEach((action) => {
        const tags = [
          action.strategyActionKind ? `kind=${action.strategyActionKind}` : '',
          action.mutationEffect ? `effect=${action.mutationEffect}` : '',
        ].filter(Boolean);
        const metaSuffix = tags.length ? ` [${tags.join(', ')}]` : '';
        lines.push(`- ${action.id}: ${action.label}${metaSuffix}${action.description ? `，${action.description}` : ''}`);
      });
      lines.push(`如果需要前端执行动作，请调用 ${CLIENT_ACTION_TOOL_NAME}。`);
    } else if (pageContext) {
      lines.push('当前页面未注册可执行动作；如果用户要求联动，必须明确说明当前页没有安全动作可执行。');
    }

    return lines.length ? [{ role: 'system', content: lines.join('\n') }] : [];
  }

  private buildClientActionTool(
    availableActions: ClientActionDescriptor[],
  ): OpenAI.ChatCompletionTool | null {
    if (!availableActions.length) return null;

    return {
      type: 'function',
      function: {
        name: CLIENT_ACTION_TOOL_NAME,
        description: '请求前端安排一个已注册的页面动作或全局动作。只有用户明确要求执行/运行/打开/刷新/提交等动作时才可自动执行；咨询型建议问题必须直接回答或返回待用户确认的动作。',
        parameters: {
          type: 'object',
          additionalProperties: false,
          properties: {
            actionId: {
              type: 'string',
              enum: availableActions.map((action) => action.id),
              description: '要执行的动作 ID，必须来自当前可执行动作列表。',
            },
            reason: {
              type: 'string',
              description: '触发该动作的原因，供前端展示。',
            },
            autoExecute: {
              type: 'boolean',
              description: '是否由前端自动执行该动作。服务端会按用户显式执行意图重新判定；未明确执行时会强制改为 false。',
            },
            payload: {
              type: 'object',
              additionalProperties: true,
              description: '传给客户端动作的可选参数。',
            },
          },
          required: ['actionId'],
        },
      },
    };
  }

  private buildClientActionEvent(
    args: Record<string, unknown>,
    availableActions: ClientActionDescriptor[],
    clientActionIntent: ClientActionExecutionIntent,
  ): Extract<ChatEvent, { type: 'action' }> | null {
    const actionId = typeof args.actionId === 'string' ? args.actionId.trim() : '';
    if (!actionId) return null;

    const meta = availableActions.find((action) => action.id === actionId);
    if (!meta) return null;
    const requestedAutoExecute = args.autoExecute === false ? false : undefined;
    const isStatefulPersonalStrategyAction = meta.mutationEffect === 'stateful'
      && (meta.strategyActionKind === 'persist_update' || meta.strategyActionKind === 'optimize');
    const canAutoExecute = clientActionIntent.explicitActionExecution && !clientActionIntent.explicitSuggestionOnly;
    const resolvedAutoExecute = isStatefulPersonalStrategyAction
      ? clientActionIntent.explicitPersonalStrategyWrite && requestedAutoExecute !== false
      : canAutoExecute && requestedAutoExecute !== false;

    return {
      type: 'action',
      actionId,
      label: meta.label,
      description: meta.description,
      reason: typeof args.reason === 'string' ? args.reason : undefined,
      payload: args.payload && typeof args.payload === 'object' && !Array.isArray(args.payload)
        ? args.payload as Record<string, unknown>
        : undefined,
      autoExecute: resolvedAutoExecute,
    };
  }

  private analyzeClientActionIntent(
    messages: ChatMessageInput[],
    pageContext: ChatPageContext | null,
    availableActions: ClientActionDescriptor[],
  ): ClientActionExecutionIntent {
    const latestUserMessage = [...messages]
      .reverse()
      .find((message) => message.role === 'user')?.content?.trim() ?? '';
    const hasWritablePersonalStrategyActions = availableActions.some((action) => (
      action.mutationEffect === 'stateful'
      && (action.strategyActionKind === 'persist_update' || action.strategyActionKind === 'optimize')
    ));
    const hasPersonalStrategyContext = Boolean(
      pageContext?.raw
      && typeof pageContext.raw === 'object'
      && (
        (pageContext.raw as Record<string, unknown>).personalStrategyContext
        || pageContext.objectType === 'personal_strategy'
      ),
    );
    const writeVerbPattern = /(修改|改一下|更新|保存|落库|写入|应用|套用|提交|覆盖|替换|优化|执行优化|直接改|直接保存|帮我改|帮我更新|帮我保存|patch|update|save|apply|persist|optimi[sz]e|edit|change|rewrite)/i;
    const suggestionOnlyPattern = /(只给建议|先给建议|先出建议|不要保存|先不要保存|不要落库|不落库|不要写入|不要自动执行|别自动执行|不要直接执行|别直接执行|只看建议|suggest only|advisory only|do not save|don't save|do not auto.?execute|don't auto.?execute|just suggest)/i;
    const advisoryQuestionPattern = /(下一步|建议|说明|解释|是否|要不要|该不该|可以怎么|怎么做|怎么看|what|why|how|should|suggest|advice|explain)/i;
    const actionExecutionPattern = /(运行|执行|打开|跳转|刷新|切换|提交|保存|应用|删除|清理|点击|点一下|直接运行|直接执行|帮我运行|帮我执行|run|execute|open|navigate|refresh|switch|submit|save|apply|delete|cleanup|trigger|invoke)/i;
    const explicitActionExecution = actionExecutionPattern.test(latestUserMessage)
      && !suggestionOnlyPattern.test(latestUserMessage)
      && !advisoryQuestionPattern.test(latestUserMessage.replace(actionExecutionPattern, ''));
    const explicitPersonalStrategyWrite = hasWritablePersonalStrategyActions
      && hasPersonalStrategyContext
      && !suggestionOnlyPattern.test(latestUserMessage)
      && !advisoryQuestionPattern.test(latestUserMessage)
      && writeVerbPattern.test(latestUserMessage);

    return {
      latestUserMessage,
      explicitActionExecution,
      explicitPersonalStrategyWrite,
      explicitSuggestionOnly: suggestionOnlyPattern.test(latestUserMessage),
      hasWritablePersonalStrategyActions,
    };
  }

  private isLocalToolName(name: string) {
    return Object.values(LOCAL_CONTEXT_TOOL_NAMES).includes(name as typeof LOCAL_CONTEXT_TOOL_NAMES[keyof typeof LOCAL_CONTEXT_TOOL_NAMES]);
  }

  private async callLocalTool(userId: string, name: string, args: Record<string, unknown>) {
    if (name === LOCAL_CONTEXT_TOOL_NAMES.behaviorSummary) {
      const summary = await this.behaviorService.getRecentSummary(userId, {
        limit: this.toClampedNumber(args.limit, 20, 1, 50),
        days: this.toClampedNumber(args.days, 30, 1, 30),
      });
      return summary ?? {
        visible: false,
        message: '当前没有可用的前端行为摘要',
      };
    }

    if (name === LOCAL_CONTEXT_TOOL_NAMES.behaviorEvidence) {
      return {
        items: await this.behaviorService.getEvidence(userId, {
          limit: this.toClampedNumber(args.limit, 12, 1, 20),
          days: this.toClampedNumber(args.days, 30, 1, 30),
          pageKey: this.toOptionalString(args.pageKey),
          eventType: this.toOptionalString(args.eventType),
          source: this.toOptionalString(args.source),
        }),
      };
    }

    return { error: `unknown local tool: ${name}` };
  }

  private toClampedNumber(value: unknown, fallback: number, min: number, max: number) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
  }

  private toOptionalString(value: unknown) {
    const normalized = String(value ?? '').trim();
    return normalized || null;
  }

  private createRoundTimeoutGuard() {
    const controller = new AbortController();
    let message = `模型在 ${FIRST_RESPONSE_TIMEOUT_MS / 1000} 秒内未返回内容或动作，请重试`;
    let firstResponseSeen = false;
    const firstResponseTimer = setTimeout(() => {
      message = `模型在 ${FIRST_RESPONSE_TIMEOUT_MS / 1000} 秒内未返回内容或动作，请重试`;
      controller.abort();
    }, FIRST_RESPONSE_TIMEOUT_MS);
    const roundTimer = setTimeout(() => {
      message = `单轮对话超过 ${ROUND_TIMEOUT_MS / 1000} 秒，请重试`;
      controller.abort();
    }, ROUND_TIMEOUT_MS);

    return {
      controller,
      get firstResponseSeen() {
        return firstResponseSeen;
      },
      get message() {
        return message;
      },
      markFirstResponse() {
        if (firstResponseSeen) return;
        firstResponseSeen = true;
        clearTimeout(firstResponseTimer);
      },
      dispose() {
        clearTimeout(firstResponseTimer);
        clearTimeout(roundTimer);
      },
    };
  }

  private isAbortLikeError(error: unknown) {
    if (error instanceof Error && error.name === 'AbortError') {
      return true;
    }
    return /abort/i.test(error instanceof Error ? error.message : String(error));
  }

  private formatUpstreamError(error: unknown) {
    const status = this.extractErrorStatus(error);
    if (status === 401 || status === 403 || status === 404 || status === 429) {
      return `模型服务返回 ${status}，已展示页面上下文降级摘要`;
    }
    if (status != null && status >= 500) {
      return `模型服务暂不可用（${status}），已展示页面上下文降级摘要`;
    }
    const message = error instanceof Error ? error.message : String(error);
    if (/context|token|maximum|too large|payload/i.test(message)) {
      return '模型上下文过大或超过上游限制，已展示页面上下文降级摘要';
    }
    return '模型服务调用失败，已展示页面上下文降级摘要';
  }

  private extractErrorStatus(error: unknown): number | null {
    if (!error || typeof error !== 'object') return null;
    const record = error as Record<string, unknown>;
    const status = Number(record.status ?? record.code);
    return Number.isFinite(status) ? status : null;
  }

  private buildRawContextSummary(raw: Record<string, unknown> | undefined) {
    if (!raw || typeof raw !== 'object') return '';
    const parts: string[] = [];
    for (const [label, key] of [
      ['strategyId', 'strategyId'],
      ['activeTab', 'activeTab'],
      ['marketStatus', 'marketStatus'],
      ['incubationStage', 'incubationStage'],
      ['riskEvents', 'riskEvents'],
      ['vectorProfiles', 'vectorProfiles'],
      ['selectedCode', 'selectedCode'],
      ['accountId', 'accountId'],
      ['workspaceId', 'workspaceId'],
    ] as const) {
      const value = raw[key];
      if (value !== undefined && value !== null && value !== '') {
        parts.push(`${label}=${this.compactContextScalar(value)}`);
      }
    }

    const ownerState = raw.ownerState;
    if (ownerState && typeof ownerState === 'object' && !Array.isArray(ownerState)) {
      const owner = ownerState as Record<string, unknown>;
      const ownerLabel = this.compactContextScalar(owner.kind ?? owner.author_id ?? '');
      if (ownerLabel) parts.push(`owner=${ownerLabel}`);
      if (owner.editable !== undefined) parts.push(`editable=${Boolean(owner.editable)}`);
      if (owner.personal_strategy !== undefined) parts.push(`personal=${Boolean(owner.personal_strategy)}`);
    }

    const personalStrategyContext = raw.personalStrategyContext;
    if (personalStrategyContext && typeof personalStrategyContext === 'object' && !Array.isArray(personalStrategyContext)) {
      const ctx = personalStrategyContext as Record<string, unknown>;
      const name = this.compactContextScalar(ctx.strategy_name ?? ctx.strategy_id ?? '');
      const status = this.compactContextScalar(ctx.status ?? '');
      const editable = ctx.editable !== undefined ? `，${Boolean(ctx.editable) ? '可编辑' : '只读'}` : '';
      parts.push(`personalStrategy=${name}${status ? `，状态 ${status}` : ''}${editable}`);
    }

    if (parts.length) return parts.slice(0, 16).join('；');
    return JSON.stringify(this.compactRawContext(raw)).slice(0, 1200);
  }

  private compactRawContext(value: unknown, depth = 0): unknown {
    if (value == null) return value;
    if (typeof value === 'string') return this.compactContextScalar(value);
    if (typeof value === 'number' || typeof value === 'boolean') return value;
    if (depth >= 2) return '[truncated]';
    if (Array.isArray(value)) return value.slice(0, 6).map((item) => this.compactRawContext(item, depth + 1));
    if (typeof value === 'object') {
      const result: Record<string, unknown> = {};
      for (const [key, nested] of Object.entries(value as Record<string, unknown>).slice(0, 16)) {
        result[key] = this.compactRawContext(nested, depth + 1);
      }
      return result;
    }
    return String(value);
  }

  private compactContextScalar(value: unknown) {
    const text = String(value ?? '').trim();
    return text.length > 180 ? `${text.slice(0, 180)}...` : text;
  }
}
