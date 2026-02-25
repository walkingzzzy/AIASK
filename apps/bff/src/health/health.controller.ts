import { Controller, Get } from '@nestjs/common';
import { HealthService } from './health.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { Public } from '../rbac/public.decorator';
import { CommonCacheService } from '../common/cache.service';

@Controller('health')
export class HealthController {
  constructor(
    private readonly healthService: HealthService,
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  @Public()
  @Get()
  getHealth() {
    return this.healthService.getHealth();
  }

  @Public()
  @Get('mcp')
  async getMcpHealth() {
    const base = this.healthService.getHealth();
    const mcp = await this.mcpGatewayService.checkAvailableTools();

    return {
      success: true,
      data: { ...base, mcp },
    };
  }

  @Public()
  @Get('cache')
  getCacheHealth() {
    const base = this.healthService.getHealth();
    return {
      ...base,
      cache: this.cacheService.getStats(),
    };
  }
}

