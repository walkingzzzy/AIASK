import { Global, Module } from '@nestjs/common';
import { HealthModule } from '../health/health.module';
import { ObservabilityController } from './observability.controller';
import { ObservabilityInterceptor } from './observability.interceptor';
import { ObservabilityService } from './observability.service';

@Global()
@Module({
  imports: [HealthModule],
  controllers: [ObservabilityController],
  providers: [ObservabilityService, ObservabilityInterceptor],
  exports: [ObservabilityService, ObservabilityInterceptor],
})
export class ObservabilityModule {}
