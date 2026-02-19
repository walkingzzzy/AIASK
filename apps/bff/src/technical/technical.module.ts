import { Module } from '@nestjs/common';
import { TechnicalController } from './technical.controller';
import { TechnicalService } from './technical.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [TechnicalController],
  providers: [TechnicalService],
})
export class TechnicalModule {}
