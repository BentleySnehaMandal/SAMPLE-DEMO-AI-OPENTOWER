"""
Parametric 3D geometry generators for tower types.
Returns JSON-serializable geometry descriptors consumed by the React Three Fiber frontend.
"""
from __future__ import annotations
import math
from typing import Any, Dict, List, Optional


# ── Bracing type normalization ─────────────────────────────────────────────────
BRACING_ALIASES: Dict[str, str] = {
    "x": "x_bracing", "x_bracing": "x_bracing", "x-bracing": "x_bracing", "x_brace": "x_bracing",
    "k": "k_bracing", "k_bracing": "k_bracing", "k-bracing": "k_bracing", "k_brace": "k_bracing",
    "warren": "warren", "w": "warren", "triangular": "warren", "diagonal": "warren",
    "hybrid": "hybrid", "h": "hybrid", "mixed": "hybrid",
}
SUPPORTED_BRACING_TYPES = ["x_bracing", "k_bracing", "warren", "hybrid"]


def normalize_bracing_type(s: str) -> Optional[str]:
    """Normalize bracing label (e.g. 'X', 'K-bracing') to internal key. Returns None if unsupported."""
    key = s.lower().strip().replace(" ", "_").replace("-", "_")
    if key in BRACING_ALIASES:
        return BRACING_ALIASES[key]
    for alias, btype in BRACING_ALIASES.items():
        if alias in key:
            return btype
    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def vec3(x, y, z):
    return {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}


def cylinder(start, end, radius, color="#aaaaaa", id_tag=""):
    return {
        "type": "cylinder",
        "start": start,
        "end": end,
        "radius": radius,
        "color": color,
        "id": id_tag,
    }


def sphere_node(pos, radius=0.15, color="#888888", id_tag=""):
    return {"type": "sphere", "position": pos, "radius": radius, "color": color, "id": id_tag}


# ── Lattice Tower ─────────────────────────────────────────────────────────────

def gen_lattice(params: Dict[str, Any]) -> Dict[str, Any]:
    h = params.get("height", 60.0)
    num_legs = params.get("num_legs", 4)
    base_w = params.get("base_width", 8.0)
    top_w = params.get("top_width", 2.0)
    segs = params.get("segment_count", 10)
    bracing = normalize_bracing_type(params.get("bracing_type", "x_bracing")) or "x_bracing"
    platforms = params.get("platform_levels", [])
    seg_bracing_map: Dict[str, str] = params.get("segment_bracing_map", {})

    components = []
    seg_h = h / segs
    angles = [i * (360 / num_legs) for i in range(num_legs)]

    leg_nodes: List[List[Dict]] = [[] for _ in range(num_legs)]

    for s in range(segs + 1):
        t = s / segs
        w = base_w * (1 - t) + top_w * t
        r = w / 2.0
        y = s * seg_h
        for li, ang in enumerate(angles):
            rad = math.radians(ang)
            leg_nodes[li].append(vec3(r * math.cos(rad), y, r * math.sin(rad)))

    # Legs
    for li in range(num_legs):
        for s in range(segs):
            cid = f"leg_{li}_seg_{s}"
            components.append(cylinder(leg_nodes[li][s], leg_nodes[li][s + 1], 0.08, "#4a90d9", cid))

    # Bracing
    for s in range(segs):
        # Per-segment override takes priority over global bracing type
        seg_bracing = normalize_bracing_type(seg_bracing_map.get(str(s), "")) or bracing
        for li in range(num_legs):
            ni = (li + 1) % num_legs
            b_bottom_a = leg_nodes[li][s]
            b_bottom_b = leg_nodes[ni][s]
            b_top_a = leg_nodes[li][s + 1]
            b_top_b = leg_nodes[ni][s + 1]

            if seg_bracing == "x_bracing":
                # Bright blue cross-bracing
                components.append(cylinder(b_bottom_a, b_top_b, 0.05, "#5599ff", f"brace_x_{li}_{s}_a"))
                components.append(cylinder(b_bottom_b, b_top_a, 0.05, "#5599ff", f"brace_x_{li}_{s}_b"))
            elif seg_bracing == "k_bracing":
                # Orange K-bracing with midpoint node
                mid = vec3(
                    (b_bottom_a["x"] + b_bottom_b["x"] + b_top_a["x"] + b_top_b["x"]) / 4,
                    (b_bottom_a["y"] + b_top_a["y"]) / 2,
                    (b_bottom_a["z"] + b_bottom_b["z"] + b_top_a["z"] + b_top_b["z"]) / 4,
                )
                components.append(cylinder(b_bottom_a, mid, 0.05, "#ff9900", f"brace_k_{li}_{s}_a"))
                components.append(cylinder(b_bottom_b, mid, 0.05, "#ff9900", f"brace_k_{li}_{s}_b"))
                components.append(cylinder(mid, b_top_a, 0.05, "#ff9900", f"brace_k_{li}_{s}_c"))
                components.append(cylinder(mid, b_top_b, 0.05, "#ff9900", f"brace_k_{li}_{s}_d"))
                components.append(sphere_node(mid, 0.07, "#ffbb44", f"brace_k_{li}_{s}_node"))
            elif seg_bracing == "warren":
                # Green alternating diagonals (Warren truss)
                if s % 2 == 0:
                    components.append(cylinder(b_bottom_a, b_top_b, 0.04, "#44dd88", f"brace_w_{li}_{s}"))
                else:
                    components.append(cylinder(b_bottom_b, b_top_a, 0.04, "#44dd88", f"brace_w_{li}_{s}"))
            else:  # hybrid: alternating X-bracing (blue) and Warren (green)
                if s % 2 == 0:
                    components.append(cylinder(b_bottom_a, b_top_b, 0.05, "#5599ff", f"brace_h_{li}_{s}_a"))
                    components.append(cylinder(b_bottom_b, b_top_a, 0.05, "#5599ff", f"brace_h_{li}_{s}_b"))
                else:
                    components.append(cylinder(b_bottom_a, b_top_b, 0.04, "#44dd88", f"brace_h_{li}_{s}"))

            # Horizontal ring
            components.append(cylinder(b_bottom_a, b_bottom_b, 0.04, "#2266aa", f"ring_{li}_{s}"))

    # Platforms
    for plat_h in platforms:
        t_p = plat_h / h
        w_p = base_w * (1 - t_p) + top_w * t_p
        r_p = w_p / 2
        for li in range(num_legs):
            ang = math.radians(angles[li])
            pa = vec3(r_p * math.cos(ang), plat_h, r_p * math.sin(ang))
            na = math.radians(angles[(li + 1) % num_legs])
            pb = vec3(r_p * math.cos(na), plat_h, r_p * math.sin(na))
            components.append(cylinder(pa, pb, 0.06, "#ffaa00", f"platform_{plat_h}_{li}"))

    return {
        "tower_type": "lattice",
        "components": components,
        "bounds": {"height": h, "base_width": base_w, "top_width": top_w},
    }


# ── Guyed Tower ───────────────────────────────────────────────────────────────

def gen_guyed(params: Dict[str, Any]) -> Dict[str, Any]:
    h = params.get("height", 90.0)
    r = params.get("mast_radius", 0.3)
    guy_levels = params.get("guy_wire_levels", 3)
    anchor_dist = params.get("guy_anchor_distance", 30.0)
    num_dirs = params.get("num_guy_directions", 3)
    segs = params.get("segment_count", 15)

    components = []
    seg_h = h / segs

    # Mast
    for s in range(segs):
        y0 = s * seg_h
        y1 = (s + 1) * seg_h
        components.append(cylinder(vec3(0, y0, 0), vec3(0, y1, 0), r, "#4a90d9", f"mast_seg_{s}"))

    # Guy wires
    for gl in range(guy_levels):
        attach_h = h * (gl + 1) / (guy_levels + 1)
        for d in range(num_dirs):
            ang = math.radians(d * 360 / num_dirs)
            anchor = vec3(anchor_dist * math.cos(ang), 0, anchor_dist * math.sin(ang))
            top_pt = vec3(0, attach_h, 0)
            components.append(cylinder(top_pt, anchor, 0.02, "#ffcc44", f"guy_{gl}_{d}"))

    return {
        "tower_type": "guyed",
        "components": components,
        "bounds": {"height": h, "mast_radius": r},
    }


# ── Monopole Tower ────────────────────────────────────────────────────────────

def gen_monopole(params: Dict[str, Any]) -> Dict[str, Any]:
    h = params.get("height", 45.0)
    base_d = params.get("base_diameter", 2.5)
    top_d = params.get("top_diameter", 0.6)
    segs = params.get("segment_count", 12)
    taper = params.get("taper_profile", "linear")

    components = []
    seg_h = h / segs

    for s in range(segs):
        t0 = s / segs
        t1 = (s + 1) / segs
        if taper == "parabolic":
            r0 = (base_d / 2) * (1 - t0 ** 2) + (top_d / 2) * t0 ** 2
            r1 = (base_d / 2) * (1 - t1 ** 2) + (top_d / 2) * t1 ** 2
        else:
            r0 = (base_d / 2) * (1 - t0) + (top_d / 2) * t0
            r1 = (base_d / 2) * (1 - t1) + (top_d / 2) * t1
        y0 = s * seg_h
        y1 = (s + 1) * seg_h
        # Use average radius for cylinder approx
        avg_r = (r0 + r1) / 2
        components.append(cylinder(vec3(0, y0, 0), vec3(0, y1, 0), avg_r, "#6699cc", f"pole_seg_{s}"))

    return {
        "tower_type": "monopole",
        "components": components,
        "bounds": {"height": h, "base_diameter": base_d, "top_diameter": top_d},
    }


# ── Mount geometry ────────────────────────────────────────────────────────────

MOUNT_COLORS = {
    "antenna": "#ff6b35",
    "rru": "#44cc88",
    "microwave_dish": "#cc44aa",
    "gps": "#ffee44",
    "cable_tray": "#888888",
}

MOUNT_SIZES = {
    "antenna": (0.08, 1.2),     # (radius, length)
    "rru": (0.15, 0.6),
    "microwave_dish": (0.4, 0.1),
    "gps": (0.05, 0.2),
    "cable_tray": (0.03, 2.0),
}


def _compute_arm_attachment(
    mount, tower_type: Optional[str], tower_params: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Return the physical point on the tower structure where the mount arm begins."""
    h = mount.height
    ang_rad = math.radians(mount.azimuth)

    if not tower_type or not tower_params:
        return vec3(0, h, 0)

    tower_h = tower_params.get("height", 60) or 60
    t = min(h / tower_h, 1.0) if tower_h > 0 else 0.0

    if tower_type == "lattice":
        base_w = tower_params.get("base_width", 8.0)
        top_w = tower_params.get("top_width", 2.0)
        num_legs = tower_params.get("num_legs", 4)
        w = base_w * (1 - t) + top_w * t
        r = w / 2.0
        # Snap azimuth to nearest leg
        leg_step = 360.0 / num_legs
        nearest = round(mount.azimuth / leg_step) * leg_step
        leg_rad = math.radians(nearest)
        return vec3(r * math.cos(leg_rad), h, r * math.sin(leg_rad))

    elif tower_type == "monopole":
        base_d = tower_params.get("base_diameter", 2.5)
        top_d = tower_params.get("top_diameter", 0.6)
        r = (base_d / 2) * (1 - t) + (top_d / 2) * t
        return vec3(r * math.cos(ang_rad), h, r * math.sin(ang_rad))

    elif tower_type == "guyed":
        r = tower_params.get("mast_radius", 0.3)
        return vec3(r * math.cos(ang_rad), h, r * math.sin(ang_rad))

    return vec3(0, h, 0)


def gen_mount_geometry(
    mount,
    tower_type: Optional[str] = None,
    tower_params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Generate geometry descriptors for a single mounted component."""
    color = MOUNT_COLORS.get(mount.type, "#ff0000")
    rad, length = MOUNT_SIZES.get(mount.type, (0.1, 0.5))
    ang = math.radians(mount.azimuth)
    arm = mount.arm_length

    arm_start = _compute_arm_attachment(mount, tower_type, tower_params)
    arm_end = vec3(
        arm_start["x"] + arm * math.cos(ang),
        mount.height,
        arm_start["z"] + arm * math.sin(ang),
    )
    eq_start = arm_end
    eq_end = vec3(
        arm_end["x"] + length * math.cos(ang),
        mount.height + length * math.sin(math.radians(mount.tilt)),
        arm_end["z"] + length * math.sin(ang),
    )

    return [
        sphere_node(arm_start, 0.08, "#666666", f"{mount.id}_bracket"),
        cylinder(arm_start, arm_end, 0.03, "#aaaaaa", f"{mount.id}_arm"),
        cylinder(eq_start, eq_end, rad, color, mount.id),
    ]


# ── Deformed geometry for wind sim ────────────────────────────────────────────

def apply_wind_deformation(
    geometry: Dict[str, Any],
    deflection_m: float,
    height_m: float,
    direction_deg: float = 0.0,
) -> Dict[str, Any]:
    """Apply a cantilever deformation to all geometry components for wind visualization."""
    import copy, json

    deformed = copy.deepcopy(geometry)
    ang = math.radians(direction_deg)
    dx = math.cos(ang)
    dz = math.sin(ang)

    def deform_point(pt: Dict) -> Dict:
        t = pt["y"] / height_m if height_m > 0 else 0
        # Parabolic deflection profile
        delta = deflection_m * (t ** 2)
        return vec3(pt["x"] + dx * delta, pt["y"], pt["z"] + dz * delta)

    for comp in deformed.get("components", []):
        if "start" in comp:
            comp["start"] = deform_point(comp["start"])
        if "end" in comp:
            comp["end"] = deform_point(comp["end"])
        if "position" in comp:
            comp["position"] = deform_point(comp["position"])

    return deformed
