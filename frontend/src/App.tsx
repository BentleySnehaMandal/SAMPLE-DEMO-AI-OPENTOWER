import React, { useEffect, useState } from 'react';
import TowerViewer from './components/TowerViewer';
import ChatPanel from './components/ChatPanel';
import PropertyInspector from './components/PropertyInspector';
import WindSimPanel from './components/WindSimPanel';
import ComponentTree from './components/ComponentTree';
import { useWebSocket } from './hooks/useWebSocket';
import { useAppStore } from './store/appStore';

type RightPanel = 'inspector' | 'wind' | 'tree';

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [rightPanel, setRightPanel] = useState<RightPanel>('tree');
  const store = useAppStore();

  useEffect(() => {
    fetch('http://localhost:8000/session/new', { method: 'POST' })
      .then((r) => r.json())
      .then((d) => {
        setSessionId(d.session_id);
        store.setSessionId(d.session_id);
      })
      .catch(() => {
        const id = crypto.randomUUID();
        setSessionId(id);
        store.setSessionId(id);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { send } = useWebSocket(sessionId);

  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__towerWSSend = send;
  }, [send]);

  const handleSendMessage = (text: string) => {
    send({ type: 'chat', content: text });
  };

  const handleSelectComponent = (id: string) => {
    store.setSelectedComponent(id);
    send({ type: 'select_component', id });
    setRightPanel('inspector');
  };

  const handleDeselectComponent = () => {
    store.setSelectedComponent(null);
    send({ type: 'select_component', id: null });
  };

  useEffect(() => {
    if (store.windSim.active) setRightPanel('wind');
  }, [store.windSim.active]);

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 font-sans overflow-hidden">
      <header className="flex items-center gap-4 px-6 py-3 bg-gray-900 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🗼</span>
          <div>
            <div className="text-sm font-bold text-white leading-tight">AI-OTDIQ</div>
            <div className="text-xs text-gray-500">Telecom Tower Engineering Assistant</div>
          </div>
        </div>
        <div className="flex items-center gap-1 ml-4">
          {(['tree', 'inspector', 'wind'] as RightPanel[]).map((p) => {
            const labels: Record<RightPanel, string> = { tree: '🌲 Hierarchy', inspector: '🔍 Inspector', wind: '🌬️ Wind Sim' };
            return (
              <button key={p} onClick={() => setRightPanel(p)}
                className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${rightPanel === p ? 'bg-blue-600 text-white' : 'bg-gray-800 hover:bg-gray-700 text-gray-300'}`}>
                {labels[p]}
              </button>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-3">
          {store.viewer.geometry && (
            <div className="text-xs text-gray-500">
              {store.viewer.geometry.tower_type.toUpperCase()} • {store.viewer.geometry.bounds.height}m • {store.viewer.mounts.length} mounts
            </div>
          )}
          <div className={`flex items-center gap-1 text-xs ${store.connected ? 'text-green-400' : 'text-red-400'}`}>
            <div className={`w-1.5 h-1.5 rounded-full ${store.connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
            {store.connected ? 'Connected' : 'Disconnected'}
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-80 flex-shrink-0 border-r border-gray-800">
          <ChatPanel onSendMessage={handleSendMessage} />
        </div>
        <div className="flex-1 relative">
          <TowerViewer onSelectComponent={handleSelectComponent} onDeselectComponent={handleDeselectComponent} />
          {store.windSim.active && (
            <div className="absolute top-3 left-3 bg-red-900 bg-opacity-80 text-red-200 text-xs rounded px-2 py-1 flex items-center gap-1">
              <div className="w-1.5 h-1.5 bg-red-400 rounded-full animate-pulse" />
              Wind Simulation Active
            </div>
          )}
          {store.thinking && (
            <div className="absolute bottom-3 left-3 bg-blue-900 bg-opacity-80 text-blue-200 text-xs rounded px-2 py-1">
              ⚙ AI Processing...
            </div>
          )}
          {!store.viewer.geometry && !store.thinking && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center text-gray-700">
                <div className="text-5xl mb-3">🗼</div>
                <div className="text-sm">Ask the AI to create a tower</div>
                <div className="text-xs mt-1">e.g. "Create a 90m lattice tower"</div>
              </div>
            </div>
          )}
        </div>
        <div className="w-72 flex-shrink-0 border-l border-gray-800 overflow-y-auto bg-gray-900">
          {rightPanel === 'inspector' && <PropertyInspector />}
          {rightPanel === 'wind' && <WindSimPanel />}
          {rightPanel === 'tree' && <ComponentTree />}
        </div>
      </div>
    </div>
  );
}

