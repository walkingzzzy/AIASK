import { Body, Controller, Get, Param, Post, Req, UseGuards, UseInterceptors } from '@nestjs/common';
import { SkillsService } from './skills.service';
import { AuthGuard } from '../rbac/auth.guard';
import { AuditInterceptor } from '../audit/audit.interceptor';

@Controller('v1/skills')
@UseGuards(AuthGuard)
@UseInterceptors(AuditInterceptor)
export class SkillsController {
    constructor(private readonly skillsService: SkillsService) { }

    @Get()
    async listSkills() {
        return this.skillsService.listSkills();
    }

    @Post(':skillName/trigger')
    async triggerSkill(
        @Param('skillName') skillName: string,
        @Body() payload: Record<string, any>,
        @Req() req: any
    ) {
        const userId = req.user?.id || 'default';
        return this.skillsService.triggerSkill(skillName, payload, userId);
    }
}
