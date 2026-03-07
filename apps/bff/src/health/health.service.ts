import { Injectable } from '@nestjs/common';
import { DbService } from '../db/db.service';

@Injectable()
export class HealthService {
  constructor(private readonly db: DbService) { }

  getHealth() {
    return {
      success: true,
      service: 'aiask-bff',
      status: 'ok',
      db: {
        enabled: this.db.enabled,
        healthy: this.db.healthy,
      },
      timestamp: new Date().toISOString(),
    };
  }

  async getDbHealth() {
    const base = {
      enabled: this.db.enabled,
      healthy: this.db.healthy,
    };

    if (!this.db.enabled) {
      return { success: true, data: { ...base, mode: 'memory' } };
    }

    // 实时连通性探测
    let reachable = false;
    let latencyMs = -1;
    try {
      const start = Date.now();
      await this.db.query('SELECT 1');
      latencyMs = Date.now() - start;
      reachable = true;
    } catch {
      reachable = false;
    }

    return {
      success: true,
      data: {
        ...base,
        reachable,
        latencyMs,
        mode: 'postgres',
      },
    };
  }
}


