import { Module } from '@nestjs/common';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import { PreferencesService } from './preferences.service';
import { TotpService } from './totp.service';
import { DbModule } from '../db/db.module';

@Module({
  imports: [DbModule],
  controllers: [AuthController],
  providers: [AuthService, PreferencesService, TotpService],
  exports: [AuthService, PreferencesService],
})
export class AuthModule {}

