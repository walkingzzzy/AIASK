import { Module } from '@nestjs/common';
import { DataController } from './data.controller';
import { DataService } from './data.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [DataController],
  providers: [DataService],
})
export class DataModule {}
