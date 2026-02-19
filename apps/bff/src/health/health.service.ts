import { Injectable } from '@nestjs/common';

@Injectable()
export class HealthService {
  getHealth() {
    return {
      success: true,
      service: 'aiask-bff',
      status: 'ok',
      timestamp: new Date().toISOString(),
    };
  }
}

