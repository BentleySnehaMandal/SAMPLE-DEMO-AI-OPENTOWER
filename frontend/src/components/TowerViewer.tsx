import { useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid, Environment } from '@react-three/drei';
import * as THREE from 'three';
import type { GeometryComponent, TowerGeometry, Vec3 } from '../types';
import { useAppStore } from '../store/appStore';

// ── helpers ────────────────────────────────────────────────────────────────────

function toV3(v: Vec3): THREE.Vector3 {
  return new THREE.Vector3(v.x, v.y, v.z);
}

// ── Single structural member ───────────────────────────────────────────────────

interface MemberProps {
  comp: GeometryComponent;
  isSelected: boolean;
  isHovered: boolean;
  onClick: (id: string) => void;
  onHover: (id: string | null) => void;
  colorOverride?: string;
  opacity?: number;
}

function CylinderMember({ comp, isSelected, isHovered, onClick, onHover, colorOverride, opacity = 1 }: MemberProps) {
  const start = comp.start ? toV3(comp.start) : new THREE.Vector3();
  const end = comp.end ? toV3(comp.end) : new THREE.Vector3();
  const direction = end.clone().sub(start);
  const length = direction.length();
  const mid = start.clone().add(end).multiplyScalar(0.5);

  const quaternion = useMemo(() => {
    const q = new THREE.Quaternion();
    const up = new THREE.Vector3(0, 1, 0);
    const dir = direction.clone().normalize();
    q.setFromUnitVectors(up, dir);
    return q;
  }, [direction]);

  if (!comp.start || !comp.end) return null;
  const color = isSelected ? '#ffcc00' : isHovered ? '#ffffff' : colorOverride || comp.color;

  return (
    <mesh
      position={mid}
      quaternion={quaternion}
      onClick={(e) => { e.stopPropagation(); onClick(comp.id); }}
      onPointerOver={(e) => { e.stopPropagation(); onHover(comp.id); }}
      onPointerOut={() => onHover(null)}
    >
      <cylinderGeometry args={[comp.radius || 0.05, comp.radius || 0.05, length, 8]} />
      <meshStandardMaterial
        color={color}
        transparent={opacity < 1}
        opacity={opacity}
        roughness={0.4}
        metalness={0.6}
      />
    </mesh>
  );
}

function SphereMember({ comp, isSelected, isHovered, onClick, onHover, colorOverride, opacity = 1 }: MemberProps) {
  if (!comp.position) return null;
  const pos = toV3(comp.position);
  const color = isSelected ? '#ffcc00' : isHovered ? '#ffffff' : colorOverride || comp.color;
  return (
    <mesh
      position={pos}
      onClick={(e) => { e.stopPropagation(); onClick(comp.id); }}
      onPointerOver={(e) => { e.stopPropagation(); onHover(comp.id); }}
      onPointerOut={() => onHover(null)}
    >
      <sphereGeometry args={[comp.radius || 0.15, 8, 8]} />
      <meshStandardMaterial color={color} transparent={opacity < 1} opacity={opacity} />
    </mesh>
  );
}

// ── Tower mesh group ───────────────────────────────────────────────────────────

interface TowerMeshProps {
  geometry: TowerGeometry;
  colorOverride?: string;
  opacity?: number;
  onSelectComponent: (id: string) => void;
}

function TowerMesh({ geometry, colorOverride, opacity = 1, onSelectComponent }: TowerMeshProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const selected = useAppStore((s) => s.selectedComponentId);

  return (
    <group>
      {geometry.components.map((comp) =>
        comp.type === 'cylinder' ? (
          <CylinderMember
            key={comp.id}
            comp={comp}
            isSelected={selected === comp.id}
            isHovered={hovered === comp.id}
            onClick={onSelectComponent}
            onHover={setHovered}
            colorOverride={colorOverride}
            opacity={opacity}
          />
        ) : (
          <SphereMember
            key={comp.id}
            comp={comp}
            isSelected={selected === comp.id}
            isHovered={hovered === comp.id}
            onClick={onSelectComponent}
            onHover={setHovered}
            colorOverride={colorOverride}
            opacity={opacity}
          />
        )
      )}
    </group>
  );
}

// ── Wind arrows ────────────────────────────────────────────────────────────────

interface WindArrowsProps {
  height: number;
  direction: number;
  intensity: number;
}

function WindArrows({ height, direction, intensity }: WindArrowsProps) {
  const arrows = useMemo(() => {
    const items = [];
    const count = 6;
    const dirRad = (direction * Math.PI) / 180;
    const dx = Math.cos(dirRad);
    const dz = Math.sin(dirRad);
    for (let i = 0; i < count; i++) {
      const y = (height * (i + 1)) / (count + 1);
      const len = 3 + intensity * 4;
      items.push({ y, dx, dz, len });
    }
    return items;
  }, [height, direction, intensity]);

  return (
    <group>
      {arrows.map((a, i) => {
        const start = new THREE.Vector3(-a.dx * a.len * 2, a.y, -a.dz * a.len * 2);
        const end = new THREE.Vector3(a.dx * 2, a.y, a.dz * 2);
        const dir = end.clone().sub(start).normalize();
        const len = end.clone().sub(start).length();
        const mid = start.clone().add(end).multiplyScalar(0.5);
        const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        return (
          <mesh key={i} position={mid} quaternion={q}>
            <cylinderGeometry args={[0.04, 0.04, len, 6]} />
            <meshBasicMaterial color="#00aaff" transparent opacity={0.5} />
          </mesh>
        );
      })}
    </group>
  );
}

// ── Main Viewer ────────────────────────────────────────────────────────────────

interface TowerViewerProps {
  onSelectComponent: (id: string) => void;
  onDeselectComponent?: () => void;
}

export default function TowerViewer({ onSelectComponent, onDeselectComponent }: TowerViewerProps) {
  const viewer = useAppStore((s) => s.viewer);
  const windSim = useAppStore((s) => s.windSim);

  const height = viewer.geometry?.bounds.height ?? 60;

  return (
    <div className="w-full h-full bg-gray-950 rounded-lg overflow-hidden">
      <Canvas
        camera={{ position: [height * 0.8, height * 0.6, height * 0.8], fov: 50 }}
        shadows
        onPointerMissed={() => onDeselectComponent?.()}
      >
        <ambientLight intensity={0.4} />
        <directionalLight position={[50, 100, 50]} intensity={1.2} castShadow />
        <pointLight position={[-30, 80, -30]} intensity={0.5} color="#aaccff" />

        {/* Grid */}
        <Grid
          args={[200, 200]}
          cellSize={5}
          cellThickness={0.5}
          cellColor="#1a2a3a"
          sectionSize={20}
          sectionThickness={1}
          sectionColor="#2a4a6a"
          fadeDistance={200}
          position={[0, 0, 0]}
        />

        {/* Original tower */}
        {viewer.geometry && windSim.showOriginal && (
          <TowerMesh
            geometry={viewer.geometry}
            opacity={windSim.active && windSim.showDeformed ? 0.35 : 1}
            colorOverride={windSim.active ? '#44aaff' : undefined}
            onSelectComponent={onSelectComponent}
          />
        )}

        {/* Deformed tower (wind sim) */}
        {windSim.active && windSim.showDeformed && viewer.deformedGeometry && (
          <TowerMesh
            geometry={viewer.deformedGeometry}
            colorOverride="#ff4444"
            opacity={0.8}
            onSelectComponent={onSelectComponent}
          />
        )}

        {/* Mount geometries */}
        {viewer.mountGeometries.map((comp) =>
          comp.type === 'cylinder' ? (
            <CylinderMember
              key={comp.id}
              comp={comp}
              isSelected={viewer.selectedComponentId === comp.id}
              isHovered={false}
              onClick={onSelectComponent}
              onHover={() => {}}
            />
          ) : (
            <SphereMember
              key={comp.id}
              comp={comp}
              isSelected={viewer.selectedComponentId === comp.id}
              isHovered={false}
              onClick={onSelectComponent}
              onHover={() => {}}
            />
          )
        )}

        {/* Wind arrows */}
        {windSim.active && windSim.showWindArrows && (
          <WindArrows
            height={height}
            direction={windSim.direction}
            intensity={windSim.intensity}
          />
        )}

        <OrbitControls makeDefault enableDamping dampingFactor={0.05} />
        <Environment preset="city" />
      </Canvas>
    </div>
  );
}
