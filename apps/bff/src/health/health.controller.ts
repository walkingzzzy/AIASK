import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { HealthService } from './health.service';
import { Public } from '../rbac/public.decorator';

@Controller('health')
export class HealthController {
  constructor(private readonly healthService: HealthService) { }

  @Public()
  @Get()
  async getHealth() {
    return this.healthService.getHealth();
  }

  @Public()
  @Get('live')
  async getLiveness() {
    return {
      success: true,
      data: this.healthService.getLivenessProbe(),
    };
  }

  @Public()
  @Get('mcp')
  async getMcpHealth() {
    const base = await this.healthService.getHealth();
    return {
      service: base.service,
      status: base.mcp.status,
      signal: base.mcp.signal,
      reasons: base.mcp.reasons,
      mcp: base.mcp,
      timestamp: base.timestamp,
    };
  }

  @Public()
  @Get('ready')
  async getReadyHealth() {
    const base = await this.healthService.getHealth();
    const ready = base.probes.readiness === 'ready';
    const payload = { success: ready, data: base };

    if (!ready) {
      throw new ServiceUnavailableException(payload);
    }

    return payload;
  }

  @Public()
  @Get('startup')
  async getStartupHealth() {
    const data = this.healthService.getStartupProbe();
    const started = data.status === 'normal';
    const payload = {
      success: started,
      data,
    };

    if (!started) {
      throw new ServiceUnavailableException(payload);
    }

    return payload;
  }

  @Public()
  @Get('cache')
  async getCacheHealth() {
    const base = await this.healthService.getHealth();
    return {
      service: base.service,
      status: base.cache.status,
      signal: base.cache.signal,
      reasons: base.cache.reasons,
      cache: base.cache,
      timestamp: base.timestamp,
    };
  }

  @Public()
  @Get('db')
  async getDbHealth() {
    return this.healthService.getDbHealth();
  }
}
