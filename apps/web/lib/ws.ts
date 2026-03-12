'use client';

import { useEffect, useRef, useCallback, useState, useMemo, createContext, useContext } from 'react';
import { io, Socket } from 'socket.io-client';

const WS_URL = (() => {
  const direct = process.env.NEXT_PUBLIC_WS_URL;
  if (direct) return direct;
  const bffBase = process.env.NEXT_PUBLIC_BFF_BASE_URL;
  if (bffBase) {
    try {
      const u = new URL(bffBase);
      return `${u.protocol}//${u.host}`;
    } catch { /* ignore */ }
  }
  return 'http://localhost:3001';
})();


// ── 连接状态类型 ─────────────────────────────────────────────

export type WsConnectionStatus = 'connected' | 'connecting' | 'disconnected';

// ── 单例连接管理 ─────────────────────────────────────────────

let _socket: Socket | null = null;
let _refCount = 0;
let _statusListeners = new Set<(s: WsConnectionStatus) => void>();

function notifyStatus(status: WsConnectionStatus) {
  _statusListeners.forEach((fn) => fn(status));
}

function getSocket(): Socket {
  if (!_socket) {
    _socket = io(`${WS_URL}/ws`, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 10000,
      autoConnect: false,
    });
    _socket.on('connect', () => notifyStatus('connected'));
    _socket.on('disconnect', () => notifyStatus('disconnected'));
    _socket.io.on('reconnect_attempt', () => notifyStatus('connecting'));
  }
  return _socket;
}

function acquireSocket(): Socket {
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
  if (_refCount === 0 && _socket) {
    _socket.disconnect();
    _socket = null;
    notifyStatus('disconnected');
  }
}

// ── 基础 Hook ────────────────────────────────────────────────

type WsEvent = string;
type WsHandler = (data: unknown) => void;

interface UseWebSocketOptions {
  /** 连接后立即发送的订阅消息 */
  subscribe?: { event: string; payload: Record<string, unknown> };
  /** 监听的事件列表 */
  events?: Record<WsEvent, WsHandler>;
}

interface UseWebSocketReturn {
  connected: boolean;
  emit: (event: string, data: unknown) => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const emit = useCallback((event: string, data: unknown) => {
    socketRef.current?.emit(event, data);
  }, []);

  return { connected, emit };
}

// ── 连接状态 Hook ────────────────────────────────────────────

/** 获取全局 WebSocket 连接状态 */
export function useWsStatus(): WsConnectionStatus {
  const [status, setStatus] = useState<WsConnectionStatus>(
    _socket?.connected ? 'connected' : 'disconnected',
  );
  useEffect(() => {
    _statusListeners.add(setStatus);
    return () => { _statusListeners.delete(setStatus); };
  }, []);
  return status;
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
  cbRef.current = { onUpdate, onBatch };

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

    const changed = !prev
      || prev.type !== type
      || prev.codes.length !== normalizedCodes.length
      || prev.codes.some((code, index) => code !== normalizedCodes[index]);

    if (!changed) return;

    if (prev) {
      emit('unsubscribe:quote', { codes: prev.codes, type: prev.type });
    }

    emit('subscribe:quote', { codes: normalizedCodes, type });
    activeSubRef.current = { codes: normalizedCodes, type };
  }, [connected, emit, enabled, normalizedCodes, type]);

  useEffect(() => () => {
    const prev = activeSubRef.current;
    if (prev) {
      emit('unsubscribe:quote', { codes: prev.codes, type: prev.type });
      activeSubRef.current = null;
    }
  }, [emit]);

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
}

export function useAlertSubscription(options: UseAlertSubscriptionOptions = {}) {
  const { userId, onAlert, onWarn } = options;
  const cbRef = useRef({ onAlert, onWarn });
  cbRef.current = { onAlert, onWarn };

  return useWebSocket({
    subscribe: {
      event: 'subscribe:alert',
      payload: { userId },
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
  accountId: string;
  onUpdate?: (data: TradeUpdateData) => void;
}

export function useTradeSubscription(options: UseTradeSubscriptionOptions) {
  const { accountId, onUpdate } = options;
  const cbRef = useRef({ onUpdate });
  cbRef.current = { onUpdate };

  return useWebSocket({
    subscribe: {
      event: 'subscribe:trade',
      payload: { accountId },
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
  cbRef.current = onMessage;

  return useWebSocket({
    events: {
      'system:message': (data) => cbRef.current?.(data as SystemMessage),
    },
  });
}

