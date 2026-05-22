"""
Agent Tool Definitions.
Each tool function operates on the EngineeringState and returns structured results.
"""
from __future__ import annotations
import re
import uuid
from typing import Any, Dict, List, Optional
from models.state import (
    EngineeringState, LatticeParams, GuyedParams, MonopoleParams,
    MountedComponent, WindInputParams
)
from engineering.geometry import (
    gen_lattice, gen_guyed, gen_monopole, gen_mount_geometry,
    normalize_bracing_type, SUPPORTED_BRACING_TYPES,
)
from engineering.wind_analysis import run_multi_direction_analysis


TOWER_DEFAULTS = {
    "lattice": LatticeParams,
    "guyed": GuyedParams,
    "monopole": MonopoleParams,
}


def tool_create_tower(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    tower_type = args.get("tower_type", "lattice").lower()
    if tower_type not in TOWER_DEFAULTS:
        return {"error": f"Unknown tower type: {tower_type}"}

    ParamModel = TOWER_DEFAULTS[tower_type]
    # Merge user args with defaults, normalizing bracing_type
    param_input = {k: v for k, v in args.items() if k != "tower_type"}
    if "bracing_type" in param_input:
        normalized = normalize_bracing_type(str(param_input["bracing_type"]))
        if normalized:
            param_input["bracing_type"] = normalized
    params = ParamModel(**param_input)

    state.tower_type = tower_type
    state.params = params.model_dump()
    state.mounts = []
    state.wind_result = None
    state.touch()

    geometry = _gen_geometry(tower_type, state.params)
    note = f"Created {tower_type} tower, height={params.height}m."
    state.engineering_notes.append(note)

    return {"status": "created", "tower_type": tower_type, "params": state.params, "geometry": geometry}


def tool_modify_tower(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    if not state.tower_type:
        return {"error": "No tower exists. Create one first."}

    # ── Segment-specific bracing modification ──
    if "bracing_type" in args and ("segment_index" in args or "segment_start" in args):
        if state.tower_type != "lattice":
            return {"error": "Per-segment bracing is only supported for lattice towers."}
        btype = normalize_bracing_type(str(args["bracing_type"]))
        if btype is None:
            return {"error": f"Unsupported bracing type: '{args['bracing_type']}'. Supported: {', '.join(SUPPORTED_BRACING_TYPES)}."}
        seg_map: Dict[str, str] = state.params.setdefault("segment_bracing_map", {})
        segs = state.params.get("segment_count", 10)
        if "segment_index" in args:
            idx = int(args["segment_index"])
            if not (0 <= idx < segs):
                return {"error": f"Segment index {idx} out of range (0–{segs - 1})."}
            seg_map[str(idx)] = btype
        else:
            start = max(0, int(args.get("segment_start", 0)))
            end = min(segs - 1, int(args.get("segment_end", segs - 1)))
            for i in range(start, end + 1):
                seg_map[str(i)] = btype
        state.touch()
        geometry = _gen_geometry(state.tower_type, state.params)
        state.engineering_notes.append(f"Segment bracing overridden: {args}")
        return {"status": "modified", "params": state.params, "geometry": geometry}

    # ── Global parameter modification ──
    for k, v in args.items():
        if k in ("segment_index", "segment_start", "segment_end"):
            continue  # handled above
        if k in state.params:
            if k == "bracing_type":
                normalized = normalize_bracing_type(str(v))
                if normalized is None:
                    return {
                        "error": (
                            f"Unsupported bracing type: '{v}'. "
                            f"Supported: {', '.join(SUPPORTED_BRACING_TYPES)}."
                        )
                    }
                # Global bracing change also clears per-segment overrides
                state.params[k] = normalized
                state.params["segment_bracing_map"] = {}
            else:
                state.params[k] = v

    state.touch()
    geometry = _gen_geometry(state.tower_type, state.params)
    state.engineering_notes.append(f"Modified tower: {args}")
    return {"status": "modified", "params": state.params, "geometry": geometry}


def tool_add_mount(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    if not state.tower_type:
        return {"error": "No tower to mount on."}

    tower_h = state.params.get("height", 60) if state.params else 60
    mount_type = args.get("type", "antenna")

    # Face keyword → azimuth mapping
    _face_map = {"north": 0.0, "n": 0.0, "east": 90.0, "e": 90.0,
                 "south": 180.0, "s": 180.0, "west": 270.0, "w": 270.0}
    face = str(args.get("face", "")).lower().strip()
    if face in _face_map and "azimuth" not in args:
        args = {**args, "azimuth": _face_map[face]}

    # Lattice towers: determine azimuth from selection or ask for clarification
    if state.tower_type == "lattice" and "azimuth" not in args:
        leg_match = re.search(r"leg_(\d+)", state.selected_component_id or "")
        if leg_match:
            num_legs = state.params.get("num_legs", 4) if state.params else 4
            leg_idx = int(leg_match.group(1))
            args = {**args, "azimuth": leg_idx * 360.0 / num_legs}
        else:
            return {
                "status": "needs_clarification",
                "question": (
                    f"Which tower face should I mount the {mount_type} on? "
                    "Options: north, east, south, west — or select a tower leg in the 3D viewer first."
                ),
            }

    # count existing of same type for labeling
    existing = sum(1 for m in state.mounts if m.type == mount_type)
    label = f"{mount_type}_{existing + 1}"

    mount = MountedComponent(
        id=label,
        type=mount_type,
        label=label,
        height=args.get("height", tower_h * 0.85),
        azimuth=args.get("azimuth", 0.0),
        tilt=args.get("tilt", 0.0),
        arm_length=args.get("arm_length", 0.5),
    )
    state.mounts.append(mount)
    state.touch()
    geo = gen_mount_geometry(mount, state.tower_type, state.params)
    return {"status": "added", "mount": mount.model_dump(), "geometry": geo}


def tool_remove_mount(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    mount_id = args.get("id")
    before = len(state.mounts)
    state.mounts = [m for m in state.mounts if m.id != mount_id]
    if len(state.mounts) == before:
        return {"error": f"Component {mount_id} not found."}
    state.touch()
    return {"status": "removed", "id": mount_id}


def tool_update_mount(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    mount_id = args.get("id")
    tower_h = state.params.get("height", 9999) if state.params else 9999

    # Height validation
    if "height" in args:
        new_h = float(args["height"])
        if new_h < 0:
            return {"error": "Height cannot be negative."}
        if new_h > tower_h:
            return {"error": f"Requested elevation {new_h}m exceeds tower height {tower_h}m."}

    for m in state.mounts:
        if m.id == mount_id:
            for k, v in args.items():
                if k != "id" and hasattr(m, k):
                    setattr(m, k, v)
            state.touch()
            geo = gen_mount_geometry(m, state.tower_type, state.params)
            return {"status": "updated", "mount": m.model_dump(), "geometry": geo}
    return {"error": f"Component {mount_id} not found."}


def tool_run_wind_analysis(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    if not state.tower_type:
        return {"error": "No tower to analyze."}

    # Update wind params if provided
    wp_data = state.wind_params.model_dump()
    for k, v in args.items():
        if k in wp_data:
            wp_data[k] = v
    state.wind_params = WindInputParams(**wp_data)

    h = state.params.get("height", 60) if state.params else 60
    base_w = state.params.get("base_width", state.params.get("mast_radius", 1) * 2 if state.params else 2) if state.params else 5
    if state.tower_type == "monopole" and state.params:
        base_w = state.params.get("base_diameter", 2.5)

    result = run_multi_direction_analysis(
        state.tower_type, h, base_w, state.wind_params.model_dump()
    )
    state.wind_result = result
    state.simulation_active = True
    state.touch()

    return {
        "status": "completed",
        "max_deflection_m": result.max_deflection_m,
        "critical_direction": result.critical_direction,
        "stability_index": result.stability_index,
        "load_cases": [lc.model_dump() for lc in result.load_cases],
        "pressure_profile": result.pressure_profile,
    }


def tool_select_component(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    comp_id = args.get("id")
    state.selected_component_id = comp_id
    return {"status": "selected", "id": comp_id}


def tool_explain_component(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    comp_id = args.get("id") or state.selected_component_id
    if not comp_id:
        return {"error": "No component selected."}

    # Check mounts
    for m in state.mounts:
        if m.id == comp_id:
            return {
                "id": comp_id,
                "type": m.type,
                "description": _mount_description(m),
                "metadata": m.model_dump(),
            }

    # Parse structural component
    return {
        "id": comp_id,
        "type": "structural",
        "description": _structural_description(comp_id, state),
    }


def tool_sync_viewer(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    """Build the full viewer state payload."""
    geometry = None
    if state.tower_type and state.params:
        geometry = _gen_geometry(state.tower_type, state.params)

    mount_geometries = []
    for m in state.mounts:
        mount_geometries.extend(gen_mount_geometry(m, state.tower_type, state.params))

    return {
        "geometry": geometry,
        "mounts": [m.model_dump() for m in state.mounts],
        "mount_geometries": mount_geometries,
        "selected_component_id": state.selected_component_id,
        "wind_result": state.wind_result.model_dump() if state.wind_result else None,
        "geometry_version": state.geometry_version,
    }


def tool_retrieve_session_state(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    return state.model_dump()


def tool_generate_report(state: EngineeringState, args: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger PDF generation – actual bytes sent separately via HTTP endpoint."""
    return {"status": "ready", "session_id": state.session_id, "action": "download_report"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen_geometry(tower_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if tower_type == "lattice":
        return gen_lattice(params)
    elif tower_type == "guyed":
        return gen_guyed(params)
    elif tower_type == "monopole":
        return gen_monopole(params)
    return {}


def _mount_description(m: MountedComponent) -> str:
    descs = {
        "antenna": f"Sector antenna mounted at {m.height}m height, azimuth {m.azimuth}°. Used for cellular signal transmission.",
        "rru": f"Remote Radio Unit (RRU) at {m.height}m. Handles baseband-to-RF conversion close to the antenna.",
        "microwave_dish": f"Microwave point-to-point dish at {m.height}m, aimed at {m.azimuth}°. Used for backhaul links.",
        "gps": f"GPS receiver module at {m.height}m. Provides timing synchronization for the BTS.",
        "cable_tray": f"Cable management tray at {m.height}m. Routes feeder and power cables.",
    }
    return descs.get(m.type, f"Component type: {m.type} at {m.height}m.")


def _structural_description(comp_id: str, state: EngineeringState) -> str:
    cid = comp_id.lower()
    if "leg" in cid:
        return "Tower leg member – primary vertical load-carrying element. Transfers all gravity and wind loads to foundation."
    if "brace" in cid or "brac" in cid:
        return "Bracing member – provides lateral stability and resists shear forces from wind loading."
    if "guy" in cid:
        return "Guy wire – pre-tensioned cable that provides lateral restraint to the mast, greatly reducing bending moments."
    if "ring" in cid or "horiz" in cid:
        return "Horizontal ring member – maintains geometric shape of the tower cross-section and distributes lateral loads."
    if "platform" in cid:
        return "Work platform – provides maintenance access. Adds wind load area; position affects overturning moment."
    if "mast" in cid or "pole" in cid:
        return "Main mast/pole – primary structural spine carrying combined axial and bending loads."
    return f"Structural component '{comp_id}'. Part of the {state.tower_type or 'tower'} structure."


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = {
    "create_tower": tool_create_tower,
    "modify_tower": tool_modify_tower,
    "add_mount": tool_add_mount,
    "remove_mount": tool_remove_mount,
    "update_mount": tool_update_mount,
    "run_wind_analysis": tool_run_wind_analysis,
    "select_component": tool_select_component,
    "explain_component": tool_explain_component,
    "sync_viewer": tool_sync_viewer,
    "retrieve_session_state": tool_retrieve_session_state,
    "generate_report": tool_generate_report,
}
