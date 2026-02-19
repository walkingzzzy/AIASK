import { Module } from '@nestjs/common';
import { TdxController } from './tdx.controller';
import { TdxService } from './tdx.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [TdxController],
  providers: [TdxService],
})
export class TdxModule {}
