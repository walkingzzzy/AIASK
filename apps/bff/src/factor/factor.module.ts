import { Module } from '@nestjs/common';
import { FactorController } from './factor.controller';
import { FactorService } from './factor.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [FactorController],
  providers: [FactorService],
})
export class FactorModule {}
