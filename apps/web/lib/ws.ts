'use client';

import { useEffect, useRef, useCallback, useState, useMemo, useSyncExternalStore } from 'react';
import { io, Socket } from 'socket.io-client';
import { useBffAvailability } from './bff-availability';
import { getBffOrigin, getRuntimeWsUrl } from './bff-base';

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1']);

function resolveWsUrl() {
  const runtimeConfigured = getRuntimeWsUrl();
  if (runtimeConfigured) {
    try {
      return new URL(runtimeConfigured).origin;
    } catch {
      return getBffOrigin();
    }
  }

  const direct = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (!direct) return getBffOrigin();
  if (typeof window === 'undefined') return direct;

  try {
    const parsed = new URL(direct);
    if (LOOPBACK_HOSTS.has(parsed.hostname) && LOOPBACK_HOSTS.has(window.location.hostname)) {
      parsed.hostname = window.location.hostname;
      return parsed.origin;
    }
    return parsed.origin;
  } catch {
    return getBffOrigin();
  }
}

// ── 连接状态类型 ─────────────────────────────────────────────

export type WsConnectionStatus = 'connected' | 'connecting' | 'disconnected';

// ── 单例连接管理 ─────────────────────────────────────────────

let _socket: Socket | null = null;
let _refCount = 0;
let _status: WsConnectionStatus = 'disconnected';
let _statusListeners = new Set<(s: WsConnectionStatus) => void>();
let _releaseTimer: ReturnType<typeof setTimeout> | null = null;

const SOCKET_RELEASE_GRACE_MS = 1500;

function notifyStatus(status: WsConnectionStatus) {
  _status = status;
  _statusListeners.forEach((fn) => fn(status));
}

function getSocket(): Socket {
  if (!_socket) {
    const transports = ['websocket', 'polling'];
    _socket = io(`${resolveWsUrl()}/ws`, {
      transports,
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: process.env.NODE_ENV === 'production' ? Infinity : 2,
      reconnectionDelay: 1000,
      reconnectionDelayMax: process.env.NODE_ENV === 'production' ? 10000 : 3000,
      autoConnect: false,
    });
    _socket.on('connect', () => notifyStatus('connected'));
    _socket.on('disconnect', () => notifyStatus('disconnected'));
    _socket.io.on('reconnect_attempt', () => notifyStatus('connecting'));
  }
  return _socket;
}

function acquireSocket(): Socket {
  if (_releaseTimer) {
    clearTimeout(_releaseTimer);
    _releaseTimer = null;
  }

  const s = getSocket();
  _refCount++;
  if (!s.connected && !s.active) {
    notifyStatus('connecting');
    s.connect();
  }
  return s;
}

function releaseSocket() {
  _refCount = Math.max(0, _refCount - 1);
  if (_refCount > 0 || !_socket || _releaseTimer) return;

  _releaseTimer = setTimeout(() => {
    _releaseTimer = null;
    if (_refCount !== 0 || !_socket) return;

    _socket.disconnect();
    _socket = null;
    notifyStatus('disconnected');
  }, SOCKET_RELEASE_GRACE_MS);
}

// ── 基础 Hook ────────────────────────────────────────────────

type WsEvent = string;
type WsHandler = (data: unknown) => void;

interface UseWebSocketOptions {
  /** 连接后立即发送的订阅消息 */
  subscribe?: { event: string; payload: Record<string, unknown> };
  /** 监听的事件列表 */
  events?: Record<WsEvent, WsHandler>;
  /** 是否启用连接，默认 true */
  enabled?: boolean;
}

interface UseWebSocketReturn {
  connected: boolean;
  emit: (event: string, data: unknown) => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  const optionsRef = useRef(options);
  const enabled = options.enabled ?? true;
  const bffAvailability = useBffAvailability({ probeOnMount: enabled });
  const canConnect = enabled && bffAvailability.reachable;
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  useEffect(() => {
    if (!canConnect) {
      if (bffAvailability.unavailable) notifyStatus('disconnected');
      return;
    }

    const socket = acquireSocket();
    socketRef.current = socket;

    const onConnect = () => {
      setConnected(true);
      const sub = optionsRef.current.subscribe;
      if (sub) socket.emit(sub.event, sub.payload);
    };

    const onDisconnect = () => setConnected(false);

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);

    // 如果已经连接，立即触发订阅
    if (socket.connected) onConnect();

    // 注册事件监听
    const events = optionsRef.current.events || {};
    for (const [evt, handler] of Object.entries(events)) {
      socket.on(evt, handler);
    }

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      for (const [evt, handler] of Object.entries(events)) {
        socket.off(evt, handler);
      }
      socketRef.current = null;
      releaseSocket();
    };
  }, [bffAvailability.unavailable, canConnect]);

  const emit = useCallback((event: string, data: unknown) => {
    socketRef.current?.emit(event, data);
  }, []);

  return { connected: canConnect ? connected : false, emit };
}

// ── 连接状态 Hook ────────────────────────────────────────────

/** 获取全局 WebSocket 连接状态 */
export function useWsStatus(): WsConnectionStatus {
  return useSyncExternalStore(
    (onStoreChange) => {
      const listener = () => onStoreChange();
      _statusListeners.add(listener);
      return () => {
        _statusListeners.delete(listener);
      };
    },
    () => _status,
    () => 'disconnected',
  );
}

// ── 行情订阅 Hook ────────────────────────────────────────────

export interface QuoteData {
  code: string;
  type: string;
  price?: number;
  change?: number;
  changePercent?: number;
  volume?: number;
  [key: string]: unknown;
}

interface UseQuoteSubscriptionOptions {
  /** 订阅的股票/指数代码，空数组则订阅全局广播 */
  codes?: string[];
  /** 类型: 'stock' | 'index' */
  type?: 'stock' | 'index';
  /** 是否启用订阅，默认 true */
  enabled?: boolean;
  /** 收到行情更新时的回调 */
  onUpdate?: (data: QuoteData) => void;
  /** 收到批量行情时的回调 */
  onBatch?: (items: QuoteData[]) => void;
}

export function useQuoteSubscription(options: UseQuoteSubscriptionOptions = {}) {
  const { codes = [], type = 'stock', enabled = true, onUpdate, onBatch } = options;
  const cbRef = useRef({ onUpdate, onBatch });
  const activeSubRef = useRef<{ codes: string[]; type: 'stock' | 'index' } | null>(null);
  useEffect(() => {
    cbRef.current = { onUpdate, onBatch };
  }, [onBatch, onUpdate]);

  const normalizedCodes = useMemo(
    () => Array.from(new Set(codes.map((code) => String(code).trim()).filter(Boolean))),
    [codes],
  );

  const socket = useWebSocket({
    events: {
      'quote:update': (data) => cbRef.current.onUpdate?.(data as QuoteData),
      'quote:batch': (data) => {
        const payload = data as { items?: QuoteData[] };
        if (payload.items) cbRef.current.onBatch?.(payload.items);
      },
    },
  });
  const { connected, emit } = socket;

  useEffect(() => {
    const prev = activeSubRef.current;

    if (!enabled || !connected) {
      if (prev) {
        emit('unsubscribe:quote', { codes: prev.codes, type: prev.type });
        activeSubRef.current = null;
      }
      return;
    }

    const changed =
      !prev ||
      prev.type !== type ||
      prev.codes.length !== normalizedCodes.length ||
      prev.codes.some((code, index) => code !== normalizedCodes[index]);

    if (!changed) return;

    if (prev) {
      emit('unsubscribe:quote', { codes: prev.codes, type: prev.type });
    }

    emit('subscribe:quote', { codes: normalizedCodes, type });
    activeSubRef.current = { codes: normalizedCodes, type };
  }, [connected, emit, enabled, normalizedCodes, type]);

  useEffect(
    () => () => {
      const prev = activeSubRef.current;
      if (prev) {
        emit('unsubscribe:quote', { codes: prev.codes, type: prev.type });
        activeSubRef.current = null;
      }
    },
    [emit],
  );

  return socket;
}

// ── 告警订阅 Hook ────────────────────────────────────────────

interface AlertData {
  message?: string;
  level?: 'info' | 'warn' | 'error';
  code?: string;
  indicator?: string;
  ts?: string;
  [key: string]: unknown;
}

interface UseAlertSubscriptionOptions {
  userId?: string;
  onAlert?: (data: AlertData) => void;
  onWarn?: (data: AlertData) => void;
  enabled?: boolean;
}

export function useAlertSubscription(options: UseAlertSubscriptionOptions = {}) {
  const { onAlert, onWarn, enabled = true } = options;
  const cbRef = useRef({ onAlert, onWarn });
  useEffect(() => {
    cbRef.current = { onAlert, onWarn };
  }, [onAlert, onWarn]);

  return useWebSocket({
    enabled,
    subscribe: {
      event: 'subscribe:alert',
      payload: {},
    },
    events: {
      'alert:triggered': (data) => cbRef.current.onAlert?.(data as AlertData),
      'alert:warn': (data) => cbRef.current.onWarn?.(data as AlertData),
    },
  });
}

// ── 交易订单订阅 Hook ────────────────────────────────────────

interface TradeUpdateData {
  orderId?: string;
  status?: string;
  filledQty?: number;
  filledPrice?: number;
  ts?: string;
  [key: string]: unknown;
}

interface UseTradeSubscriptionOptions {
  accountId?: string;
  onUpdate?: (data: TradeUpdateData) => void;
  enabled?: boolean;
}

export function useTradeSubscription(options: UseTradeSubscriptionOptions) {
  const { accountId, onUpdate, enabled = true } = options;
  const cbRef = useRef({ onUpdate });
  useEffect(() => {
    cbRef.current = { onUpdate };
  }, [onUpdate]);
  const normalizedAccountId = accountId && accountId !== 'default' ? accountId : undefined;

  return useWebSocket({
    enabled,
    subscribe: {
      event: 'subscribe:trade',
      payload: normalizedAccountId ? { accountId: normalizedAccountId } : {},
    },
    events: {
      'trade:update': (data) => cbRef.current.onUpdate?.(data as TradeUpdateData),
    },
  });
}

// ── 系统消息 Hook ────────────────────────────────────────────

interface SystemMessage {
  message: string;
  level: 'info' | 'warn' | 'error';
  ts: string;
}

export function useSystemMessages(onMessage?: (msg: SystemMessage) => void) {
  const cbRef = useRef(onMessage);
  useEffect(() => {
    cbRef.current = onMessage;
  }, [onMessage]);

  return useWebSocket({
    events: {
      'system:message': (data) => cbRef.current?.(data as SystemMessage),
    },
  });
}
