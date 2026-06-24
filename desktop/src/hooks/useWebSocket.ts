/**
 * WebSocket Hook - 实时事件流
 * 用于 Runs 事件、自动化任务、股票雷达推送等实时更新场景
 */

import { useEffect, useRef, useState } from "react";

export interface WebSocketMessage<T = unknown> {
  type: string;
  data: T;
  timestamp: number;
}

export interface UseWebSocketOptions {
  url: string;
  enabled?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

export interface UseWebSocketReturn<T = unknown> {
  messages: WebSocketMessage<T>[];
  lastMessage: WebSocketMessage<T> | null;
  connected: boolean;
  error: string | null;
  send: (type: string, data: unknown) => void;
  clear: () => void;
  reconnect: () => void;
}

/**
 * WebSocket Hook - 实时事件流
 *
 * @example
 * const { messages, connected, send } = useWebSocket({
 *   url: `ws://localhost:8000/ws/runs/${runId}`,
 *   enabled: true,
 *   onMessage: (msg) => {
 *     if (msg.type === 'run_completed') {
 *       refetch();
 *     }
 *   }
 * });
 */
export function useWebSocket<T = unknown>(options: UseWebSocketOptions): UseWebSocketReturn<T> {
  const {
    url,
    enabled = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onMessage,
    onConnect,
    onDisconnect,
    onError
  } = options;

  const [messages, setMessages] = useState<WebSocketMessage<T>[]>([]);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage<T> | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = () => {
    if (!enabled || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log("[WebSocket] Connected:", url);
        setConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
        onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage<T> = JSON.parse(event.data);
          setMessages((prev) => [...prev, message]);
          setLastMessage(message);
          onMessage?.(message);
        } catch (err) {
          console.error("[WebSocket] Failed to parse message:", err);
        }
      };

      ws.onerror = (event) => {
        console.error("[WebSocket] Error:", event);
        setError("WebSocket 连接错误");
        onError?.(event);
      };

      ws.onclose = () => {
        console.log("[WebSocket] Disconnected");
        setConnected(false);
        wsRef.current = null;
        onDisconnect?.();

        // 自动重连
        if (enabled && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current += 1;
          console.log(`[WebSocket] Reconnecting (${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`);

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval);
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          setError(`WebSocket 重连失败（已尝试 ${maxReconnectAttempts} 次）`);
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error("[WebSocket] Connection error:", err);
      setError(err instanceof Error ? err.message : "WebSocket 连接失败");
    }
  };

  const disconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  const send = (type: string, data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message: WebSocketMessage = {
        type,
        data,
        timestamp: Date.now()
      };
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn("[WebSocket] Cannot send message: not connected");
    }
  };

  const clear = () => {
    setMessages([]);
    setLastMessage(null);
  };

  const reconnect = () => {
    reconnectAttemptsRef.current = 0;
    disconnect();
    connect();
  };

  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [url, enabled]);

  return {
    messages,
    lastMessage,
    connected,
    error,
    send,
    clear,
    reconnect
  };
}

/**
 * Server-Sent Events (SSE) Hook - 单向实时推送
 * 用于只读事件流场景（如日志流、运行状态）
 */
export interface UseSSEOptions {
  url: string;
  enabled?: boolean;
  onMessage?: (data: unknown) => void;
  onError?: (error: Event) => void;
}

export interface UseSSEReturn {
  messages: unknown[];
  lastMessage: unknown | null;
  connected: boolean;
  error: string | null;
  clear: () => void;
  reconnect: () => void;
}

export function useSSE(options: UseSSEOptions): UseSSEReturn {
  const { url, enabled = true, onMessage, onError } = options;

  const [messages, setMessages] = useState<unknown[]>([]);
  const [lastMessage, setLastMessage] = useState<unknown | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = () => {
    if (!enabled || eventSourceRef.current) {
      return;
    }

    try {
      const es = new EventSource(url);

      es.onopen = () => {
        console.log("[SSE] Connected:", url);
        setConnected(true);
        setError(null);
      };

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMessages((prev) => [...prev, data]);
          setLastMessage(data);
          onMessage?.(data);
        } catch (err) {
          console.error("[SSE] Failed to parse message:", err);
        }
      };

      es.onerror = (event) => {
        console.error("[SSE] Error:", event);
        setConnected(false);
        setError("SSE 连接错误");
        onError?.(event);
        es.close();
        eventSourceRef.current = null;
      };

      eventSourceRef.current = es;
    } catch (err) {
      console.error("[SSE] Connection error:", err);
      setError(err instanceof Error ? err.message : "SSE 连接失败");
    }
  };

  const disconnect = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setConnected(false);
    }
  };

  const clear = () => {
    setMessages([]);
    setLastMessage(null);
  };

  const reconnect = () => {
    disconnect();
    connect();
  };

  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [url, enabled]);

  return {
    messages,
    lastMessage,
    connected,
    error,
    clear,
    reconnect
  };
}
