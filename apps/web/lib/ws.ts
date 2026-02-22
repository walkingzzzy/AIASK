'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { io, Socket } from 'socket.io-client';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || '';

// ── 单例连接管理 ─────────────────────────────────────────────

let _socket: Socket | null = null;
let _refCount = 0;

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
  }
  return _socket;
}

function acquireSocket(): Socket {
  const s = getSocket();
  _refCount++;
  if (!s.connected && !s.active) s.connect();
  return s;
}

function releaseSocket() {
  _refCount = Math.max(0, _refCount - 1);
  if (_refCount === 0 && _socket) {
    _socket.disconnect();
    _socket = null;
  }
}

// ── React Hook ───────────────────────────────────────────────

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
