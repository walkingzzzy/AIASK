import { BadRequestException, Body, Controller, Get, Logger, Post, Req, Res } from '@nestjs/common';
import { IsArray, IsString, IsIn, ValidateNested, IsOptional, MaxLength, ArrayMaxSize, IsObject } from 'class-validator';
import { Type } from 'class-transformer';
import type { Request, Response } from 'express';
import { ChatService } from './chat.service';
import { PreferencesService } from '../auth/preferences.service';
import type { ChatMode } from './chat.protocol';
import { probeCompatibleBaseUrl } from './llm-compat';

class SaveLlmConfigDto {
  @IsOptional() @IsString() apiKey?: string;
  @IsString() baseUrl!: string;
  @IsString() model!: string;
}

class ProbeModelsDto {
  @IsString() baseUrl!: string;
  @IsOptional() @IsString() apiKey?: string;
  @IsOptional() @IsString() model?: string;
}

class ChatMessageDto {
  @IsIn(['user', 'assistant', 'system']) role!: 'user' | 'assistant' | 'system';
  @IsString() @MaxLength(32000) content!: string;
}

class ChatCompletionsDto {
  @IsArray()
  @ArrayMaxSize(100)
  @ValidateNested({ each: true })
  @Type(() => ChatMessageDto)
  messages!: ChatMessageDto[];

  @IsOptional()
  @IsIn(['chat', 'copilot', 'assistant'])
  mode?: ChatMode;

  @IsOptional()
  @ValidateNested()
  @Type(() => ChatPageContextDto)
  pageContext?: ChatPageContextDto | null;

  @IsOptional()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => ClientActionDescriptorDto)
  availableActions?: ClientActionDescriptorDto[];
}

class ChatPageContextDto {
  @IsString() pageKey!: string;
  @IsString() title!: string;
  @IsString() summary!: string;
  @IsOptional() @IsString() primaryGoal?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) requiredInputs?: string[];
  @IsOptional() @IsString() stockCode?: string;
  @IsOptional() @IsString() selectedCode?: string;
  @IsOptional() @IsString() accountId?: string;
  @IsOptional() @IsString() strategyId?: string;
  @IsOptional() @IsString() workspaceId?: string;
  @IsOptional() @IsString() objectType?: string;
  @IsOptional() @IsString() objectId?: string;
  @IsOptional() @IsString() resultType?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) tags?: string[];
  @IsOptional() @IsArray() @IsString({ each: true }) suggestions?: string[];
  @IsOptional() @IsArray() @IsString({ each: true }) recommendedNextActions?: string[];
  @IsOptional() @IsArray() @IsString({ each: true }) evidenceSummary?: string[];
  @IsOptional() @IsArray() @IsString({ each: true }) riskNotes?: string[];
  @IsOptional() @IsString() dataFreshness?: string | null;
  @IsOptional() @IsArray() @IsString({ each: true }) degradedReason?: string[];
  @IsOptional() @IsObject() freshness?: Record<string, unknown> | null;
  @IsOptional() @IsObject() raw?: Record<string, unknown>;
}

class ClientActionDescriptorDto {
  @IsString() id!: string;
  @IsString() label!: string;
  @IsOptional() @IsString() description?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) keywords?: string[];
  @IsOptional() @IsIn(['global', 'page']) scope?: 'global' | 'page';
  @IsOptional() @IsString() pageKey?: string;
  @IsOptional() @IsIn(['view', 'optimize', 'generate_update_suggestion', 'persist_update']) strategyActionKind?: 'view' | 'optimize' | 'generate_update_suggestion' | 'persist_update';
  @IsOptional() @IsIn(['readonly', 'advisory', 'stateful']) mutationEffect?: 'readonly' | 'advisory' | 'stateful';
}

class SyncChatConversationsDto {
  @IsArray() conversations!: unknown[];
}

const MODEL_PRESETS = [
  { provider: 'A-J API', baseUrl: 'https://api.a-j.app/v1', models: ['gpt-5.4'] },
  { provider: 'OpenAI', baseUrl: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { provider: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { provider: 'Moonshot', baseUrl: 'https://api.moonshot.cn/v1', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'] },
  { provider: 'Qwen', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-turbo', 'qwen-plus', 'qwen-max'] },
  { provider: 'GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-flash', 'glm-4', 'glm-4-plus'] },
  { provider: 'Yi', baseUrl: 'https://api.lingyiwanwu.com/v1', models: ['yi-lightning', 'yi-large', 'yi-medium'] },
];

type ChatRequest = Request & {
  user?: { sub?: string; id?: string };
};

const CHAT_SYNC_MAX_CONVERSATIONS = 20;
const CHAT_SYNC_MAX_MESSAGES_PER_CONVERSATION = 40;
const CHAT_SYNC_MAX_CONTENT_LENGTH = 8000;
const CHAT_SYNC_MAX_TEXT_LENGTH = 320;

@Controller('chat')
export class ChatController {
  private readonly logger = new Logger(ChatController.name);

  constructor(
    private readonly chatService: ChatService,
    private readonly preferencesService: PreferencesService,
  ) {}

  @Get('config')
  async getConfig(@Req() req: ChatRequest) {
    const userId = req.user?.sub ?? req.user?.id ?? '';
    const config = await this.preferencesService.getMaskedLlmConfig(String(userId));
    return { success: true, data: config };
  }

  @Post('config')
  async saveConfig(@Req() req: ChatRequest, @Body() body: SaveLlmConfigDto) {
    const userId = req.user?.sub ?? req.user?.id ?? '';
    const currentConfig = await this.preferencesService.getLlmConfig(String(userId));
    const resolvedApiKey = String(body.apiKey ?? '').trim() || (currentConfig?.apiKey ?? '');
    if (!resolvedApiKey) {
      throw new BadRequestException('请填写 API Key');
    }

    const probe = await probeCompatibleBaseUrl({
      baseUrl: body.baseUrl,
      apiKey: resolvedApiKey,
      model: body.model,
    });
    if (!probe.success) {
      throw new BadRequestException(probe.error ?? 'Base URL 与当前模型不兼容');
    }

    await this.preferencesService.setLlmConfig(String(userId), {
      apiKey: body.apiKey,
      baseUrl: probe.normalizedBaseUrl,
      model: body.model,
    });
    const config = await this.preferencesService.getMaskedLlmConfig(String(userId));
    return {
      success: true,
      data: {
        saved: true,
        normalizedBaseUrl: probe.normalizedBaseUrl,
        compatibility: probe.compatibility,
        ...config,
      },
    };
  }

  @Get('models')
  getModels() {
    return { success: true, data: MODEL_PRESETS };
  }

  @Post('probe-models')
  async probeModels(@Req() req: ChatRequest, @Body() body: ProbeModelsDto) {
    const userId = req.user?.sub ?? req.user?.id ?? '';
    const currentConfig = await this.preferencesService.getLlmConfig(String(userId));
    const resolvedApiKey = String(body.apiKey ?? '').trim() || (currentConfig?.apiKey ?? '');
    if (!resolvedApiKey) {
      return { success: false, error: '请先填写 API Key', models: [], normalizedBaseUrl: '' };
    }

    const probe = await probeCompatibleBaseUrl({
      baseUrl: body.baseUrl,
      apiKey: resolvedApiKey,
      model: body.model ?? currentConfig?.model ?? null,
    });

    return {
      success: probe.success,
      models: probe.models,
      error: probe.error,
      normalizedBaseUrl: probe.normalizedBaseUrl,
      compatibility: probe.compatibility,
    };
  }

  @Get('conversations')
  async getConversations(@Req() req: ChatRequest) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const chatHistory = ((prefs.chatHistory ?? {}) as Record<string, unknown>).conversations;
    return { success: true, data: { conversations: Array.isArray(chatHistory) ? chatHistory : [] } };
  }

  @Post('conversations/sync')
  async syncConversations(@Req() req: ChatRequest, @Body() body: SyncChatConversationsDto) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const sanitized = this.sanitizeConversations(body.conversations);
    try {
      await this.preferencesService.setUserPreferences(userId, {
        ...prefs,
        chatHistory: {
          conversations: sanitized.conversations,
          syncedAt: new Date().toISOString(),
          droppedMessages: sanitized.droppedMessages,
        },
      });
      return { success: true, data: { saved: true, count: sanitized.conversations.length, droppedMessages: sanitized.droppedMessages } };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.error(`Chat conversation sync persistence failed: ${message}`);
      return {
        success: true,
        data: {
          saved: false,
          count: 0,
          droppedMessages: sanitized.droppedMessages,
          error: 'chat_history_sync_skipped',
        },
      };
    }
  }

  @Post('completions')
  async completions(@Req() req: ChatRequest, @Res() res: Response, @Body() body: ChatCompletionsDto) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.flushHeaders();

    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    let clientDisconnected = false;
    const markDisconnected = () => {
      clientDisconnected = true;
    };

    req.on('close', markDisconnected);
    res.on('close', markDisconnected);

    try {
      for await (const event of this.chatService.streamChat(userId, body)) {
        if (clientDisconnected || res.writableEnded || res.destroyed) {
          break;
        }
        res.write(`data: ${JSON.stringify(event)}\n\n`);
      }
    } catch (err: unknown) {
      if (!clientDisconnected && !res.writableEnded && !res.destroyed) {
        const message = err instanceof Error ? err.message : String(err);
        res.write(`data: ${JSON.stringify({ type: 'error', message })}\n\n`);
      }
    } finally {
      req.off('close', markDisconnected);
      res.off('close', markDisconnected);
    }

    if (!res.writableEnded && !res.destroyed) {
      res.end();
    }
  }

  private sanitizeConversations(input: unknown[] = []) {
    let droppedMessages = 0;
    const candidates = input
      .map((item) => this.asRecord(item))
      .filter((conversation): conversation is Record<string, unknown> => Boolean(conversation && typeof conversation.id === 'string'))
      .sort((left, right) => {
        const leftTime = typeof left.updatedAt === 'string' ? new Date(left.updatedAt).getTime() : 0;
        const rightTime = typeof right.updatedAt === 'string' ? new Date(right.updatedAt).getTime() : 0;
        return rightTime - leftTime;
      })
      .slice(0, CHAT_SYNC_MAX_CONVERSATIONS);

    const conversations = candidates.map((conversation) => {
      const rawMessages = Array.isArray(conversation.messages) ? conversation.messages : [];
      if (rawMessages.length > CHAT_SYNC_MAX_MESSAGES_PER_CONVERSATION) {
        droppedMessages += rawMessages.length - CHAT_SYNC_MAX_MESSAGES_PER_CONVERSATION;
      }
      const messages = rawMessages
        .slice(-CHAT_SYNC_MAX_MESSAGES_PER_CONVERSATION)
        .map((message) => {
          const sanitized = this.sanitizeMessage(message);
          if (!sanitized) droppedMessages += 1;
          return sanitized;
        })
        .filter((message): message is NonNullable<ReturnType<typeof this.sanitizeMessage>> => message != null);

      return {
        id: this.truncateText(conversation.id, 120),
        title: this.truncateText(conversation.title ?? '当前会话', 160) || '当前会话',
        updatedAt: typeof conversation.updatedAt === 'string' ? conversation.updatedAt : new Date().toISOString(),
        workspaceId: typeof conversation.workspaceId === 'string' ? this.truncateText(conversation.workspaceId, 120) : undefined,
        messages,
      };
    });

    if (droppedMessages > 0) {
      this.logger.warn(`Dropped ${droppedMessages} invalid chat sync messages`);
    }
    return { conversations, droppedMessages };
  }

  private sanitizeMessage(message: unknown) {
    const record = this.asRecord(message);
    if (!record || (record.role !== 'user' && record.role !== 'assistant') || typeof record.id !== 'string') {
      return null;
    }
    const toolCalls = Array.isArray(record.toolCalls)
      ? record.toolCalls.map((item) => this.sanitizeToolCall(item)).filter((item): item is NonNullable<ReturnType<typeof this.sanitizeToolCall>> => item != null)
      : [];
    const actions = Array.isArray(record.actions)
      ? record.actions.map((item) => this.sanitizeAction(item)).filter((item): item is NonNullable<ReturnType<typeof this.sanitizeAction>> => item != null)
      : [];
    const toolTrace = this.sanitizeToolTrace(record.toolTrace);
    const content = this.truncateText(record.content ?? '', CHAT_SYNC_MAX_CONTENT_LENGTH);
    if (!content && toolCalls.length === 0 && actions.length === 0 && !toolTrace) {
      return null;
    }
    return {
      id: this.truncateText(record.id, 120),
      role: record.role,
      content,
      ...(toolCalls.length > 0 ? { toolCalls } : {}),
      ...(actions.length > 0 ? { actions } : {}),
      ...(toolTrace ? { toolTrace } : {}),
    };
  }

  private sanitizeToolCall(value: unknown) {
    const record = this.asRecord(value);
    const id = this.truncateText(record?.id, 120);
    const name = this.truncateText(record?.name, 160);
    if (!id || !name) return null;
    return {
      id,
      name,
      args: this.compactObject(record?.args),
      result: this.summarizeUnknown(record?.result),
      pending: record?.pending === true,
    };
  }

  private sanitizeAction(value: unknown) {
    const record = this.asRecord(value);
    const id = this.truncateText(record?.id, 120);
    const actionId = this.truncateText(record?.actionId, 160);
    const label = this.truncateText(record?.label, 160);
    const status = String(record?.status ?? '');
    if (!id || !actionId || !label || !['pending', 'running', 'done', 'error'].includes(status)) return null;
    return {
      id,
      actionId,
      label,
      description: typeof record?.description === 'string' ? this.truncateText(record.description, 320) : undefined,
      reason: typeof record?.reason === 'string' ? this.truncateText(record.reason, 320) : undefined,
      payload: this.compactObject(record?.payload),
      status,
      autoExecute: record?.autoExecute === true,
      resultMessage: typeof record?.resultMessage === 'string' ? this.truncateText(record.resultMessage, 320) : undefined,
    };
  }

  private sanitizeToolTrace(value: unknown) {
    const record = this.asRecord(value);
    if (!record || record.schemaVersion !== 'tool_trace.v1') return undefined;
    const scope = this.asRecord(record.scope) ?? {};
    const status = String(record.status ?? '');
    const evidenceMode = String(record.evidenceMode ?? '');
    return {
      schemaVersion: 'tool_trace.v1',
      id: this.truncateText(record.id, 120) || 'trace',
      visibility: 'owner_only',
      generatedAt: typeof record.generatedAt === 'string' ? record.generatedAt : new Date().toISOString(),
      status: ['empty', 'running', 'completed', 'partial_error'].includes(status) ? status : 'empty',
      scope: {
        mode: this.truncateText(scope.mode, 80) || undefined,
        pageKey: this.truncateText(scope.pageKey, 120) || undefined,
        objectType: this.truncateText(scope.objectType, 120) || undefined,
        objectId: this.truncateText(scope.objectId, 160) || undefined,
        stockCode: this.truncateText(scope.stockCode, 32) || undefined,
      },
      items: Array.isArray(record.items)
        ? record.items.slice(0, 20).map((item) => this.sanitizeToolTraceItem(item)).filter((item): item is NonNullable<ReturnType<typeof this.sanitizeToolTraceItem>> => item != null)
        : [],
      answerReferences: Array.isArray(record.answerReferences)
        ? record.answerReferences.slice(0, 20).map((item) => this.sanitizeAnswerReference(item)).filter((item): item is NonNullable<ReturnType<typeof this.sanitizeAnswerReference>> => item != null)
        : [],
      evidenceMode: ['mcp_supported', 'tool_supported', 'page_context_supported', 'advisory_only'].includes(evidenceMode) ? evidenceMode : 'advisory_only',
      advisoryOnly: record.advisoryOnly === true,
      advisoryReason: typeof record.advisoryReason === 'string' ? this.truncateText(record.advisoryReason, 320) : undefined,
    };
  }

  private sanitizeToolTraceItem(value: unknown) {
    const record = this.asRecord(value);
    const kind = String(record?.kind ?? '');
    const status = String(record?.status ?? '');
    const id = this.truncateText(record?.id, 120);
    const toolName = this.truncateText(record?.toolName, 160);
    if (!id || !toolName || !['mcp', 'local_context', 'client_action', 'compliance'].includes(kind) || !['pending', 'success', 'error'].includes(status)) return null;
    return {
      id,
      referenceLabel: this.truncateText(record?.referenceLabel, 16) || 'T?',
      kind,
      toolName,
      status,
      startedAt: typeof record?.startedAt === 'string' ? record.startedAt : '',
      finishedAt: typeof record?.finishedAt === 'string' ? record.finishedAt : undefined,
      durationMs: typeof record?.durationMs === 'number' ? record.durationMs : undefined,
      inputSummary: this.compactStringArray(record?.inputSummary, 8, 240),
      outputSummary: this.compactStringArray(record?.outputSummary, 8, 320),
      errorMessage: typeof record?.errorMessage === 'string' ? this.truncateText(record.errorMessage, 320) : undefined,
      citedInAnswer: record?.citedInAnswer === true,
    };
  }

  private sanitizeAnswerReference(value: unknown) {
    const record = this.asRecord(value);
    const itemId = this.truncateText(record?.itemId, 120);
    const toolName = this.truncateText(record?.toolName, 160);
    if (!itemId || !toolName) return null;
    return {
      itemId,
      referenceLabel: this.truncateText(record?.referenceLabel, 16) || 'T?',
      toolName,
      evidenceSummary: this.truncateText(record?.evidenceSummary, 320),
    };
  }

  private compactStringArray(value: unknown, maxItems: number, maxLength: number): string[] {
    return Array.isArray(value)
      ? value.map((item) => this.truncateText(item, maxLength)).filter(Boolean).slice(0, maxItems)
      : [];
  }

  private compactObject(value: unknown): Record<string, unknown> | undefined {
    const record = this.asRecord(value);
    if (!record) return undefined;
    const entries = Object.entries(record).slice(0, 12);
    if (entries.length === 0) return undefined;
    return Object.fromEntries(entries.map(([key, item]) => [key, this.summarizeUnknown(item)]));
  }

  private summarizeUnknown(value: unknown): string | number | boolean | null | undefined {
    if (value == null || typeof value === 'number' || typeof value === 'boolean') return value;
    if (typeof value === 'string') return this.truncateText(value, 1000);
    if (Array.isArray(value)) return `[array:${value.length}]`;
    if (typeof value === 'object') {
      const keys = Object.keys(value as Record<string, unknown>).slice(0, 8);
      return `[object:${keys.join(',')}]`;
    }
    return String(value);
  }

  private truncateText(value: unknown, maxLength = CHAT_SYNC_MAX_TEXT_LENGTH): string {
    const text = String(value ?? '').trim();
    return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
  }

  private asRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null;
  }
}
