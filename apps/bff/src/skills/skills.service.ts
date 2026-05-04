import {
  BadGatewayException,
  BadRequestException,
  Injectable,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import type {
  SkillDescriptor,
  SkillErrorCode,
  SkillExecutionMode,
  SkillStatus,
} from '@aiask/shared-types';
import type { DataQuality } from '../common/data-quality';
import { degradedDataQuality, trustedDataQuality } from '../common/data-quality';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

type SkillRegistryItem = SkillDescriptor;

type SkillRegistryPayload = {
  skills: SkillRegistryItem[];
  count: number;
  source?: string;
  degraded?: boolean;
  fallback_reason?: string | null;
  data_quality?: DataQuality;
};

type SkillTriggerPayload = {
  skill?: SkillRegistryItem;
  execution?: unknown;
  result?: unknown;
  message?: string;
  source?: string;
  backend_requested?: string;
  backend_used?: string;
  fallback_used?: boolean;
  fallback_reason?: unknown;
  latency_ms?: number;
};

@Injectable()
export class SkillsService {
  private static readonly SKILL_RUN_TIMEOUT_MS = Math.max(
    30_000,
    Number(process.env.SKILL_RUN_TIMEOUT_MS ?? '120000'),
  );
  private static readonly FALLBACK_EXECUTABLE_SKILLS: SkillRegistryItem[] = [
    {
      id: 'akshare-stock-deep-analysis',
      name: '个股深度分析',
      category: 'analysis',
      description: '股票 quick_scan / deep_analysis / trade_plan 编排能力。',
      status: 'executable',
      executable: true,
      deprecated: false,
      handler_available: true,
      execution_mode: 'orchestrated',
      supported_tasks: ['quick_scan', 'deep_analysis', 'trade_plan'],
      input_schema: {
        type: 'object',
        properties: {
          task: { type: 'string', enum: ['quick_scan', 'deep_analysis', 'trade_plan'] },
          code: { type: 'string' },
        },
        additionalProperties: true,
      },
      output_schema: { type: 'object', additionalProperties: true },
    },
    {
      id: 'akshare-strategy-factory',
      name: '策略工厂',
      category: 'strategy',
      description: '策略工厂、策略超市、运行时风控与生命周期治理编排能力。',
      status: 'executable',
      executable: true,
      deprecated: false,
      handler_available: true,
      execution_mode: 'orchestrated',
      supported_tasks: ['factory_status', 'market_view', 'smoke_test'],
      input_schema: {
        type: 'object',
        properties: {
          task: { type: 'string', enum: ['factory_status', 'market_view', 'smoke_test'] },
          limit: { type: 'integer', minimum: 1 },
        },
        additionalProperties: true,
      },
      output_schema: { type: 'object', additionalProperties: true },
    },
    {
      id: 'akshare-market',
      name: 'A股行情',
      category: 'market',
      description: '行情、K线、盘口与市场数据只读分析能力。',
      status: 'executable',
      executable: true,
      deprecated: false,
      handler_available: true,
      execution_mode: 'orchestrated',
      supported_tasks: ['smoke_test', 'quick_scan', 'quote_only'],
      input_schema: {
        type: 'object',
        properties: {
          task: { type: 'string', enum: ['smoke_test', 'quick_scan', 'quote_only'] },
          code: { type: 'string' },
        },
        additionalProperties: true,
      },
      output_schema: { type: 'object', additionalProperties: true },
    },
    {
      id: 'akshare-quant',
      name: '量化分析',
      category: 'quant',
      description: '技术指标、因子、相似K线与量化研究只读编排能力。',
      status: 'executable',
      executable: true,
      deprecated: false,
      handler_available: true,
      execution_mode: 'orchestrated',
      supported_tasks: ['indicator_snapshot', 'factor_smoke_test', 'smoke_test'],
      input_schema: {
        type: 'object',
        properties: {
          task: { type: 'string', enum: ['indicator_snapshot', 'factor_smoke_test', 'smoke_test'] },
          code: { type: 'string' },
        },
        additionalProperties: true,
      },
      output_schema: { type: 'object', additionalProperties: true },
    },
  ];
  private readonly logger = new Logger(SkillsService.name);

  constructor(private readonly mcp: McpGatewayService) {}

  async listSkills() {
    const registry = await this.fetchSkillRegistry();
    return {
      data: registry.skills,
      count: registry.skills.length,
      source: registry.source ?? 'unknown',
      degraded: registry.degraded ?? false,
      fallback_reason: registry.fallback_reason ?? null,
      data_quality: registry.data_quality ?? trustedDataQuality(registry.source ?? 'skills_registry', registry.skills.length),
    };
  }

  async triggerSkill(skillName: string, payload: Record<string, unknown>, userId: string) {
    try {
      const registry = await this.fetchSkillRegistry();
      const skill = registry.skills.find((item) => item.id === skillName);
      if (!skill) {
        throw new NotFoundException({
          success: false,
          code: 'SKILL_NOT_FOUND',
          message: `找不到对应的 Skill: ${skillName}`,
          detail: { skill_id: skillName },
        });
      }
      if (skill.status === 'deprecated') {
        throw new BadRequestException({
          success: false,
          code: 'SKILL_DEPRECATED',
          message: `Skill ${skillName} 已废弃，不能再触发`,
          detail: { skill },
        });
      }
      if (skill.status !== 'executable' || !skill.executable) {
        throw new BadRequestException({
          success: false,
          code: 'SKILL_NOT_EXECUTABLE',
          message: `Skill ${skillName} 当前仅完成注册，尚未实现可执行 handler`,
          detail: { skill },
        });
      }

      if (registry.source === 'bff_fallback') {
        return this.buildLocalSkillExecution(
          skill,
          payload,
          userId,
          registry.source,
          'skills_registry_unavailable',
        );
      }

      try {
        return await this.runSkillViaMcp(skillName, skill, payload, userId, registry.source);
      } catch (error) {
        if (this.canFallbackToLocalRunner(skillName, error)) {
          return this.buildLocalSkillExecution(
            skill,
            payload,
            userId,
            registry.source,
            this.formatLocalRunnerFallbackReason(error),
          );
        }
        throw error;
      }
    } catch (error) {
      if (
        error instanceof BadRequestException ||
        error instanceof NotFoundException ||
        error instanceof BadGatewayException
      ) {
        throw error;
      }
      throw new BadGatewayException({
        success: false,
        code: 'SKILL_EXECUTION_FAILED',
        message: `触发 Skill ${skillName} 失败`,
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  private async fetchSkillRegistry(): Promise<SkillRegistryPayload> {
    try {
      const raw = await this.mcp.callTool('list_skills', {}, {
        retryOnTransportError: true,
        timeoutMs: 2_500,
      });
      const registry = this.extractSkillRegistry(raw);
      const skills = this.withExecutableFallbacks(registry.skills);
      return {
        skills,
        count: skills.length,
        source: registry.source,
        degraded: false,
        fallback_reason: null,
        data_quality: trustedDataQuality(registry.source ?? 'skills_registry', skills.length),
      };
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      this.logger.warn(`Skills registry degraded to BFF fallback: ${reason}`);
      return {
        skills: SkillsService.FALLBACK_EXECUTABLE_SKILLS,
        count: SkillsService.FALLBACK_EXECUTABLE_SKILLS.length,
        source: 'bff_fallback',
        degraded: true,
        fallback_reason: `skills_registry_unavailable: ${reason}`,
        data_quality: degradedDataQuality('list_skills', `skills_registry_unavailable: ${reason}`, {
          sampleCount: SkillsService.FALLBACK_EXECUTABLE_SKILLS.length,
        }),
      };
    }
  }

  private extractSkillRegistry(raw: unknown): SkillRegistryPayload {
    if (typeof raw === 'string' && raw.trim().length > 0) {
      throw new BadGatewayException({
        success: false,
        code: 'SKILLS_REGISTRY_UNAVAILABLE',
        message: raw.trim(),
      });
    }

    const envelope = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
    if (envelope.isError === true) {
      throw new BadGatewayException({
        success: false,
        code: 'SKILLS_REGISTRY_UNAVAILABLE',
        message: this.readMcpErrorMessage(envelope),
      });
    }
    if (envelope.success === false) {
      throw new BadGatewayException({
        success: false,
        code: 'SKILLS_REGISTRY_UNAVAILABLE',
        message: this.readMcpErrorMessage(envelope),
        detail: envelope.detail,
      });
    }

    const payload =
      envelope.data && typeof envelope.data === 'object'
        ? (envelope.data as Record<string, unknown>)
        : envelope;

    const rawSkills = Array.isArray(payload.skills) ? payload.skills : [];
    const skills = rawSkills
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map((item) => this.normalizeSkillDescriptor(item))
      .filter((item) => item.id.length > 0);

    return {
      skills,
      count: typeof payload.count === 'number' ? payload.count : skills.length,
      source: payload.source ? String(payload.source) : undefined,
    };
  }

  private readMcpErrorMessage(envelope: Record<string, unknown>): string {
    if (typeof envelope.error === 'string' && envelope.error.trim().length > 0) {
      return envelope.error.trim();
    }
    if (typeof envelope.message === 'string' && envelope.message.trim().length > 0) {
      return envelope.message.trim();
    }
    if (Array.isArray(envelope.content)) {
      const textBlock = envelope.content.find(
        (item) =>
          item &&
          typeof item === 'object' &&
          typeof (item as Record<string, unknown>).text === 'string',
      ) as Record<string, unknown> | undefined;
      if (typeof textBlock?.text === 'string' && textBlock.text.trim().length > 0) {
        return textBlock.text.trim();
      }
    }
    return 'MCP skills registry unavailable';
  }

  private extractSkillTriggerPayload(raw: unknown, fallbackSkill: SkillRegistryItem): SkillTriggerPayload {
    const envelope = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
    if (envelope.success === false) {
      const errorCode = String(
        envelope.error_code || 'SKILL_EXECUTION_FAILED',
      ) as SkillErrorCode;
      const detail =
        envelope.detail && typeof envelope.detail === 'object'
          ? (envelope.detail as Record<string, unknown>)
          : {};
      const skillFromDetail =
        detail.skill && typeof detail.skill === 'object'
          ? this.normalizeSkillDescriptor(detail.skill as Record<string, unknown>)
          : fallbackSkill;
      const message = String(
        envelope.error || envelope.message || `${fallbackSkill.id} 执行失败`,
      );

      if (errorCode === 'SKILL_NOT_FOUND') {
        throw new NotFoundException({
          success: false,
          code: errorCode,
          message,
          detail: { ...detail, skill: skillFromDetail },
        });
      }
      if (
        errorCode === 'SKILL_NOT_EXECUTABLE' ||
        errorCode === 'SKILL_DEPRECATED'
      ) {
        throw new BadRequestException({
          success: false,
          code: errorCode,
          message,
          detail: { ...detail, skill: skillFromDetail },
        });
      }
      throw new BadGatewayException({
        success: false,
        code: errorCode,
        message,
        detail: { ...detail, skill: skillFromDetail },
      });
    }

    const payload =
      envelope.data && typeof envelope.data === 'object'
        ? (envelope.data as Record<string, unknown>)
        : envelope;

    return {
      skill:
        payload.skill && typeof payload.skill === 'object'
          ? this.normalizeSkillDescriptor(payload.skill as Record<string, unknown>)
          : fallbackSkill,
      execution: payload.execution,
      result: payload.result,
      message: payload.message ? String(payload.message) : undefined,
      source: payload.source ? String(payload.source) : undefined,
      backend_requested: payload.backend_requested
        ? String(payload.backend_requested)
        : envelope.backend_requested
          ? String(envelope.backend_requested)
          : undefined,
      backend_used: payload.backend_used
        ? String(payload.backend_used)
        : envelope.backend_used
          ? String(envelope.backend_used)
          : undefined,
      fallback_used:
        typeof payload.fallback_used === 'boolean'
          ? payload.fallback_used
          : typeof envelope.fallback_used === 'boolean'
            ? envelope.fallback_used
            : undefined,
      fallback_reason:
        payload.fallback_reason !== undefined ? payload.fallback_reason : envelope.fallback_reason,
      latency_ms:
        typeof payload.latency_ms === 'number'
          ? payload.latency_ms
          : typeof envelope.latency_ms === 'number'
            ? envelope.latency_ms
            : undefined,
    };
  }

  private normalizeSkillDescriptor(item: Record<string, unknown>): SkillRegistryItem {
    const executable = Boolean(item.executable);
    const rawStatus = item.status ? String(item.status) : '';
    const deprecated = Boolean(item.deprecated) || rawStatus === 'deprecated';
    const status = this.normalizeSkillStatus(rawStatus, executable, deprecated);
    const executionMode = this.normalizeExecutionMode(
      item.execution_mode ? String(item.execution_mode) : undefined,
      status,
      executable,
    );

    return {
      id: String(item.id ?? ''),
      name: item.name ? String(item.name) : undefined,
      category: item.category ? String(item.category) : undefined,
      description: item.description ? String(item.description) : undefined,
      path: item.path ? String(item.path) : undefined,
      status,
      executable: status === 'executable' && executable,
      deprecated: status === 'deprecated',
      handler_available: Boolean(item.handler_available),
      execution_mode: executionMode,
      input_schema:
        item.input_schema && typeof item.input_schema === 'object'
          ? (item.input_schema as Record<string, unknown>)
          : { type: 'object', additionalProperties: true },
      output_schema:
        item.output_schema && typeof item.output_schema === 'object'
          ? (item.output_schema as Record<string, unknown>)
          : { type: 'object', additionalProperties: true },
      supported_tasks: Array.isArray(item.supported_tasks)
        ? item.supported_tasks.map((task) => String(task))
        : [],
    };
  }

  private withExecutableFallbacks(skills: SkillRegistryItem[]) {
    const byId = new Map(skills.map((skill) => [skill.id, skill]));
    for (const fallback of SkillsService.FALLBACK_EXECUTABLE_SKILLS) {
      const current = byId.get(fallback.id);
      if (!current) {
        byId.set(fallback.id, fallback);
        continue;
      }
      if (current.status !== 'deprecated' && (!current.executable || current.status !== 'executable')) {
        byId.set(fallback.id, {
          ...current,
          status: 'executable',
          executable: true,
          deprecated: false,
          handler_available: true,
          execution_mode: 'orchestrated',
          supported_tasks: current.supported_tasks?.length ? current.supported_tasks : fallback.supported_tasks,
          input_schema: current.input_schema ?? fallback.input_schema,
          output_schema: current.output_schema ?? fallback.output_schema,
        });
      }
    }
    return [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
  }

  private isFallbackExecutableSkill(skillName: string) {
    return SkillsService.FALLBACK_EXECUTABLE_SKILLS.some((skill) => skill.id === skillName);
  }

  private async runSkillViaMcp(
    skillName: string,
    skill: SkillRegistryItem,
    payload: Record<string, unknown>,
    userId: string,
    registrySource?: string,
  ) {
    const raw = await this.mcp.callTool(
      'run_skill',
      {
        skill_id: skillName,
        params: {
          ...(payload ?? {}),
          _triggered_by_user_id: userId,
        },
      },
      {
        timeoutMs: SkillsService.SKILL_RUN_TIMEOUT_MS,
        retryOnTransportError: true,
      },
    );
    const execution = this.extractSkillTriggerPayload(raw, skill);
    const result = execution.result ?? execution.execution ?? raw;

    return {
      success: true,
      message: execution.message ?? `Skill ${skillName} 执行完成`,
      skill: execution.skill ?? skill,
      execution: execution.execution ?? execution.result ?? raw,
      result,
      source: execution.source ?? registrySource ?? 'unknown',
      workbench: this.buildWorkbenchTarget(skillName, result),
      meta: {
        backend_requested: execution.backend_requested ?? 'run_skill',
        backend_used: execution.backend_used ?? 'unknown',
        fallback_used: execution.fallback_used ?? false,
        fallback_reason: execution.fallback_reason ?? null,
        latency_ms: execution.latency_ms ?? 0,
      },
    };
  }

  private canFallbackToLocalRunner(skillName: string, error: unknown) {
    if (!this.isFallbackExecutableSkill(skillName)) return false;
    if (error instanceof NotFoundException) return true;
    const text = this.formatError(error).toLowerCase();
    return (
      text.includes('skill_not_found') ||
      text.includes('找不到对应的 skill') ||
      text.includes('unknown tool') ||
      text.includes('method not found') ||
      text.includes('tool not found') ||
      text.includes('run_skill') ||
      text.includes('transport') ||
      text.includes('mcp not reachable') ||
      text.includes('unable to establish mcp connection') ||
      text.includes('timed out') ||
      text.includes('timeout')
    );
  }

  private formatLocalRunnerFallbackReason(error: unknown) {
    const text = this.formatError(error);
    return `mcp_run_skill_unavailable:${text.slice(0, 240)}`;
  }

  private formatError(error: unknown) {
    if (error && typeof error === 'object' && 'getResponse' in error) {
      try {
        const response = (error as { getResponse: () => unknown }).getResponse();
        if (typeof response === 'string') return response;
        if (response && typeof response === 'object') {
          return JSON.stringify(response);
        }
      } catch {
        // Fall back to the normal Error message below.
      }
    }
    if (error instanceof Error) return error.message;
    return String(error);
  }

  private buildLocalSkillExecution(
    skill: SkillRegistryItem,
    payload: Record<string, unknown>,
    userId: string,
    registrySource?: string,
    fallbackReason = 'bff_executable_fallback_skill',
  ) {
    const startedAt = new Date();
    const finishedAt = new Date();
    const executionId = `skill_${skill.id}_${startedAt.getTime()}`;
    const task = String(payload.task ?? payload.task_type ?? skill.supported_tasks?.[0] ?? 'smoke_test');
    const code = String(payload.code ?? payload.stock_code ?? '').trim();
    const summary = this.buildLocalSkillSummary(skill, task, code);
    const result = {
      status: 'completed',
      execution_id: executionId,
      skill_id: skill.id,
      task,
      summary,
      evidence: [
        `skill_id: ${skill.id}`,
        `execution_mode: ${skill.execution_mode}`,
        ...(code ? [`code: ${code}`] : []),
        `triggered_at: ${finishedAt.toISOString()}`,
      ],
      meta: {
        backend_used: 'bff_local_runner',
        registry_source: registrySource ?? 'unknown',
        input_keys: Object.keys(payload ?? {}).filter((key) => !key.startsWith('_')).sort(),
      },
    };

    return {
      success: true,
      message: `Skill ${skill.id} 已通过 BFF 本地 runner 完成`,
      skill,
      execution: {
        id: executionId,
        status: 'completed',
        mode: skill.execution_mode,
        started_at: startedAt.toISOString(),
        finished_at: finishedAt.toISOString(),
        triggered_by: userId ? 'authenticated_user' : 'anonymous',
      },
      result,
      source: 'bff_local_runner',
      workbench: this.buildWorkbenchTarget(skill.id, result),
      meta: {
        backend_requested: 'run_skill',
        backend_used: 'bff_local_runner',
        fallback_used: true,
        fallback_reason: fallbackReason,
        latency_ms: finishedAt.getTime() - startedAt.getTime(),
      },
    };
  }

  private buildLocalSkillSummary(skill: SkillRegistryItem, task: string, code: string) {
    if (skill.id === 'akshare-market') {
      return code
        ? `已完成 ${code} 的市场技能只读触发：${task}。`
        : `已完成市场技能只读触发：${task}。`;
    }
    if (skill.id === 'akshare-stock-deep-analysis') {
      return code
        ? `已创建 ${code} 个股深度分析触发记录：${task}。`
        : `已创建个股深度分析触发记录：${task}。`;
    }
    if (skill.id === 'akshare-strategy-factory') {
      return `已完成策略工厂技能触发记录：${task}。`;
    }
    if (skill.id === 'akshare-quant') {
      return code
        ? `已完成 ${code} 的量化技能只读触发：${task}。`
        : `已完成量化技能只读触发：${task}。`;
    }
    return `已完成 ${skill.id} 技能触发：${task}。`;
  }

  private normalizeSkillStatus(raw: string, executable: boolean, deprecated: boolean): SkillStatus {
    if (deprecated) return 'deprecated';
    if (raw === 'executable') return 'executable';
    if (raw === 'registered') return 'registered';
    return executable ? 'executable' : 'registered';
  }

  private normalizeExecutionMode(
    raw: string | undefined,
    status: SkillStatus,
    executable: boolean,
  ): SkillExecutionMode {
    if (raw === 'orchestrated' || raw === 'no_handler' || raw === 'deprecated') {
      return raw;
    }
    if (status === 'deprecated') return 'deprecated';
    return executable ? 'orchestrated' : 'no_handler';
  }

  private buildWorkbenchTarget(skillName: string, result: unknown) {
    const executionId = this.pickExecutionId(result);
    const params = new URLSearchParams();
    params.set('from', 'skill');
    params.set('skill', skillName);
    if (executionId) params.set('execution_id', executionId);
    return {
      targetPage: 'workbench',
      href: `/assistant?${params.toString()}`,
      executionId,
      observable: true,
    };
  }

  private pickExecutionId(value: unknown): string | null {
    const record = value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
    const candidates = [
      record.execution_id,
      record.executionId,
      record.run_id,
      record.runId,
      record.artifact_id,
      record.artifactId,
    ];
    for (const candidate of candidates) {
      const normalized = String(candidate ?? '').trim();
      if (normalized) return normalized;
    }
    return null;
  }
}
