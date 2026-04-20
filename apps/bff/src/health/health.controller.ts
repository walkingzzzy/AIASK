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
    const base = await this.healthService.getHealth();
    return {
      success: true,
      data: {
        service: base.service,
        status: 'ok',
        probe: 'liveness',
        startedAt: base.startedAt,
        timestamp: base.timestamp,
      },
    };
  }

  @Public()
  @Get('mcp')
  async getMcpHealth() {
    const base = await this.healthService.getHealth();
    return {
      success: true,
      data: { ...base, mcp: base.mcp },
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
    const base = await this.healthService.getHealth();
    const started = base.probes.startup === 'complete';
    const payload = {
      success: started,
      data: {
        service: base.service,
        status: started ? 'ok' : 'starting',
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
      ...base,
      cache: base.cache,
    };
  }

  @Public()
  @Get('db')
  async getDbHealth() {
    return this.healthService.getDbHealth();
  }
}
