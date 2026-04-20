import { Module } from '@nestjs/common';
import { CommonCacheModule } from '../common/cache.module';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { McpJobsController } from './mcp-jobs.controller';
import { McpJobsService } from './mcp-jobs.service';

@Module({
  imports: [CommonCacheModule, McpGatewayModule],
  controllers: [McpJobsController],
  providers: [McpJobsService],
  exports: [McpJobsService],
})
export class McpJobsModule {}
