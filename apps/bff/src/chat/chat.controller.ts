import { BadRequestException, Body, Controller, Get, Post, Req, Res } from '@nestjs/common';
import { IsArray, IsString, IsIn, ValidateNested, IsOptional, MaxLength, ArrayMaxSize, IsObject, IsBoolean, IsNumber } from 'class-validator';
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

class ChatToolTraceScopeDto {
  @IsOptional() @IsString() @MaxLength(80) mode?: string;
  @IsOptional() @IsString() @MaxLength(120) pageKey?: string;
  @IsOptional() @IsString() @MaxLength(120) objectType?: string;
  @IsOptional() @IsString() @MaxLength(160) objectId?: string;
  @IsOptional() @IsString() @MaxLength(32) stockCode?: string;
}

class ChatToolTraceItemDto {
  @IsString() @MaxLength(120) id!: string;
  @IsString() @MaxLength(16) referenceLabel!: string;
  @IsIn(['mcp', 'local_context', 'client_action']) kind!: 'mcp' | 'local_context' | 'client_action';
  @IsString() @MaxLength(160) toolName!: string;
  @IsIn(['pending', 'success', 'error']) status!: 'pending' | 'success' | 'error';
  @IsString() startedAt!: string;
  @IsOptional() @IsString() finishedAt?: string;
  @IsOptional() @IsNumber() durationMs?: number;
  @IsArray() @ArrayMaxSize(12) @IsString({ each: true }) @MaxLength(240, { each: true }) inputSummary!: string[];
  @IsArray() @ArrayMaxSize(12) @IsString({ each: true }) @MaxLength(320, { each: true }) outputSummary!: string[];
  @IsOptional() @IsString() @MaxLength(320) errorMessage?: string;
  @IsOptional() @IsBoolean() citedInAnswer?: boolean;
}

class ChatToolTraceAnswerReferenceDto {
  @IsString() @MaxLength(120) itemId!: string;
  @IsString() @MaxLength(16) referenceLabel!: string;
  @IsString() @MaxLength(160) toolName!: string;
  @IsString() @MaxLength(320) evidenceSummary!: string;
}

class ChatToolTraceDto {
  @IsIn(['tool_trace.v1']) schemaVersion!: 'tool_trace.v1';
  @IsString() @MaxLength(120) id!: string;
  @IsIn(['owner_only']) visibility!: 'owner_only';
  @IsString() generatedAt!: string;
  @IsIn(['empty', 'running', 'completed', 'partial_error']) status!: 'empty' | 'running' | 'completed' | 'partial_error';
  @ValidateNested() @Type(() => ChatToolTraceScopeDto) scope!: ChatToolTraceScopeDto;
  @IsArray() @ArrayMaxSize(40) @ValidateNested({ each: true }) @Type(() => ChatToolTraceItemDto) items!: ChatToolTraceItemDto[];
  @IsArray() @ArrayMaxSize(40) @ValidateNested({ each: true }) @Type(() => ChatToolTraceAnswerReferenceDto) answerReferences!: ChatToolTraceAnswerReferenceDto[];
  @IsIn(['mcp_supported', 'tool_supported', 'page_context_supported', 'advisory_only']) evidenceMode!: 'mcp_supported' | 'tool_supported' | 'page_context_supported' | 'advisory_only';
  @IsBoolean() advisoryOnly!: boolean;
  @IsOptional() @IsString() @MaxLength(320) advisoryReason?: string;
}

class ChatConversationMessageDto {
  @IsString() id!: string;
  @IsIn(['user', 'assistant']) role!: 'user' | 'assistant';
  @IsString() content!: string;
  @IsOptional()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => ChatConversationToolCallDto)
  toolCalls?: ChatConversationToolCallDto[];

  @IsOptional()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => ChatConversationActionDto)
  actions?: ChatConversationActionDto[];

  @IsOptional()
  @ValidateNested()
  @Type(() => ChatToolTraceDto)
  toolTrace?: ChatToolTraceDto;
}

class ChatConversationToolCallDto {
  @IsString() id!: string;
  @IsString() name!: string;
  @IsOptional() @IsObject() args?: Record<string, unknown>;
  @IsOptional() result?: unknown;
  @IsOptional() @IsBoolean() pending?: boolean;
}

class ChatConversationActionDto {
  @IsString() id!: string;
  @IsString() actionId!: string;
  @IsString() label!: string;
  @IsOptional() @IsString() description?: string;
  @IsOptional() @IsString() reason?: string;
  @IsOptional() @IsObject() payload?: Record<string, unknown>;
  @IsIn(['pending', 'running', 'done', 'error']) status!: 'pending' | 'running' | 'done' | 'error';
  @IsOptional() @IsBoolean() autoExecute?: boolean;
  @IsOptional() @IsString() resultMessage?: string;
}

class ChatConversationDto {
  @IsString() id!: string;
  @IsOptional() @IsString() title?: string;
  @IsString() updatedAt!: string;
  @IsOptional() @IsString() workspaceId?: string;
  @IsArray() @ValidateNested({ each: true }) @Type(() => ChatConversationMessageDto) messages!: ChatConversationMessageDto[];
}

class SyncChatConversationsDto {
  @IsArray() @ValidateNested({ each: true }) @Type(() => ChatConversationDto) conversations!: ChatConversationDto[];
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

@Controller('chat')
export class ChatController {
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
    await this.preferencesService.setUserPreferences(userId, {
      ...prefs,
      chatHistory: {
        conversations: body.conversations.slice(0, 50),
        syncedAt: new Date().toISOString(),
      },
    });
    return { success: true, data: { saved: true, count: body.conversations.length } };
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
}
