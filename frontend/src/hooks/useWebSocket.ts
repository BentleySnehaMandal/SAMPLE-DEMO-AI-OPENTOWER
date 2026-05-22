import { useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '../store/appStore';
import { downloadReportBlob } from '../utils/report';

const WS_BASE = 'ws://localhost:8000/ws';

export function useWebSocket(sessionId: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const store = useAppStore();

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    const ws = new WebSocket(`${WS_BASE}/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      store.setConnected(true);
      store.addMessage({ role: 'system', content: '🔗 Connected to Tower Engineering AI' });
    };

    ws.onclose = () => {
      store.setConnected(false);
    };

    ws.onerror = () => {
      store.setConnected(false);
      store.addMessage({ role: 'system', content: '⚠️ Connection lost. Retrying...' });
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg, store);
      } catch {
        console.error('Failed to parse WS message');
      }
    };

    return () => {
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return { send };
}

function handleMessage(msg: { type: string; payload: Record<string, unknown> }, store: ReturnType<typeof useAppStore.getState>) {
  switch (msg.type) {
    case 'session_init':
    case 'geometry_update':
      store.applyViewerUpdate(msg.payload as Parameters<typeof store.applyViewerUpdate>[0]);
      break;

    case 'ai_response':
      store.setThinking(false);
      store.addMessage({
        role: 'assistant',
        content: (msg.payload.content as string) || '',
        tool_called: msg.payload.tool_called as string | undefined,
      });
      break;

    case 'thinking':
      store.setThinking(true);
      break;

    case 'wind_analysis_result':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      store.setWindResult(msg.payload as any);
      if (msg.payload.wind_params) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        store.setWindParams(msg.payload.wind_params as any);
      }
      break;

    case 'wind_deformation_update':
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      store.setDeformedGeometry((msg.payload as any).deformed);
      break;

    case 'component_selected':
      store.setSelectedComponent(msg.payload.id as string);
      break;

    case 'report_ready': {
      const pdfB64 = msg.payload.pdf_base64 as string | undefined;
      const filename = (msg.payload.filename as string) || 'tower_report.pdf';
      const sid = msg.payload.session_id as string;

      if (pdfB64) {
        // Inline base64 delivery — no HTTP request needed, works reliably
        try {
          const bytes = Uint8Array.from(atob(pdfB64), (c) => c.charCodeAt(0));
          const blob = new Blob([bytes], { type: 'application/pdf' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          store.addMessage({ role: 'system', content: '📄 Engineering report downloaded.' });
        } catch {
          store.addMessage({ role: 'system', content: '⚠️ PDF decode failed. Try the Download button in the Wind Sim panel.' });
        }
      } else {
        // Fallback: backend didn't include base64, use direct browser navigation (no CORS)
        downloadReportBlob(sid);
        store.addMessage({ role: 'system', content: '📄 Downloading report…' });
      }
      break;
    }

    case 'error':
      store.setThinking(false);
      store.addMessage({ role: 'system', content: `⚠️ Error: ${msg.payload.message}` });
      break;

    case 'pong':
      break;

    default:
      console.debug('Unhandled WS message:', msg.type);
  }
}
