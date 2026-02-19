import {
  CallHandler,
  ExecutionContext,
  Injectable,
  Logger,
  NestInterceptor,
} from '@nestjs/common';
import { Observable, tap } from 'rxjs';
import { AuditStore } from './audit.store';

type RequestUser = {
  id: string;
  username: string;
  role: 'admin' | 'user';
};

@Injectable()
export class AuditInterceptor implements NestInterceptor {
  private readonly logger = new Logger('Audit');

  constructor(private readonly auditStore: AuditStore) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const now = Date.now();
    const http = context.switchToHttp();
    const request = http.getRequest<{
      method?: string;
      url?: string;
      headers?: Record<string, string | undefined>;
      user?: RequestUser;
      traceId?: string;
    }>();
    const response = http.getResponse<{
      statusCode?: number;
      setHeader?: (name: string, value: string) => void;
    }>();

    const traceId =
      request.headers?.['x-trace-id'] ||
      request.headers?.['x-request-id'] ||
      `trace_${Math.random().toString(36).slice(2, 10)}`;

    request.traceId = String(traceId);

    if (typeof response.setHeader === 'function') {
      response.setHeader('x-trace-id', String(traceId));
    }

    return next.handle().pipe(
      tap({
        next: () => {
          const duration = Date.now() - now;
          const entry = {
            trace_id: String(traceId),
            method: request.method ?? 'UNKNOWN',
            path: request.url ?? 'UNKNOWN',
            status: response.statusCode ?? 200,
            duration_ms: duration,
            user: request.user
              ? {
                  id: request.user.id,
                  username: request.user.username,
                  role: request.user.role,
                }
              : null,
            ts: new Date().toISOString(),
          };

          this.auditStore.append(entry);
          this.logger.log(JSON.stringify(entry));
        },
      }),
    );
  }
}

