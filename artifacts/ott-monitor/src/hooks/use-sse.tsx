import React, { createContext, useContext, useEffect, useState } from 'react';
import type { CheckResult } from '@workspace/api-client-react';

interface SseContextType {
  deviceStatuses: Record<number, CheckResult>;
  hlsStreamStatuses: Record<number, CheckResult>;
  connected: boolean;
}

const SseContext = createContext<SseContextType | undefined>(undefined);

export function SseProvider({ children }: { children: React.ReactNode }) {
  const [deviceStatuses, setDeviceStatuses] = useState<Record<number, CheckResult>>({});
  const [hlsStreamStatuses, setHlsStreamStatuses] = useState<Record<number, CheckResult>>({});
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let evtSource: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      evtSource = new EventSource('/api/stream/status');

      evtSource.onopen = () => {
        setConnected(true);
      };

      evtSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Format expected: { type: 'device' | 'hls_stream', result: CheckResult }
          if (data.type === 'device' && data.result?.device_id) {
            setDeviceStatuses(prev => ({ ...prev, [data.result.device_id]: data.result }));
          } else if (data.type === 'hls_stream' && data.result?.hls_stream_id) {
            setHlsStreamStatuses(prev => ({ ...prev, [data.result.hls_stream_id]: data.result }));
          }
        } catch (error) {
          console.error("SSE Parse error", error);
        }
      };

      evtSource.onerror = () => {
        setConnected(false);
        evtSource?.close();
        reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      evtSource?.close();
      clearTimeout(reconnectTimeout);
    };
  }, []);

  return (
    <SseContext.Provider value={{ deviceStatuses, hlsStreamStatuses, connected }}>
      {children}
    </SseContext.Provider>
  );
}

export function useSse() {
  const context = useContext(SseContext);
  if (!context) {
    throw new Error('useSse must be used within an SseProvider');
  }
  return context;
}
