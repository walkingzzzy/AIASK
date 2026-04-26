import { Badge, SectionCard } from '@/components/ui';
import { paperTradingNoteCardCls } from '@/app/paper-trading/components/paper-trading-panel-styles';
import type {
  PaperTradingTrustReconcileItem,
  PaperTradingTrustState,
  PaperTradingTrustStatus,
  PaperTradingTrustTimestamp,
} from '@aiask/shared-types';

type PaperTradingTrustStatusProps = {
  status: PaperTradingTrustStatus;
};

function badgeVariant(state: PaperTradingTrustState | undefined) {
  if (state === 'blocked') return 'danger' as const;
  if (state === 'warning') return 'warning' as const;
  return 'success' as const;
}

function levelVariant(level: PaperTradingTrustStatus['level']) {
  if (level === 'blocked') return 'danger' as const;
  if (level === 'caution') return 'warning' as const;
  return 'success' as const;
}

function formatStatusTime(value: string | null | undefined) {
  if (!value) return '暂无';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatAge(ageSeconds: number | null | undefined) {
  if (ageSeconds == null || !Number.isFinite(ageSeconds)) return null;
  if (ageSeconds < 60) return `距今 ${ageSeconds} 秒`;
  if (ageSeconds < 3600) return `距今 ${Math.round(ageSeconds / 60)} 分钟`;
  return `距今 ${Math.round(ageSeconds / 3600)} 小时`;
}

function TimestampTile({
  label,
  payload,
}: {
  label: string;
  payload: PaperTradingTrustTimestamp | null | undefined;
}) {
  return (
    <div className={paperTradingNoteCardCls}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{label}</span>
        <Badge variant={badgeVariant(payload?.status)}>{payload?.fresh === false ? '待刷新' : '正常'}</Badge>
      </div>
      <div className="mt-3 text-sm font-semibold text-text-primary">{formatStatusTime(payload?.at)}</div>
      <div className="mt-1 text-[11px] text-text-secondary">{formatAge(payload?.age_seconds) ?? '时间戳待补齐'}</div>
      <div className="mt-3 text-xs leading-6 text-text-secondary">{payload?.detail ?? '暂无说明'}</div>
    </div>
  );
}

function ReconcileTile({
  label,
  payload,
}: {
  label: string;
  payload: PaperTradingTrustReconcileItem | null | undefined;
}) {
  return (
    <div className={paperTradingNoteCardCls}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{label}</span>
        <Badge variant={badgeVariant(payload?.status)}>{payload?.reconciled ? '已 reconcile' : '未就绪'}</Badge>
      </div>
      <div className="mt-3 text-sm font-semibold text-text-primary">
        {payload?.reconciled ? '当前快照可用' : '当前快照需复核'}
      </div>
      <div className="mt-3 text-xs leading-6 text-text-secondary">{payload?.detail ?? '暂无说明'}</div>
      {payload?.reference_at ? (
        <div className="mt-2 text-[11px] text-text-secondary">参考时间 {formatStatusTime(payload.reference_at)}</div>
      ) : null}
    </div>
  );
}

export default function PaperTradingTrustStatusCard({ status }: PaperTradingTrustStatusProps) {
  const topLabel =
    status.level === 'ready'
      ? '最新 + 可演示'
      : status.level === 'caution'
        ? '链路最新，演示需提示 NAV 口径'
        : '当前不建议直接演示';

  return (
    <SectionCard className="mb-4 p-4 sm:p-5">
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.08fr)_minmax(340px,0.92fr)]">
        <div>
          <div className="eyebrow">Trust Gate</div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant={status.latest ? 'success' : 'warning'}>
              {status.latest ? '数据最新' : '数据待刷新'}
            </Badge>
            <Badge variant={levelVariant(status.level)}>
              {status.demo_ready ? (status.level === 'caution' ? '谨慎演示' : '可演示') : '暂不演示'}
            </Badge>
            <Badge variant={status.environment?.dry_run ? 'warning' : 'info'}>
              {status.environment?.dry_run ? 'dry-run' : status.environment?.label ?? '环境待确认'}
            </Badge>
            <Badge variant={status.market_phase === 'trading' ? 'warning' : 'neutral'}>
              {status.market_phase === 'trading' ? '交易时段' : '非交易时段'}
            </Badge>
          </div>
          <h3 className="mb-0 mt-4 text-xl font-semibold text-text-primary">{status.headline ?? topLabel}</h3>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            {topLabel}。这张卡把撮合扫描、价格刷新、NAV 快照、持仓/订单/NAV reconcile 和环境口径收在一起，避免用户自己拼时间线。
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <TimestampTile label="撮合时间" payload={status.timestamps?.matching} />
            <TimestampTile label="价格刷新" payload={status.timestamps?.prices} />
            <TimestampTile label="NAV 快照" payload={status.timestamps?.nav} />
          </div>
        </div>

        <div className="grid gap-3">
          <ReconcileTile label="持仓" payload={status.reconcile?.positions} />
          <ReconcileTile label="订单" payload={status.reconcile?.orders} />
          <ReconcileTile label="NAV" payload={status.reconcile?.nav} />
          <div className={paperTradingNoteCardCls}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">一眼判断</span>
              <Badge variant={levelVariant(status.level)}>{status.level === 'ready' ? '绿灯' : status.level === 'caution' ? '黄灯' : '红灯'}</Badge>
            </div>
            <div className="mt-3 text-sm font-semibold text-text-primary">
              {status.latest ? '先看“数据最新”' : '顶部不是“数据最新”，先刷新'}
            </div>
            <div className="mt-3 space-y-2 text-xs leading-6 text-text-secondary">
              {(status.reasons?.length ? status.reasons : ['没有额外阻塞项']).slice(0, 4).map((reason) => (
                <div key={reason}>{reason}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
