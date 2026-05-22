"""Engineering calculation utilities for telecom towers."""
from __future__ import annotations
import math
from typing import List, Dict, Any


# ── Wind load helpers (TIA-222 inspired simplified) ───────────────────────────

AIR_DENSITY = 1.225  # kg/m³

def dynamic_pressure(wind_speed_ms: float) -> float:
    """Basic dynamic wind pressure q = 0.5 * rho * V^2 (Pa)"""
    return 0.5 * AIR_DENSITY * wind_speed_ms ** 2


def exposure_factor(category: str, height_m: float) -> float:
    """Simplified exposure coefficient by height and category."""
    base = {"A": 0.70, "B": 0.85, "C": 1.00, "D": 1.15}.get(category.upper(), 1.0)
    return base * (height_m / 10.0) ** 0.20


def gust_factor(structural_class: str) -> float:
    return {"I": 0.85, "II": 0.90, "III": 0.95}.get(structural_class.upper(), 0.90)


def tower_drag_coefficient(tower_type: str) -> float:
    return {"lattice": 2.2, "guyed": 1.8, "monopole": 0.8}.get(tower_type, 1.2)


def compute_base_shear(
    tower_type: str,
    height_m: float,
    effective_width_m: float,
    wind_speed_ms: float,
    exposure: str = "C",
    struct_class: str = "II",
) -> float:
    """Estimate total horizontal wind shear at base (kN)."""
    total = 0.0
    segments = 20
    dh = height_m / segments
    Cd = tower_drag_coefficient(tower_type)
    G = gust_factor(struct_class)
    for i in range(segments):
        h = (i + 0.5) * dh
        Kz = exposure_factor(exposure, h)
        q = dynamic_pressure(wind_speed_ms)
        # width tapers linearly
        w = effective_width_m * (1 - 0.7 * h / height_m) if tower_type == "lattice" else effective_width_m
        F = q * Kz * G * Cd * w * dh
        total += F
    return total / 1000.0  # -> kN


def compute_overturning_moment(
    tower_type: str,
    height_m: float,
    effective_width_m: float,
    wind_speed_ms: float,
    exposure: str = "C",
    struct_class: str = "II",
) -> float:
    """Estimate overturning moment at base (kN·m)."""
    total = 0.0
    segments = 20
    dh = height_m / segments
    Cd = tower_drag_coefficient(tower_type)
    G = gust_factor(struct_class)
    for i in range(segments):
        h = (i + 0.5) * dh
        Kz = exposure_factor(exposure, h)
        q = dynamic_pressure(wind_speed_ms)
        w = effective_width_m * (1 - 0.7 * h / height_m) if tower_type == "lattice" else effective_width_m
        F = q * Kz * G * Cd * w * dh
        total += F * h
    return total / 1000.0  # -> kN·m


def compute_tip_deflection(
    tower_type: str,
    height_m: float,
    overturning_kNm: float,
    base_width_m: float = 5.0,
) -> float:
    """Approximate tip deflection using cantilever analogy (m)."""
    # EI estimate very rough – for visual purposes only
    E_steel = 200e6  # kN/m²
    if tower_type == "lattice":
        I_eff = (base_width_m / 2) ** 2 * 2 * 0.01  # rough section inertia m⁴
    elif tower_type == "guyed":
        I_eff = 0.008
    else:  # monopole
        r = base_width_m / 2
        t = 0.02
        I_eff = math.pi * ((r**4) - ((r - t)**4)) / 4
    EI = E_steel * I_eff
    deflection = overturning_kNm * (height_m ** 2) / (2 * EI)
    return min(deflection, height_m * 0.05)   # cap at 5% of height


def build_pressure_profile(
    tower_type: str,
    height_m: float,
    wind_speed_ms: float,
    exposure: str = "C",
    num_points: int = 20,
) -> List[Dict[str, float]]:
    profile = []
    Cd = tower_drag_coefficient(tower_type)
    for i in range(num_points):
        h = (i + 1) * height_m / num_points
        Kz = exposure_factor(exposure, h)
        q = dynamic_pressure(wind_speed_ms)
        p = q * Kz * Cd
        profile.append({"height": round(h, 2), "pressure": round(p, 2)})
    return profile


def run_multi_direction_analysis(
    tower_type: str,
    height_m: float,
    base_width_m: float,
    wind_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Run 12-direction (30° intervals) wind analysis."""
    from models.state import WindLoadCase, WindAnalysisResult
    load_cases = []
    max_defl = 0.0
    critical_dir = 0.0

    for i in range(12):
        direction = i * 30.0
        # effective width varies by direction for lattice
        angle_rad = math.radians(direction % 90)
        dir_factor = math.cos(angle_rad) + math.sin(angle_rad) * 0.6
        eff_width = base_width_m * dir_factor if tower_type == "lattice" else base_width_m

        V = wind_params.get("service_wind_speed", 45.0)
        exposure = wind_params.get("exposure_category", "C")
        struct_class = wind_params.get("structural_class", "II")

        shear = compute_base_shear(tower_type, height_m, eff_width, V, exposure, struct_class)
        moment = compute_overturning_moment(tower_type, height_m, eff_width, V, exposure, struct_class)
        deflection = compute_tip_deflection(tower_type, height_m, moment, eff_width)
        stress_ratio = min(moment / (height_m * 50), 0.99)  # normalized

        lc = WindLoadCase(
            direction=direction,
            wind_speed=V,
            base_shear=round(shear, 2),
            overturning_moment=round(moment, 2),
            tip_deflection=round(deflection, 3),
            max_stress_ratio=round(stress_ratio, 3),
        )
        load_cases.append(lc)

        if deflection > max_defl:
            max_defl = deflection
            critical_dir = direction

    pressure_profile = build_pressure_profile(tower_type, height_m, V, exposure)
    stability_idx = 1.0 - max(lc.max_stress_ratio for lc in load_cases)

    return WindAnalysisResult(
        load_cases=load_cases,
        max_deflection_m=round(max_defl, 3),
        critical_direction=critical_dir,
        stability_index=round(stability_idx, 3),
        pressure_profile=pressure_profile,
    )
