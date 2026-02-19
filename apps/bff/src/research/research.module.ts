import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { ResearchController } from './research.controller';
import { ResearchService } from './research.service';

@Module({
  imports: [McpGatewayModule],
  controllers: [ResearchController],
  providers: [ResearchService],
})
export class ResearchModule {}

