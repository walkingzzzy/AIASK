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
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

type SkillRegistryItem = SkillDescriptor;

type SkillRegistryPayload = {
  skills: SkillRegistryItem[];
  count: number;
  source?: string;
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
  private readonly logger = new Logger(SkillsService.name);

  constructor(private readonly mcp: McpGatewayService) {}

  async listSkills() {
    try {
      const registry = await this.fetchSkillRegistry();
      return {
        data: registry.skills,
        count: registry.count,
        source: registry.source ?? 'unknown',
      };
    } catch (error) {
      this.logger.error(`Failed to list skills from MCP registry: ${error}`);
      if (error instanceof BadGatewayException) {
        throw error;
      }
      throw new BadGatewayException({
        success: false,
        code: 'SKILLS_REGISTRY_UNAVAILABLE',
        message: '技能注册表暂不可用',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
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
        },
      );
      const execution = this.extractSkillTriggerPayload(raw, skill);

      return {
        success: true,
        message: execution.message ?? `Skill ${skillName} 执行完成`,
        skill: execution.skill ?? skill,
        execution: execution.execution ?? execution.result ?? raw,
        result: execution.result ?? execution.execution ?? raw,
        source: execution.source ?? registry.source ?? 'unknown',
        meta: {
          backend_requested: execution.backend_requested,
          backend_used: execution.backend_used,
          fallback_used: execution.fallback_used,
          fallback_reason: execution.fallback_reason,
          latency_ms: execution.latency_ms,
        },
      };
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
    const raw = await this.mcp.callTool('list_skills', {});
    const registry = this.extractSkillRegistry(raw);
    return {
      skills: registry.skills,
      count: registry.count ?? registry.skills.length,
      source: registry.source,
    };
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
      backend_requested: envelope.backend_requested
        ? String(envelope.backend_requested)
        : undefined,
      backend_used: envelope.backend_used ? String(envelope.backend_used) : undefined,
      fallback_used:
        typeof envelope.fallback_used === 'boolean'
          ? envelope.fallback_used
          : undefined,
      fallback_reason: envelope.fallback_reason,
      latency_ms:
        typeof envelope.latency_ms === 'number' ? envelope.latency_ms : undefined,
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
          : undefined,
      output_schema:
        item.output_schema && typeof item.output_schema === 'object'
          ? (item.output_schema as Record<string, unknown>)
          : undefined,
      supported_tasks: Array.isArray(item.supported_tasks)
        ? item.supported_tasks.map((task) => String(task))
        : undefined,
    };
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
}
