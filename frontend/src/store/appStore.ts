import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type {
  AppState, ChatMessage, TowerGeometry, GeometryComponent,
  MountedComponent, WindAnalysisResult, WindSimState, WindInputParams
} from '../types';
import { v4 as uuidv4 } from 'uuid';

// Install uuid: npm install uuid @types/uuid

interface AppStore extends AppState {
  setSessionId: (id: string) => void;
  setConnected: (v: boolean) => void;
  setThinking: (v: boolean) => void;
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  setGeometry: (geo: TowerGeometry | null) => void;
  setDeformedGeometry: (geo: TowerGeometry | null) => void;
  setMounts: (mounts: MountedComponent[]) => void;
  setMountGeometries: (geos: GeometryComponent[]) => void;
  setSelectedComponent: (id: string | null) => void;
  setWindResult: (result: WindAnalysisResult | null) => void;
  setWindSimActive: (v: boolean) => void;
  setWindIntensity: (v: number) => void;
  setWindDirection: (v: number) => void;
  toggleWindOption: (key: keyof Pick<WindSimState, 'showDeformed' | 'showOriginal' | 'showPressureHeatmap' | 'showWindArrows'>) => void;
  setWindParams: (params: WindInputParams | null) => void;
  applyViewerUpdate: (payload: {
    geometry?: TowerGeometry | null;
    mounts?: MountedComponent[];
    mount_geometries?: GeometryComponent[];
    selected_component_id?: string | null;
    geometry_version?: number;
    wind_result?: WindAnalysisResult | null;
  }) => void;
}

export const useAppStore = create<AppStore>()(
  immer((set) => ({
    sessionId: '',
    connected: false,
    thinking: false,
    messages: [],
    selectedComponentId: null,
    viewer: {
      geometry: null,
      deformedGeometry: null,
      mounts: [],
      mountGeometries: [],
      selectedComponentId: null,
      geometry_version: 0,
    },
    windSim: {
      active: false,
      intensity: 1.0,
      direction: 0,
      result: null,
      showDeformed: true,
      showOriginal: true,
      showPressureHeatmap: false,
      showWindArrows: true,
      windParams: null,
    },

    setSessionId: (id) => set((s) => { s.sessionId = id; }),
    setConnected: (v) => set((s) => { s.connected = v; }),
    setThinking: (v) => set((s) => { s.thinking = v; }),

    addMessage: (msg) =>
      set((s) => {
        s.messages.push({ ...msg, id: uuidv4(), timestamp: Date.now() });
      }),

    setGeometry: (geo) => set((s) => { s.viewer.geometry = geo; }),
    setDeformedGeometry: (geo) => set((s) => { s.viewer.deformedGeometry = geo; }),
    setMounts: (mounts) => set((s) => { s.viewer.mounts = mounts; }),
    setMountGeometries: (geos) => set((s) => { s.viewer.mountGeometries = geos; }),

    setSelectedComponent: (id) =>
      set((s) => {
        s.selectedComponentId = id;
        s.viewer.selectedComponentId = id;
      }),

    setWindResult: (result) =>
      set((s) => {
        s.windSim.result = result;
        s.windSim.active = result !== null;
      }),

    setWindSimActive: (v) => set((s) => { s.windSim.active = v; }),
    setWindIntensity: (v) => set((s) => { s.windSim.intensity = v; }),
    setWindDirection: (v) => set((s) => { s.windSim.direction = v; }),

    setWindParams: (params) => set((s) => { s.windSim.windParams = params; }),

    toggleWindOption: (key) =>
      set((s) => {
        (s.windSim as Record<string, unknown>)[key] = !(s.windSim as Record<string, unknown>)[key];
      }),

    applyViewerUpdate: (payload) =>
      set((s) => {
        if (payload.geometry !== undefined) s.viewer.geometry = payload.geometry;
        if (payload.mounts) s.viewer.mounts = payload.mounts;
        if (payload.mount_geometries) s.viewer.mountGeometries = payload.mount_geometries;
        if (payload.selected_component_id !== undefined)
          s.viewer.selectedComponentId = payload.selected_component_id;
        if (payload.geometry_version !== undefined)
          s.viewer.geometry_version = payload.geometry_version;
        if (payload.wind_result !== undefined) s.windSim.result = payload.wind_result;
      }),
  }))
);
