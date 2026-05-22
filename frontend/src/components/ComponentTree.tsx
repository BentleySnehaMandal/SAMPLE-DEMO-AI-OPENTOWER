import React from 'react';
import { useAppStore } from '../store/appStore';

export default function ComponentTree() {
  const mounts = useAppStore((s) => s.viewer.mounts);
  const geometry = useAppStore((s) => s.viewer.geometry);
  const selectedId = useAppStore((s) => s.selectedComponentId);
  const setSelected = useAppStore((s) => s.setSelectedComponent);

  const MOUNT_ICONS: Record<string, string> = {
    antenna: '📡',
    rru: '📦',
    microwave_dish: '🔭',
    gps: '🛰️',
    cable_tray: '🔌',
  };

  return (
    <div className="p-3 text-sm overflow-y-auto h-full">
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">Component Hierarchy</div>

      {/* Tower */}
      {geometry ? (
        <div className="mb-3">
          <div className="flex items-center gap-2 text-blue-300 font-medium mb-1">
            <span>🗼</span>
            <span>{geometry.tower_type.toUpperCase()} TOWER</span>
            <span className="ml-auto text-xs text-gray-500">{geometry.bounds.height}m</span>
          </div>
          <div className="ml-4 text-xs text-gray-500 space-y-1">
            <div>Height: {geometry.bounds.height}m</div>
            {geometry.bounds.base_width && <div>Base: {geometry.bounds.base_width}m</div>}
            {geometry.bounds.base_diameter && <div>Base Ø: {geometry.bounds.base_diameter}m</div>}
            <div className="text-gray-600">{geometry.components.length} geometry members</div>
          </div>
        </div>
      ) : (
        <div className="text-gray-600 text-xs mb-3">No tower created</div>
      )}

      {/* Mounted equipment */}
      <div className="mb-2">
        <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">
          Equipment ({mounts.length})
        </div>
        {mounts.length === 0 ? (
          <div className="text-xs text-gray-600">No equipment mounted</div>
        ) : (
          <div className="space-y-1">
            {mounts.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m.id === selectedId ? null : m.id)}
                className={`w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                  selectedId === m.id
                    ? 'bg-blue-800 text-blue-100 border border-blue-600'
                    : 'hover:bg-gray-800 text-gray-300'
                }`}
              >
                <span>{MOUNT_ICONS[m.type] || '📌'}</span>
                <span className="font-mono">{m.id}</span>
                <span className="text-gray-500 ml-auto">{m.height}m</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
