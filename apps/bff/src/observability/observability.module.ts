import { Global, Module } from '@nestjs/common';
import { ObservabilityController } from './observability.controller';
import { ObservabilityInterceptor } from './observability.interceptor';
import { ObservabilityService } from './observability.service';

@Global()
@Module({
  controllers: [ObservabilityController],
  providers: [ObservabilityService, ObservabilityInterceptor],
  exports: [ObservabilityService, ObservabilityInterceptor],
})
export class ObservabilityModule {}
