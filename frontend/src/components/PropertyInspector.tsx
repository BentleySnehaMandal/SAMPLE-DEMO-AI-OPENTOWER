import { useAppStore } from '../store/appStore';

export default function PropertyInspector() {
  const selectedId = useAppStore((s) => s.selectedComponentId);
  const mounts = useAppStore((s) => s.viewer.mounts);
  const viewer = useAppStore((s) => s.viewer);

  const mount = mounts.find((m) => m.id === selectedId);

  if (!selectedId) {
    return (
      <div className="p-4 text-gray-500 text-sm">
        <div className="text-center mt-4">
          <div className="text-2xl mb-2">🔍</div>
          <div>Click a component in the 3D viewer to inspect it</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 text-sm">
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">Component Inspector</div>

      <div className="bg-gray-800 rounded-lg p-3 mb-3">
        <div className="font-mono text-blue-300 text-sm mb-1">{selectedId}</div>
        {mount ? (
          <div className="text-xs text-emerald-400 capitalize">{mount.type.replace('_', ' ')}</div>
        ) : (
          <div className="text-xs text-gray-400">Structural Member</div>
        )}
      </div>

      {mount ? (
        <div className="space-y-2">
          <PropRow label="Type" value={mount.type.replace('_', ' ')} />
          <PropRow label="Height" value={`${mount.height} m`} />
          <PropRow label="Azimuth" value={`${mount.azimuth}°`} />
          <PropRow label="Tilt" value={`${mount.tilt}°`} />
          <PropRow label="Arm Length" value={`${mount.arm_length} m`} />
          <div className="mt-3 text-xs text-gray-500">
            Tip: Ask the AI to move, rotate, or remove this component.
          </div>
        </div>
      ) : (
        <StructuralInfo compId={selectedId} towerType={viewer.geometry?.tower_type} />
      )}

      <button
        className="mt-4 w-full text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded px-3 py-2 transition-colors"
        onClick={() => {
          useAppStore.getState().setSelectedComponent(null);
        }}
      >
        Clear Selection
      </button>
    </div>
  );
}

function PropRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-200 font-mono">{value}</span>
    </div>
  );
}

function StructuralInfo({ compId, towerType }: { compId: string; towerType?: string }) {
  const id = compId.toLowerCase();
  let role = 'Structural Member';
  let desc = `Part of ${towerType || 'tower'} structure.`;

  if (id.includes('leg')) { role = 'Tower Leg'; desc = 'Primary vertical load-carrying element. Transfers gravity and wind loads to foundation.'; }
  else if (id.includes('brace')) { role = 'Bracing Member'; desc = 'Provides lateral stability. Resists shear forces from wind loading.'; }
  else if (id.includes('guy')) { role = 'Guy Wire'; desc = 'Pre-tensioned cable providing lateral restraint, reducing bending moments significantly.'; }
  else if (id.includes('ring') || id.includes('horiz')) { role = 'Horizontal Ring'; desc = 'Maintains cross-section geometry and distributes lateral loads.'; }
  else if (id.includes('platform')) { role = 'Work Platform'; desc = 'Maintenance access level. Adds wind load area; height affects overturning moment.'; }
  else if (id.includes('mast') || id.includes('pole')) { role = 'Main Mast'; desc = 'Primary structural spine carrying combined axial and bending loads.'; }

  return (
    <div className="space-y-2">
      <PropRow label="Role" value={role} />
      <div className="text-xs text-gray-400 leading-relaxed mt-2">{desc}</div>
    </div>
  );
}
