"""
LangGraph agentic orchestration for the Tower Engineering Assistant.
Nodes: input → intent → context → plan → tool_exec → reflect → respond
"""
from __future__ import annotations
import json
import re
import logging
from typing import Any, Dict, List, Optional, TypedDict, Annotated
import operator

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, END

from models.state import EngineeringState
from tools.tower_tools import TOOLS

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are TOWER-AI, an expert structural engineering AI assistant for telecom towers.

CRITICAL INSTRUCTION: When the user wants to DO something (create, modify, add, remove, run analysis, generate report), you MUST output a tool call as a JSON code block. No exceptions.

TOOL CALL FORMAT — always wrap in triple backticks with json tag:
```json
{"tool": "TOOL_NAME", "args": {KEY: VALUE}}
```

AVAILABLE TOOLS AND WHEN TO USE THEM:

create_tower — user wants to create/build/make a new tower
  args: {"tower_type": "lattice"|"guyed"|"monopole", "height": number, "base_width": number, "num_legs": number, "bracing_type": "x_bracing"|"k_bracing"|"warren"|"hybrid", "segment_count": number}

modify_tower — user wants to change TOWER STRUCTURE parameters: height, bracing type, number of legs, base width, segment count.
  DO NOT USE for moving/adjusting equipment — use update_mount for that.
  args: {"height": number} or {"bracing_type": "k_bracing"} — only include changed fields
  For segment-specific bracing: {"segment_index": number, "bracing_type": "k_bracing"}
  For range of segments: {"segment_start": number, "segment_end": number, "bracing_type": "k_bracing"}

add_mount — user wants to add antenna, RRU, microwave dish, GPS, cable tray
  args: {"type": "antenna"|"rru"|"microwave_dish"|"gps"|"cable_tray", "height": number, "azimuth": number}

remove_mount — user wants to remove a specific mounted component
  args: {"id": "antenna_1"}

update_mount — user wants to MOVE, REPOSITION, ADJUST HEIGHT, ROTATE, or MODIFY a mounted component.
  Use this when the user references a specific component ID (antenna_1, rru_1, etc.) and wants to change its position.
  args: {"id": "antenna_1", "height": number, "azimuth": number, "tilt": number}

run_wind_analysis — user wants wind analysis, wind study, wind load calculation
  args: {"service_wind_speed": number, "direction_deg": number, "ice_thickness": number}

generate_report — user wants a PDF or engineering report
  args: {}

explain_component — user asks what a component is or what it does
  args: {"id": "SELECTED_COMPONENT_ID_OR_EMPTY"}

EXAMPLES:

User: "Create a 90m lattice tower"
```json
{"tool": "create_tower", "args": {"tower_type": "lattice", "height": 90}}
```

User: "Add 3 antennas near the top"
```json
{"tool": "add_mount", "args": {"type": "antenna", "height": 80, "azimuth": 0}}
```
(call this THREE times with different azimuths: 0, 120, 240)

User: "Run wind analysis at 50 m/s"
```json
{"tool": "run_wind_analysis", "args": {"service_wind_speed": 50}}
```

User: "Run analysis with heavy ice loading, ice thickness 25mm"
```json
{"tool": "run_wind_analysis", "args": {"ice_thickness": 25}}
```

User: "Run wind analysis at 50 m/s from the west"
```json
{"tool": "run_wind_analysis", "args": {"service_wind_speed": 50, "direction_deg": 270}}
```

User: "Increase height to 120m"
```json
{"tool": "modify_tower", "args": {"height": 120}}
```

User: "Move antenna_1 down to 60 meters"
```json
{"tool": "update_mount", "args": {"id": "antenna_1", "height": 60}}
```

User: "Raise rru_1 near the top"
```json
{"tool": "update_mount", "args": {"id": "rru_1", "height": 95}}
```

User: "Change segment 4 to K-bracing"
```json
{"tool": "modify_tower", "args": {"segment_index": 3, "bracing_type": "k_bracing"}}
```

User: "Use Warren bracing near the top"
```json
{"tool": "modify_tower", "args": {"segment_start": 7, "segment_end": 9, "bracing_type": "warren"}}
```

IMPORTANT DISAMBIGUATION:
- "Move/lower/raise/adjust antenna_1" → ALWAYS use update_mount (equipment has an ID like antenna_1, rru_2)
- "Increase tower height" → modify_tower
- If user mentions a component ID (antenna_1, rru_1, microwave_dish_1), use update_mount

For conversational questions (no action needed), just reply normally without a tool call.

ENGINEERING PERSONA:
- Apply engineering defaults when parameters are missing
- Lattice default: height=60m, 4 legs, X-bracing, base_width=8m
- Guyed default: height=90m, 3 guy levels, mast_radius=0.3m
- Monopole default: height=45m, base_diameter=2.5m
- Always give brief engineering commentary after actions
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Keyword-based intent fallback
# ═══════════════════════════════════════════════════════════════════════════════

def _keyword_fallback(user_text: str, eng_state: EngineeringState) -> Optional[Dict[str, Any]]:
    """
    If the LLM fails to produce a tool call, use keywords to infer one.
    Returns a tool call dict or None.
    """
    text = user_text.lower()

    # ── 1a. Remove mount (check FIRST to prevent 'remove' being caught by 'move' substring) ──
    if re.search(r"\b(remove|delete|take off)\b", text):
        mount_rm = re.search(r"\b(antenna|rru|microwave_dish|gps|cable_tray)_\d+\b", text)
        if mount_rm:
            return {"tool": "remove_mount", "args": {"id": mount_rm.group(0)}}

    # ── 1b. Update mount (HIGHEST PRIORITY after remove — check before modify_tower to prevent misrouting) ──
    # If text references a specific component ID, always route to update_mount
    mount_id_match = re.search(r"\b(antenna|rru|microwave_dish|gps|cable_tray)_(\d+)\b", text)
    _UPDATE_WORDS = re.compile(r"\b(move|lower|raise|set|put|change|update|adjust|relocate|shift|elevation|height|position)\b")
    if mount_id_match and _UPDATE_WORDS.search(text):
        mount_id = mount_id_match.group(0)
        new_h = _extract_height_from_text(text)
        args: Dict[str, Any] = {"id": mount_id}
        if new_h is not None:
            args["height"] = new_h
        elif "top" in text or "near the top" in text:
            tower_h = eng_state.params.get("height", 60) if eng_state.params else 60
            args["height"] = tower_h * 0.9
        elif "bottom" in text or "base" in text or "near the bottom" in text:
            tower_h = eng_state.params.get("height", 60) if eng_state.params else 60
            args["height"] = tower_h * 0.1
        return {"tool": "update_mount", "args": args}

    # ── 2. Create tower ──
    if any(w in text for w in ["create", "build", "make", "generate"]):
        if any(w in text for w in ["lattice", "guyed", "monopole", "tower"]):
            tower_type = "lattice"
            if "guyed" in text:
                tower_type = "guyed"
            elif "monopole" in text:
                tower_type = "monopole"
            height = _extract_number(text, default=60.0)
            return {"tool": "create_tower", "args": {"tower_type": tower_type, "height": height}}

    # ── 3. Modify tower ──
    # First check for bracing independently (handles "use", "apply", "switch", etc.)
    if eng_state.tower_type and "bracing" in text:
        seg_match = re.search(r"segment\s+(\d+)", text) or re.search(r"(\d+)(?:st|nd|rd|th)\s+segment", text)
        btype_raw = (
            "k_bracing" if any(k in text for k in ["k-brac", "k brac", " k ", "k_brac"])
            else "warren" if "warren" in text
            else "hybrid" if "hybrid" in text
            else "x_bracing"
        )
        # Also detect "K" standalone or "X" in context like "change to K"
        if re.search(r"\bk\b", text) and btype_raw == "x_bracing":
            btype_raw = "k_bracing"
        segs = eng_state.params.get("segment_count", 10) if eng_state.params else 10
        if seg_match:
            seg_idx = int(seg_match.group(1)) - 1  # user says "segment 4" → 0-indexed = 3
            return {"tool": "modify_tower", "args": {"segment_index": seg_idx, "bracing_type": btype_raw}}
        top_match = re.search(r"top\s+(\d+)", text)
        bot_match = re.search(r"bottom\s+(\d+)|base\s+(\d+)", text)
        if top_match:
            n = int(top_match.group(1))
            return {"tool": "modify_tower", "args": {"segment_start": segs - n, "segment_end": segs - 1, "bracing_type": btype_raw}}
        elif bot_match:
            n = int((bot_match.group(1) or bot_match.group(2)))
            return {"tool": "modify_tower", "args": {"segment_start": 0, "segment_end": n - 1, "bracing_type": btype_raw}}
        elif "near the top" in text or "at the top" in text or "only at the top" in text:
            return {"tool": "modify_tower", "args": {"segment_start": segs - 3, "segment_end": segs - 1, "bracing_type": btype_raw}}
        elif "near the bottom" in text or "at the base" in text:
            return {"tool": "modify_tower", "args": {"segment_start": 0, "segment_end": 2, "bracing_type": btype_raw}}
        # Global bracing change
        if any(w in text for w in ["change", "modify", "use", "switch", "apply", "set", "update", "convert"]):
            return {"tool": "modify_tower", "args": {"bracing_type": btype_raw}}

    if eng_state.tower_type and any(w in text for w in ["increase", "decrease", "change", "modify", "taller", "shorter", "wider", "make", "set"]):
        if "height" in text or "taller" in text or "shorter" in text:
            h = _extract_number(text, default=None)
            if h:
                return {"tool": "modify_tower", "args": {"height": h}}

    # ── 4. Add mount ──
    if any(w in text for w in ["add", "attach", "mount", "install", "place"]):
        mount_map = {
            "antenna": "antenna",
            "rru": "rru",
            "microwave": "microwave_dish",
            "dish": "microwave_dish",
            "gps": "gps",
            "cable": "cable_tray",
        }
        for kw, mtype in mount_map.items():
            if kw in text:
                tower_h = eng_state.params.get("height", 60) if eng_state.params else 60
                # Determine height from text (skip count number, look for height)
                height_match = re.search(r"at\s+(\d+)\s*m", text)
                h = float(height_match.group(1)) if height_match else tower_h * 0.85
                # Determine azimuth from compass directions
                azimuth = 0.0
                if "north" in text: azimuth = 0.0
                elif "east" in text: azimuth = 90.0
                elif "south" in text: azimuth = 180.0
                elif "west" in text: azimuth = 270.0
                return {"tool": "add_mount", "args": {"type": mtype, "height": h, "azimuth": azimuth}}

    # ── 5. Wind analysis ──
    if any(w in text for w in ["wind", "analysis", "analyze", "simulation", "load", "ice"]):
        args: Dict[str, Any] = {}

        # Ice loading — extract ice_thickness specifically
        if "ice" in text:
            # "ice thickness 25mm", "ice thickness of 25", "25mm ice"
            ice_match = (
                re.search(r"ice\s+thickness\s+(?:of\s+)?(\d+(?:\.\d+)?)", text)
                or re.search(r"(\d+(?:\.\d+)?)\s*mm\s+ice", text)
                or re.search(r"ice[^\d]*(\d+(?:\.\d+)?)", text)
            )
            if ice_match:
                args["ice_thickness"] = float(ice_match.group(1))

        # Wind speed — only extract if "m/s", "mph", "kph", or "at N" pattern present
        speed_match = (
            re.search(r"(\d+(?:\.\d+)?)\s*m/s", text)
            or re.search(r"at\s+(\d+(?:\.\d+)?)\s*m", text)
            or re.search(r"(\d+(?:\.\d+)?)\s*mph", text)
        )
        if speed_match:
            args["service_wind_speed"] = float(speed_match.group(1))
        elif "ice" not in text:
            # No ice, no explicit speed — use first number as speed
            args["service_wind_speed"] = _extract_number(text, default=45.0)

        # Wind direction
        dir_map = {"north": 0.0, "east": 90.0, "south": 180.0, "west": 270.0,
                   "northeast": 45.0, "southeast": 135.0, "southwest": 225.0, "northwest": 315.0}
        for compass, deg in dir_map.items():
            if compass in text:
                args["direction_deg"] = deg
                break

        return {"tool": "run_wind_analysis", "args": args}

    # ── 7. Report ──
    if any(w in text for w in ["report", "pdf", "document"]):
        return {"tool": "generate_report", "args": {}}

    # ── 8. Explain ──
    if any(w in text for w in ["what is", "explain", "describe", "tell me about"]):
        return {"tool": "explain_component", "args": {"id": eng_state.selected_component_id or ""}}

    return None


def _extract_number(text: str, default: Optional[float]) -> float:
    """Extract first number found in text (handles '90m', '50 m/s', etc.)."""
    nums = re.findall(r"(\d+(?:\.\d+)?)", text)
    if nums:
        return float(nums[0])
    return default or 0.0


def _extract_height_from_text(text: str) -> Optional[float]:
    """Context-aware height extractor that avoids misreading component IDs."""
    patterns = [
        r"to\s+(\d+(?:\.\d+)?)\s*m(?:eters?|etres?)?\b",
        r"down\s+to\s+(\d+(?:\.\d+)?)",
        r"up\s+to\s+(\d+(?:\.\d+)?)",
        r"at\s+(\d+(?:\.\d+)?)\s*m(?:eters?|etres?)?\b",
        r"height\s+(?:of\s+)?(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s+m(?:eters?|etres?)\b",
        r"(\d{2,}(?:\.\d+)?)",   # 2+ digit fallback — avoids single-digit IDs like antenna_1
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Agent graph state
# ═══════════════════════════════════════════════════════════════════════════════

class AgentGraphState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    eng_state: EngineeringState
    tool_result: Optional[Dict[str, Any]]
    response: Optional[str]
    tool_called: Optional[str]
    retry_count: int
    user_text: str


# ═══════════════════════════════════════════════════════════════════════════════
# Nodes
# ═══════════════════════════════════════════════════════════════════════════════

def build_llm(model_name: str = "llama3.2:latest") -> ChatOllama:
    return ChatOllama(model=model_name, temperature=0.1, base_url="http://localhost:11434")


def user_input_node(state: AgentGraphState) -> AgentGraphState:
    return state


def engineering_context_node(state: AgentGraphState) -> AgentGraphState:
    eng = state["eng_state"]
    parts = []
    if eng.tower_type:
        parts.append(f"Current tower: {eng.tower_type.upper()}, height={eng.params.get('height')}m")
    else:
        parts.append("No tower created yet.")
    if eng.mounts:
        parts.append("Mounts: " + ", ".join(f"{m.id}({m.type}@{m.height}m)" for m in eng.mounts))
    if eng.selected_component_id:
        parts.append(f"Selected component: {eng.selected_component_id}")
    if eng.wind_result:
        parts.append(f"Last wind: max_defl={eng.wind_result.max_deflection_m}m, stability={eng.wind_result.stability_index}")

    ctx = SystemMessage(content="[ENGINEERING STATE]\n" + "\n".join(parts))
    return {**state, "messages": [ctx]}


def planning_node(state: AgentGraphState) -> AgentGraphState:
    llm = build_llm()
    sys_msg = SystemMessage(content=SYSTEM_PROMPT)
    all_messages = [sys_msg] + state["messages"]

    try:
        response = llm.invoke(all_messages)
        content = response.content or ""
        logger.info(f"LLM raw response: {content[:300]}")
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        content = ""

    # Try to extract tool call from LLM output
    tool_call = _extract_tool_call(content)

    # Fallback: use keyword routing if LLM didn't produce a tool call
    if not tool_call:
        tool_call = _keyword_fallback(state["user_text"], state["eng_state"])
        if tool_call:
            logger.info(f"Using keyword fallback: {tool_call['tool']}")
            # Generate a brief response since LLM didn't provide one
            content = content or f"On it! Running {tool_call['tool'].replace('_', ' ')}..."

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "tool_called": tool_call["tool"] if tool_call else None,
        "tool_result": {"pending_args": tool_call["args"]} if tool_call else None,
        "response": content if not tool_call else None,
    }


def tool_execution_node(state: AgentGraphState) -> AgentGraphState:
    tool_name = state.get("tool_called")
    if not tool_name or tool_name not in TOOLS:
        return {**state, "tool_result": {"error": f"Unknown tool: {tool_name}"}}

    args = state.get("tool_result", {}).get("pending_args", {})
    eng_state = state["eng_state"]

    try:
        result = TOOLS[tool_name](eng_state, args)
        logger.info(f"Tool {tool_name} result keys: {list(result.keys())}")
    except Exception as e:
        logger.error(f"Tool {tool_name} error: {e}")
        result = {"error": str(e)}

    return {**state, "tool_result": result}


def reflection_node(state: AgentGraphState) -> AgentGraphState:
    tool_result = state.get("tool_result", {})
    tool_name = state.get("tool_called", "unknown")

    if "error" in tool_result and state.get("retry_count", 0) < 1:
        err_msg = SystemMessage(content=f"[TOOL ERROR] {tool_name}: {tool_result['error']}. Inform the user clearly.")
        return {
            **state,
            "messages": [err_msg],
            "retry_count": state.get("retry_count", 0) + 1,
            "tool_called": None,
            "tool_result": None,
        }

    # Build concise result summary (exclude geometry to keep prompt short)
    summary_data = {k: v for k, v in tool_result.items()
                    if k not in ("geometry", "deformed_geometry", "components", "mount_geometries")}
    result_summary = json.dumps(summary_data, indent=2, default=str)[:800]

    try:
        llm = build_llm()
        commentary_msgs = [
            SystemMessage(content=SYSTEM_PROMPT),
            *state["messages"],
            SystemMessage(
                content=f"[TOOL '{tool_name}' COMPLETED]\n{result_summary}\n\n"
                        f"Give the user a clear 2-3 sentence engineering response. "
                        f"Confirm what was done, mention key values, and add one useful engineering insight. "
                        f"Do NOT output any JSON or tool calls — just plain text."
            ),
        ]
        response = llm.invoke(commentary_msgs)
        reply = response.content or _default_reply(tool_name, tool_result)
    except Exception as e:
        logger.error(f"Reflection LLM failed: {e}")
        reply = _default_reply(tool_name, tool_result)

    return {**state, "response": reply}


def response_generation_node(state: AgentGraphState) -> AgentGraphState:
    # Ensure response is never empty
    if not state.get("response"):
        return {**state, "response": "I've processed your request. Let me know if you need any adjustments."}
    return state


# ═══════════════════════════════════════════════════════════════════════════════
# Default replies when LLM fails
# ═══════════════════════════════════════════════════════════════════════════════

def _default_reply(tool_name: str, result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"There was an issue: {result['error']}"
    replies = {
        "create_tower": lambda r: f"Tower created successfully! {r.get('tower_type','').upper()} tower, height={r.get('params',{}).get('height','?')}m. You should see it in the 3D viewer now.",
        "modify_tower": lambda r: f"Tower updated. New parameters: {r.get('params',{})}.",
        "add_mount": lambda r: f"Added {r.get('mount',{}).get('type','equipment')} — ID: {r.get('mount',{}).get('id','?')} at {r.get('mount',{}).get('height','?')}m.",
        "remove_mount": lambda r: f"Removed component {r.get('id','?')} from the tower.",
        "update_mount": lambda r: f"Updated {r.get('mount',{}).get('id','?')} successfully.",
        "run_wind_analysis": lambda r: f"Wind analysis complete. Max deflection: {r.get('max_deflection_m','?')}m, Stability index: {r.get('stability_index','?')}. Check the Wind Sim panel for full results.",
        "generate_report": lambda _: "Report is ready! Click the Download PDF button in the Wind Sim panel.",
        "explain_component": lambda r: r.get("description", "This is a structural component of the tower."),
    }
    fn = replies.get(tool_name)
    return fn(result) if fn else "Action completed successfully."


# ═══════════════════════════════════════════════════════════════════════════════
# Routing
# ═══════════════════════════════════════════════════════════════════════════════

def route_after_planning(state: AgentGraphState) -> str:
    if state.get("tool_called"):
        return "tool_execution"
    return "respond"


def route_after_reflection(state: AgentGraphState) -> str:
    if state.get("retry_count", 0) > 0 and not state.get("tool_called") and not state.get("response"):
        return "planning"
    return "respond"


# ═══════════════════════════════════════════════════════════════════════════════
# Build graph
# ═══════════════════════════════════════════════════════════════════════════════

def build_agent_graph():
    graph = StateGraph(AgentGraphState)
    graph.add_node("user_input", user_input_node)
    graph.add_node("engineering_context", engineering_context_node)
    graph.add_node("planning", planning_node)
    graph.add_node("tool_execution", tool_execution_node)
    graph.add_node("reflection", reflection_node)
    graph.add_node("respond", response_generation_node)

    graph.set_entry_point("user_input")
    graph.add_edge("user_input", "engineering_context")
    graph.add_edge("engineering_context", "planning")
    graph.add_conditional_edges("planning", route_after_planning, {
        "tool_execution": "tool_execution",
        "respond": "respond",
    })
    graph.add_edge("tool_execution", "reflection")
    graph.add_conditional_edges("reflection", route_after_reflection, {
        "planning": "planning",
        "respond": "respond",
    })
    graph.add_edge("respond", END)
    return graph.compile()


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON tool call block from LLM response."""
    # Match ```json ... ``` blocks
    for pattern in [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "tool" in data and "args" in data:
                    return data
            except json.JSONDecodeError:
                pass
    # Try bare JSON
    try:
        data = json.loads(text.strip())
        if "tool" in data and "args" in data:
            return data
    except Exception:
        pass
    # Try to find JSON object anywhere in text
    match = re.search(r'\{[^{}]*"tool"[^{}]*"args"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if "tool" in data and "args" in data:
                return data
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are TOWER-AI, an expert AI co-pilot for telecom tower structural engineers.

Your persona:
- You think like a senior structural engineer with 20+ years in telecom towers.
- You speak clearly, confidently, and technically when needed, but also simply when the user is exploring.
- You proactively apply engineering judgment — you never wait to be told obvious defaults.
- You warn about bad engineering choices politely, but still execute them if the user insists.

Your capabilities:
- Create and modify 3D parametric tower models (Lattice, Guyed, Monopole).
- Add, move, rotate, and remove mounted equipment (antennas, RRUs, dishes, GPS).
- Run simplified wind load analysis (12-direction, 30° intervals).
- Maintain engineering state persistently across the conversation.
- Generate engineering PDF reports.
- Explain any selected structural component.

Engineering intelligence you apply automatically:
- Taller towers need wider bases and stronger bracing.
- More mounted equipment increases wind load area.
- Guy wires dramatically reduce bending moments in guyed towers.
- Lattice towers distribute loads more efficiently than monopoles.
- Tower sway can be reduced by: adding guy wires, widening base, reducing equipment load, or changing bracing type.

You respond to natural language. You ALWAYS call a tool when an engineering action is required.
Never just describe what you'll do — execute it by calling the tool.

When outputting a tool call, respond ONLY with a JSON block in this exact format:
```json
{
  "tool": "<tool_name>",
  "args": { ... }
}
```

Available tools: create_tower, modify_tower, add_mount, remove_mount, update_mount,
run_wind_analysis, generate_report, select_component, explain_component,
sync_viewer, retrieve_session_state

After calling a tool, you'll receive the result. Then provide a brief engineering commentary to the user.

If the user's request is conversational or asks for explanation (no action needed), respond normally without a tool call.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Agent graph state
# ═══════════════════════════════════════════════════════════════════════════════

class AgentGraphState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    eng_state: EngineeringState
    tool_result: Optional[Dict[str, Any]]
    response: Optional[str]
    tool_called: Optional[str]
    retry_count: int


# ═══════════════════════════════════════════════════════════════════════════════
# Nodes
# ═══════════════════════════════════════════════════════════════════════════════

def build_llm(model_name: str = "llama3.2:latest") -> ChatOllama:
    return ChatOllama(model=model_name, temperature=0.2, base_url="http://localhost:11434")


def user_input_node(state: AgentGraphState) -> AgentGraphState:
    """Entry node – just passes through. Message already added before graph call."""
    return state


def engineering_context_node(state: AgentGraphState) -> AgentGraphState:
    """Inject current engineering state as context into the message list."""
    eng = state["eng_state"]
    context_parts = []

    if eng.tower_type:
        context_parts.append(f"Current tower: {eng.tower_type.upper()}, height={eng.params.get('height')}m")
    else:
        context_parts.append("No tower created yet.")

    if eng.mounts:
        mount_summary = ", ".join(f"{m.id}({m.type}@{m.height}m)" for m in eng.mounts)
        context_parts.append(f"Mounted equipment: {mount_summary}")

    if eng.selected_component_id:
        context_parts.append(f"User has selected component: {eng.selected_component_id}")

    if eng.wind_result:
        context_parts.append(
            f"Last wind analysis: max deflection={eng.wind_result.max_deflection_m}m, "
            f"stability index={eng.wind_result.stability_index}"
        )

    context_msg = SystemMessage(content="[ENGINEERING CONTEXT]\n" + "\n".join(context_parts))
    return {**state, "messages": [context_msg]}


def planning_node(state: AgentGraphState) -> AgentGraphState:
    """Ask the LLM to decide what tool to call (or respond directly)."""
    llm = build_llm()
    sys_msg = SystemMessage(content=SYSTEM_PROMPT)
    all_messages = [sys_msg] + state["messages"]

    response = llm.invoke(all_messages)
    content = response.content

    # Try to extract a tool call from the response
    tool_call = _extract_tool_call(content)

    return {
        **state,
        "messages": [AIMessage(content=content)],
        "tool_called": tool_call["tool"] if tool_call else None,
        "tool_result": {"pending_args": tool_call["args"]} if tool_call else None,
        "response": content if not tool_call else None,
    }


def tool_execution_node(state: AgentGraphState) -> AgentGraphState:
    """Execute the selected tool."""
    tool_name = state.get("tool_called")
    if not tool_name or tool_name not in TOOLS:
        return {**state, "tool_result": {"error": f"Unknown tool: {tool_name}"}}

    args = state.get("tool_result", {}).get("pending_args", {})
    eng_state = state["eng_state"]

    try:
        result = TOOLS[tool_name](eng_state, args)
    except Exception as e:
        result = {"error": str(e)}

    return {**state, "tool_result": result}


def reflection_node(state: AgentGraphState) -> AgentGraphState:
    """After tool execution, ask LLM to generate user-facing commentary."""
    tool_result = state.get("tool_result", {})
    tool_name = state.get("tool_called", "")

    if "error" in tool_result and state.get("retry_count", 0) < 2:
        # Inject error and let planning retry
        error_msg = SystemMessage(content=f"[TOOL ERROR] {tool_name} failed: {tool_result['error']}. Try a different approach or ask the user.")
        return {
            **state,
            "messages": [error_msg],
            "retry_count": state.get("retry_count", 0) + 1,
            "tool_called": None,
            "tool_result": None,
        }

    # Build result summary for LLM
    result_summary = json.dumps(
        {k: v for k, v in tool_result.items() if k not in ("geometry", "deformed_geometry", "components")},
        indent=2, default=str
    )[:1200]  # truncate large geometry

    llm = build_llm()
    commentary_prompt = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"],
        SystemMessage(content=f"[TOOL RESULT from {tool_name}]\n{result_summary}\n\nNow give the user a clear, engineering-quality explanation of what was done and any important observations. Be concise."),
    ]
    response = llm.invoke(commentary_prompt)
    return {**state, "response": response.content}


def response_generation_node(state: AgentGraphState) -> AgentGraphState:
    """Final node – response is already in state.response."""
    return state


# ═══════════════════════════════════════════════════════════════════════════════
# Routing
# ═══════════════════════════════════════════════════════════════════════════════

def route_after_planning(state: AgentGraphState) -> str:
    if state.get("tool_called"):
        return "tool_execution"
    return "respond"


def route_after_reflection(state: AgentGraphState) -> str:
    # If retry triggered (tool_called cleared, error in previous result)
    if state.get("retry_count", 0) > 0 and state.get("tool_called") is None and state.get("response") is None:
        return "planning"
    return "respond"


# ═══════════════════════════════════════════════════════════════════════════════
# Build graph
# ═══════════════════════════════════════════════════════════════════════════════

def build_agent_graph():
    graph = StateGraph(AgentGraphState)

    graph.add_node("user_input", user_input_node)
    graph.add_node("engineering_context", engineering_context_node)
    graph.add_node("planning", planning_node)
    graph.add_node("tool_execution", tool_execution_node)
    graph.add_node("reflection", reflection_node)
    graph.add_node("respond", response_generation_node)

    graph.set_entry_point("user_input")
    graph.add_edge("user_input", "engineering_context")
    graph.add_edge("engineering_context", "planning")
    graph.add_conditional_edges("planning", route_after_planning, {
        "tool_execution": "tool_execution",
        "respond": "respond",
    })
    graph.add_edge("tool_execution", "reflection")
    graph.add_conditional_edges("reflection", route_after_reflection, {
        "planning": "planning",
        "respond": "respond",
    })
    graph.add_edge("respond", END)

    return graph.compile()


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON tool call block from LLM response."""
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if "tool" in data and "args" in data:
                return data
        except json.JSONDecodeError:
            pass
    # Try inline JSON
    try:
        data = json.loads(text.strip())
        if "tool" in data and "args" in data:
            return data
    except Exception:
        pass
    return None
