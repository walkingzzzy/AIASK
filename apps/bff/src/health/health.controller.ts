import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
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
  ) { }

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
  @Get('ready')
  async getReadyHealth() {
    const base = this.healthService.getHealth();
    const mcp = await this.mcpGatewayService.checkAvailableTools();
    const dbReady = !base.db.enabled || base.db.healthy;
    const ready = dbReady && mcp.reachable;
    const payload = { success: ready, data: { ...base, mcp } };

    if (!ready) {
      throw new ServiceUnavailableException(payload);
    }

    return payload;
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

  @Public()
  @Get('db')
  async getDbHealth() {
    return this.healthService.getDbHealth();
  }
}
