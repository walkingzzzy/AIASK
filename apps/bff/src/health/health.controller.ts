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
    return this.healthService.getLivenessSnapshot();
  }

  @Public()
  @Get('mcp')
  async getMcpHealth() {
    return this.healthService.getMcpHealthSnapshot();
  }

  @Public()
  @Get('ready')
  async getReadyHealth() {
    const base = await this.healthService.getHealth();
    const ready = base.probes.readiness !== 'blocked';
    const payload = { success: ready, data: base };

    if (!ready) {
      throw new ServiceUnavailableException(payload);
    }

    return payload;
  }

  @Public()
  @Get('startup')
  async getStartupHealth() {
    const base = await this.healthService.getHealth();
    const started = base.probes.startup === 'complete';
    const payload = {
      success: started,
      data: {
        service: base.service,
        status: started ? 'normal' : 'starting',
        probe: 'startup',
        startedAt: base.startedAt,
        timestamp: base.timestamp,
      },
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
