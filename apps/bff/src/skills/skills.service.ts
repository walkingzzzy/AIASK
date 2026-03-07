import { BadGatewayException, Injectable, Logger } from '@nestjs/common';
import * as fs from 'fs';
import * as path from 'path';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class SkillsService {
    private readonly logger = new Logger(SkillsService.name);
    private readonly skillsDir: string;

    constructor(private readonly mcp: McpGatewayService) {
        // Navigate up from apps/bff/dist/src/skills to root /.codex/skills
        this.skillsDir = path.resolve(process.cwd(), '../../.codex/skills');
    }

    async listSkills() {
        try {
            if (!fs.existsSync(this.skillsDir)) {
                return { data: [] };
            }
            const dirs = fs.readdirSync(this.skillsDir, { withFileTypes: true })
                .filter(dirent => dirent.isDirectory())
                .map(dirent => dirent.name);
            return { data: dirs };
        } catch (error) {
            this.logger.error(`Failed to list skills: ${error}`);
            return { data: [] };
        }
    }

    async triggerSkill(skillName: string, payload: Record<string, any>, userId: string) {
        const skillPath = path.join(this.skillsDir, skillName, 'SKILL.md');

        if (!fs.existsSync(skillPath)) {
            throw new BadGatewayException({
                success: false,
                message: `找不到对应的 Skill: ${skillName}`,
            });
        }

        try {
            const result = await this.mcp.callTool('run_skill', {
                skill_id: skillName,
                params: payload ?? {},
            });

            return {
                success: true,
                message: `Skill ${skillName} 执行完成`,
                result,
            };
        } catch (error) {
            throw new BadGatewayException({
                success: false,
                message: `触发 Skill ${skillName} 失败`,
                detail: String(error instanceof Error ? error.message : error),
            });
        }
    }
}
