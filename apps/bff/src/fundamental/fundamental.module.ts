import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { FundamentalController } from './fundamental.controller';
import { FundamentalService } from './fundamental.service';

@Module({
  imports: [McpGatewayModule],
  controllers: [FundamentalController],
  providers: [FundamentalService],
})
export class FundamentalModule {}

