"""
Tower Engineering State Models
Pydantic schemas for the entire application state.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# ── Mount / Equipment ─────────────────────────────────────────────────────────

class MountedComponent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: Literal["antenna", "rru", "microwave_dish", "gps", "cable_tray"]
    label: str
    height: float          # metres from base
    azimuth: float = 0.0   # degrees
    tilt: float = 0.0
    arm_length: float = 0.5
    metadata: Dict[str, Any] = {}


# ── Tower Geometry Parameters ──────────────────────────────────────────────────

class LatticeParams(BaseModel):
    height: float = 60.0
    num_legs: int = 4
    base_width: float = 8.0
    top_width: float = 2.0
    bracing_type: Literal["x_bracing", "k_bracing", "warren", "hybrid"] = "x_bracing"
    segment_count: int = 10
    material: str = "galvanized_steel"
    leg_taper_ratio: float = 0.25
    platform_levels: List[float] = []
    include_ladder: bool = True
    # Per-segment bracing overrides: str(segment_index) → bracing_type
    segment_bracing_map: Dict[str, str] = Field(default_factory=dict)


class GuyedParams(BaseModel):
    height: float = 90.0
    mast_radius: float = 0.3
    guy_wire_levels: int = 3
    guy_anchor_distance: float = 30.0
    num_guy_directions: int = 3
    segment_count: int = 15
    material: str = "galvanized_steel"


class MonopoleParams(BaseModel):
    height: float = 45.0
    base_diameter: float = 2.5
    top_diameter: float = 0.6
    taper_profile: Literal["linear", "parabolic"] = "linear"
    segment_count: int = 12
    access_platform: bool = True
    material: str = "steel"


TowerParams = LatticeParams | GuyedParams | MonopoleParams


# ── Wind Analysis ──────────────────────────────────────────────────────────────

class WindInputParams(BaseModel):
    structural_class: str = "II"
    exposure_category: str = "C"
    topographic_category: str = "flat"
    min_wind_speed: float = 30.0   # m/s
    max_wind_speed: float = 60.0
    service_wind_speed: float = 45.0
    direction_deg: float = 0.0
    ice_wind_speed: float = 20.0
    ice_thickness: float = 0.0     # mm
    ice_density: float = 900.0     # kg/m³


class WindLoadCase(BaseModel):
    direction: float               # degrees
    wind_speed: float
    base_shear: float
    overturning_moment: float
    tip_deflection: float
    max_stress_ratio: float


class WindAnalysisResult(BaseModel):
    load_cases: List[WindLoadCase] = []
    max_deflection_m: float = 0.0
    critical_direction: float = 0.0
    stability_index: float = 1.0
    pressure_profile: List[Dict[str, float]] = []   # height vs pressure
    deformed_geometry: Optional[List[Dict[str, Any]]] = None


# ── Main Engineering State ─────────────────────────────────────────────────────

class EngineeringState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tower_type: Optional[Literal["lattice", "guyed", "monopole"]] = None
    params: Optional[Dict[str, Any]] = None        # serialized tower params
    mounts: List[MountedComponent] = []
    wind_params: WindInputParams = Field(default_factory=WindInputParams)
    wind_result: Optional[WindAnalysisResult] = None
    selected_component_id: Optional[str] = None
    geometry_version: int = 0
    simulation_active: bool = False
    engineering_notes: List[str] = []
    conversation_history: List[Dict[str, str]] = []
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def touch(self):
        self.updated_at = datetime.utcnow().isoformat()
        self.geometry_version += 1
