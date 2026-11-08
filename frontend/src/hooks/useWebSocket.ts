import { useRef, useCallback, useState } from 'react';

type MessageHandler = (data: ArrayBuffer | string) => void;

interface UseWebSocketReturn {
  connect: () => void;
  disconnect: () => void;
  sendJson: (data: Record<string, unknown>) => void;
  sendBinary: (data: ArrayBuffer) => void;
  isConnected: boolean;
}

export function useWebSocket(
  onMessage: MessageHandler,
  onOpen?: () => void,
  onClose?: () => void,
  onError?: (msg: string) => void
): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('WebSocket already open, sending start trigger...');
      onOpenRef.current?.();
      return;
    }

    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }

    // Support remote backend (e.g. when hosted on Vercel) or fallback to current origin
    const remoteBackend = (import.meta as any).env?.VITE_BACKEND_URL;
    let wsUrl = '';
    if (remoteBackend) {
      const cleanHost = remoteBackend.replace(/^https?:\/\//, '').replace(/\/$/, '');
      const protocol = remoteBackend.startsWith('http:') ? 'ws:' : 'wss:';
      wsUrl = `${protocol}//${cleanHost}/ws/voice-conversion`;
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      wsUrl = `${protocol}//${window.location.host}/ws/voice-conversion`;
    }

    console.log('Connecting WebSocket to:', wsUrl);
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log('WebSocket opened successfully');
      setIsConnected(true);
      onOpenRef.current?.();
    };

    ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        onMessageRef.current?.(event.data);
      } else if (typeof event.data === 'string') {
        onMessageRef.current?.(event.data);
      }
    };

    ws.onclose = (event: CloseEvent) => {
      console.log('WebSocket closed code:', event.code, event.reason);
      setIsConnected(false);
      wsRef.current = null;
      onCloseRef.current?.();
    };

    ws.onerror = (e) => {
      console.error('WebSocket error:', e);
      onErrorRef.current?.('WebSocket connection error');
    };

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
      setIsConnected(false);
    }
  }, []);

  const sendJson = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  return { connect, disconnect, sendJson, sendBinary, isConnected };
}
