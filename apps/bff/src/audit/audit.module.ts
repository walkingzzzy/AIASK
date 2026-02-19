import { Module } from '@nestjs/common';
import { AuditStore } from './audit.store';
import { AuditController } from './audit.controller';

@Module({
  controllers: [AuditController],
  providers: [AuditStore],
  exports: [AuditStore],
})
export class AuditModule {}

