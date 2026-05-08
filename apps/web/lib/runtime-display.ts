export type RealtimeDisplayStatus = 'connected' | 'idle' | 'reconnecting' | 'offline';
export type ReachabilityStatus = 'unknown' | 'checking' | 'online' | 'offline';
export type NotificationAcceptanceStatus = 'unavailable' | 'prerequisite_missing' | 'degraded' | null;
export type NotificationTrustStatus = 'trusted' | 'degraded' | 'partial' | 'conflict' | 'empty' | 'unavailable' | 'unknown';
export type NotificationFeedState = 'ready' | 'empty' | 'unavailable' | 'degraded';

export function resolveRealtimeDisplayStatus(
  transportStatus: RealtimeDisplayStatus,
  reachabilityStatus: ReachabilityStatus | string,
): RealtimeDisplayStatus {
  if (reachabilityStatus === 'offline') {
    return 'offline';
  }
  if (reachabilityStatus === 'checking' && transportStatus === 'connected') {
    return 'reconnecting';
  }
  return transportStatus;
}

export function resolveNotificationFeedState(input: {
  enabled: boolean;
  itemsLength: number;
  acceptanceStatus: NotificationAcceptanceStatus;
  serviceUnavailable: boolean;
  trustStatus: NotificationTrustStatus;
  reachabilityStatus: ReachabilityStatus | string;
}): NotificationFeedState {
  const { enabled, itemsLength, acceptanceStatus, serviceUnavailable, trustStatus, reachabilityStatus } = input;

  if (!enabled) {
    return 'unavailable';
  }

  if (
    serviceUnavailable
    || acceptanceStatus === 'unavailable'
    || reachabilityStatus === 'offline'
  ) {
    return 'unavailable';
  }

  if (
    acceptanceStatus === 'degraded'
    || acceptanceStatus === 'prerequisite_missing'
    || trustStatus === 'degraded'
    || trustStatus === 'partial'
    || trustStatus === 'conflict'
    || trustStatus === 'unavailable'
  ) {
    return 'degraded';
  }

  return itemsLength > 0 ? 'ready' : 'empty';
}
