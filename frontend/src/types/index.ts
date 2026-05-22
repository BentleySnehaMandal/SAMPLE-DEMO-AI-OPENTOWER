// Engineering state types mirroring backend models

export type TowerType = 'lattice' | 'guyed' | 'monopole';
export type MountType = 'antenna' | 'rru' | 'microwave_dish' | 'gps' | 'cable_tray';

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface GeometryComponent {
  type: 'cylinder' | 'sphere';
  id: string;
  color: string;
  start?: Vec3;
  end?: Vec3;
  radius?: number;
  position?: Vec3;
}

export interface TowerGeometry {
  tower_type: TowerType;
  components: GeometryComponent[];
  bounds: {
    height: number;
    base_width?: number;
    top_width?: number;
    base_diameter?: number;
    mast_radius?: number;
  };
}

export interface MountedComponent {
  id: string;
  type: MountType;
  label: string;
  height: number;
  azimuth: number;
  tilt: number;
  arm_length: number;
  metadata: Record<string, unknown>;
}

export interface WindLoadCase {
  direction: number;
  wind_speed: number;
  base_shear: number;
  overturning_moment: number;
  tip_deflection: number;
  max_stress_ratio: number;
}

export interface WindAnalysisResult {
  load_cases: WindLoadCase[];
  max_deflection_m: number;
  critical_direction: number;
  stability_index: number;
  pressure_profile: { height: number; pressure: number }[];
  deformed_geometry?: TowerGeometry | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  tool_called?: string;
}

export interface ViewerState {
  geometry: TowerGeometry | null;
  deformedGeometry: TowerGeometry | null;
  mounts: MountedComponent[];
  mountGeometries: GeometryComponent[];
  selectedComponentId: string | null;
  geometry_version: number;
}

export interface WindInputParams {
  structural_class: string;
  exposure_category: string;
  topographic_category: string;
  min_wind_speed: number;
  max_wind_speed: number;
  service_wind_speed: number;
  direction_deg: number;
  ice_wind_speed: number;
  ice_thickness: number;
  ice_density: number;
}

export interface WindSimState {
  active: boolean;
  intensity: number;
  direction: number;
  result: WindAnalysisResult | null;
  showDeformed: boolean;
  showOriginal: boolean;
  showPressureHeatmap: boolean;
  showWindArrows: boolean;
  windParams: WindInputParams | null;
}

export interface AppState {
  sessionId: string;
  connected: boolean;
  thinking: boolean;
  messages: ChatMessage[];
  viewer: ViewerState;
  windSim: WindSimState;
  selectedComponentId: string | null;
}
