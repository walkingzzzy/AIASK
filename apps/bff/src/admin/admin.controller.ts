import { Body, ConflictException, Controller, Get, Param, Post, UseGuards, UseInterceptors } from '@nestjs/common';
import { AdminService } from './admin.service';
import { AuthGuard } from '../rbac/auth.guard';
import { Roles } from '../rbac/roles.decorator';
import { AuditInterceptor } from '../audit/audit.interceptor';

@Controller('admin')
@UseGuards(AuthGuard)
@UseInterceptors(AuditInterceptor)
@Roles('admin')
export class AdminController {
  constructor(private readonly adminService: AdminService) {}

  @Get('mcp-stats')
  async getMcpStats() {
    const data = await this.adminService.getMcpStats();
    return { success: true, data };
  }

  @Get('cache-stats')
  async getCacheStats() {
    const data = await this.adminService.getCacheStats();
    return { success: true, data };
  }

  @Post('cache/clear')
  async clearCache(@Body() body: { prefix?: string }) {
    const data = await this.adminService.clearCache(body?.prefix);
    return { success: true, data };
  }

  @Get('dead-letters')
  async getDeadLetters() {
    const result = await this.adminService.getDeadLetters();
    return { success: true, data: result.items, items: result.items, path: result.path, count: result.count };
  }

  @Post('dead-letters/clear')
  async clearDeadLetters() {
    const data = await this.adminService.clearDeadLetters();
    return { success: true, data };
  }

  @Post('dead-letters/seed')
  async seedDeadLetters(@Body() body: { count?: number }) {
    const data = await this.adminService.seedDeadLetters(body?.count);
    return { success: true, data };
  }

  @Post('dead-letters/:id/retry')
  async retryDeadLetter(@Param('id') id: string) {
    const data = await this.adminService.retryDeadLetter(id);
    if (!data.success) {
      throw new ConflictException(data.message);
    }
    return { success: true, data };
  }

  @Get('users')
  async listUsers() {
    const items = await this.adminService.listUsers();
    return { success: true, data: { items }, items };
  }
}
