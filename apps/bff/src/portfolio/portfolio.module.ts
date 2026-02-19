import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { PortfolioController } from './portfolio.controller';
import { PortfolioService } from './portfolio.service';

@Module({
  imports: [McpGatewayModule],
  controllers: [PortfolioController],
  providers: [PortfolioService],
})
export class PortfolioModule {}

