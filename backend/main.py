"""
FastAPI main application.
REST + WebSocket endpoints for the Tower Engineering Assistant.
Direct pipeline: intent detection → tool execution → LLM response → UI sync.
"""
from __future__ import annotations
import asyncio
import json
import re
import uuid
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import base64

from models.state import EngineeringState
from tools.tower_tools import tool_sync_viewer, TOOLS
from engineering.report_generator import generate_pdf_report
from engineering.geometry import apply_wind_deformation
from agents.tower_agent import _keyword_fallback, _extract_tool_call, build_llm, SYSTEM_PROMPT, _default_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Tower Engineering AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory session store ────────────────────────────────────────────────────
sessions: Dict[str, EngineeringState] = {}


def get_or_create_session(session_id: str) -> EngineeringState:
    if session_id not in sessions:
        s = EngineeringState(session_id=session_id)
        sessions[session_id] = s
    return sessions[session_id]


# ── Direct AI pipeline (no LangGraph state complexity) ────────────────────────

def detect_tool_call(user_text: str, state: EngineeringState) -> Optional[Dict[str, Any]]:
    """
    Detect which tool to call.
    1. Try LLM with structured prompt.
    2. Fall back to keyword routing if LLM fails or gives no tool call.
    """
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = build_llm()
        # Build a concise context string
        ctx = ""
        if state.tower_type:
            ctx = f"[Current: {state.tower_type.upper()} tower, height={state.params.get('height')}m"
            if state.mounts:
                ctx += f", {len(state.mounts)} mounts: {', '.join(m.id for m in state.mounts)}"
            ctx += "]"
        else:
            ctx = "[No tower yet]"

        prompt = f"{ctx}\nUser: {user_text}"
        msgs = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = llm.invoke(msgs)
        content = response.content or ""
        logger.info(f"LLM response (first 200): {content[:200]}")
        tool_call = _extract_tool_call(content)
        if tool_call:
            logger.info(f"LLM gave tool call: {tool_call['tool']}")
            return tool_call
    except Exception as e:
        logger.warning(f"LLM intent detection failed: {e}")

    # Keyword fallback
    tool_call = _keyword_fallback(user_text, state)
    if tool_call:
        logger.info(f"Keyword fallback: {tool_call['tool']}")
    return tool_call


def generate_ai_response(user_text: str, state: EngineeringState,
                          tool_name: Optional[str], tool_result: Optional[Dict]) -> str:
    """Generate a natural language response using LLM, with smart fallback."""
    default = _default_reply(tool_name, tool_result) if (tool_name and tool_result) else None

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = build_llm()
        if tool_name and tool_result and "error" not in tool_result:
            # Summarize result (exclude large geometry blobs)
            summary = {k: v for k, v in tool_result.items()
                       if k not in ("geometry", "components", "mount_geometries", "deformed_geometry")}
            result_str = json.dumps(summary, default=str)[:600]
            prompt = (
                f"User asked: \"{user_text}\"\n"
                f"Tool '{tool_name}' completed with result: {result_str}\n\n"
                f"Give a 2-3 sentence engineering response confirming what was done, "
                f"mentioning key values, and one useful insight. Plain text only, no JSON."
            )
        elif tool_name and tool_result and "error" in tool_result:
            prompt = f"Tool '{tool_name}' failed: {tool_result['error']}. Tell the user what went wrong in 1 sentence."
        else:
            # Conversational — no tool
            ctx = f"Tower: {state.tower_type or 'none'}, height={state.params.get('height') if state.params else 'N/A'}m" if state.tower_type else "No tower created."
            prompt = f"[Context: {ctx}]\nUser: {user_text}\n\nReply as TOWER-AI, a structural engineering assistant. Be concise and helpful."

        msgs = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = llm.invoke(msgs)
        reply = (response.content or "").strip()
        # Strip any accidental JSON/tool calls from response
        reply = re.sub(r"```.*?```", "", reply, flags=re.DOTALL).strip()
        if reply:
            return reply
    except Exception as e:
        logger.warning(f"LLM response generation failed: {e}")

    return default or "I've processed your request. What would you like to do next?"


def process_chat_sync(user_text: str, state: EngineeringState) -> Dict[str, Any]:
    """
    Synchronous chat processing pipeline:
    detect_tool → execute_tool → generate_response
    Returns dict with tool_name, tool_result, response, needs_geometry_update, etc.
    """
    # 1. Detect what tool to call (LLM + fallback)
    tool_call = detect_tool_call(user_text, state)
    tool_name: Optional[str] = None
    tool_result: Optional[Dict] = None

    # 2. Execute tool
    if tool_call:
        tool_name = tool_call["tool"]
        tool_args = tool_call.get("args", {})
        logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
        try:
            tool_result = TOOLS[tool_name](state, tool_args)
            logger.info(f"Tool result keys: {list(tool_result.keys())}")

            # Short-circuit on clarification requests — skip geometry update and LLM
            if tool_result.get("status") == "needs_clarification":
                q = tool_result["question"]
                state.conversation_history.append({"role": "user", "content": user_text})
                state.conversation_history.append({"role": "assistant", "content": q})
                return {"tool_name": None, "tool_result": None, "response": q}

            # Handle "add N antennas" — repeat add_mount  
            count_match = re.search(r"\b([2-9]|10)\s+(antenna|rru|dish|microwave)", user_text.lower())
            if tool_name == "add_mount" and count_match and "error" not in tool_result:
                count = int(count_match.group(1))
                mtype = tool_result.get("mount", {}).get("type", "antenna")
                mh = tool_result.get("mount", {}).get("height", state.params.get("height", 60) * 0.85 if state.params else 51)
                for i in range(1, count):
                    az = i * 360 / count
                    TOOLS["add_mount"](state, {"type": mtype, "height": mh, "azimuth": az})

        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            tool_result = {"error": str(e)}

    # 3. Generate AI response
    response = generate_ai_response(user_text, state, tool_name, tool_result)

    # 4. Save to history
    state.conversation_history.append({"role": "user", "content": user_text})
    state.conversation_history.append({"role": "assistant", "content": response})

    return {
        "tool_name": tool_name,
        "tool_result": tool_result,
        "response": response,
    }


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(sessions)}


@app.post("/session/new")
async def new_session():
    sid = str(uuid.uuid4())
    sessions[sid] = EngineeringState(session_id=sid)
    return {"session_id": sid}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    state = get_or_create_session(session_id)
    return state.model_dump()


@app.get("/session/{session_id}/report")
async def download_report(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found. Has it expired or been reset?")
    state = sessions[session_id]
    pdf_bytes = generate_pdf_report(state.model_dump())
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=tower_report_{session_id[:8]}.pdf",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


@app.get("/session/{session_id}/geometry")
async def get_geometry(session_id: str):
    state = get_or_create_session(session_id)
    result = tool_sync_viewer(state, {})
    return result


@app.post("/session/{session_id}/select")
async def select_component(session_id: str, body: dict):
    state = get_or_create_session(session_id)
    comp_id = body.get("id")
    state.selected_component_id = comp_id
    return {"selected": comp_id}


@app.get("/session/{session_id}/wind/deformed")
async def get_deformed(session_id: str, intensity: float = 1.0, direction: float = 0.0):
    """Return deformed geometry for a given wind intensity (0-1 scale)."""
    state = get_or_create_session(session_id)
    if not state.tower_type or not state.wind_result:
        raise HTTPException(status_code=400, detail="Run wind analysis first.")

    from tools.tower_tools import _gen_geometry
    base_geo = _gen_geometry(state.tower_type, state.params)
    max_defl = state.wind_result.max_deflection_m * intensity
    h = state.params.get("height", 60)
    deformed = apply_wind_deformation(base_geo, max_defl, h, direction)
    return {"original": base_geo, "deformed": deformed}


# ── WebSocket ──────────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self.active[session_id] = ws

    def disconnect(self, session_id: str):
        self.active.pop(session_id, None)

    async def send(self, session_id: str, data: dict):
        ws = self.active.get(session_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(session_id)

    async def broadcast(self, data: dict):
        dead = []
        for sid, ws in self.active.items():
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(sid)
        for sid in dead:
            self.disconnect(sid)


manager = ConnectionManager()


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    state = get_or_create_session(session_id)

    try:
        # Send initial state
        await manager.send(session_id, {
            "type": "session_init",
            "payload": tool_sync_viewer(state, {}),
        })

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "chat":
                user_text = msg.get("content", "")
                await manager.send(session_id, {"type": "thinking", "payload": {}})

                try:
                    # Run the direct pipeline in a thread (LLM calls are blocking)
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: process_chat_sync(user_text, state)
                    )

                    tool_name = result["tool_name"]
                    tool_result = result["tool_result"] or {}
                    ai_response = result["response"]

                    logger.info(f"Chat done. tool={tool_name}, reply_len={len(ai_response)}")

                    # Send AI text response
                    await manager.send(session_id, {
                        "type": "ai_response",
                        "payload": {"content": ai_response, "tool_called": tool_name},
                    })

                    # Send geometry update for structural or equipment changes
                    if tool_name in ("create_tower", "modify_tower", "add_mount", "remove_mount", "update_mount"):
                        viewer_update = tool_sync_viewer(state, {})
                        await manager.send(session_id, {
                            "type": "geometry_update",
                            "payload": viewer_update,
                        })

                    # Send wind analysis results
                    if tool_name == "run_wind_analysis" and "load_cases" in tool_result:
                        await manager.send(session_id, {
                            "type": "wind_analysis_result",
                            "payload": {
                                **tool_result,
                                "wind_params": state.wind_params.model_dump(),
                            },
                        })

                    # Report ready — generate PDF on the backend and deliver inline via WebSocket
                    if tool_name == "generate_report":
                        try:
                            pdf_bytes = generate_pdf_report(state.model_dump())
                            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                            await manager.send(session_id, {
                                "type": "report_ready",
                                "payload": {
                                    "session_id": session_id,
                                    "pdf_base64": pdf_b64,
                                    "filename": f"tower_report_{session_id[:8]}.pdf",
                                },
                            })
                        except Exception as pdf_err:
                            logger.error(f"PDF generation error: {pdf_err}")
                            await manager.send(session_id, {
                                "type": "report_ready",
                                "payload": {"session_id": session_id},
                            })

                except Exception as e:
                    logger.error(f"Chat processing error: {e}", exc_info=True)
                    await manager.send(session_id, {
                        "type": "error",
                        "payload": {"message": str(e)},
                    })

            elif msg_type == "select_component":
                comp_id = msg.get("id")
                state.selected_component_id = comp_id
                await manager.send(session_id, {
                    "type": "component_selected",
                    "payload": {"id": comp_id},
                })

            elif msg_type == "wind_slider":
                if state.wind_result and state.tower_type:
                    intensity = float(msg.get("intensity", 1.0))
                    direction = float(msg.get("direction", state.wind_result.critical_direction))
                    from tools.tower_tools import _gen_geometry
                    base_geo = _gen_geometry(state.tower_type, state.params)
                    max_defl = state.wind_result.max_deflection_m * intensity
                    h = state.params.get("height", 60)
                    deformed = apply_wind_deformation(base_geo, max_defl, h, direction)
                    await manager.send(session_id, {
                        "type": "wind_deformation_update",
                        "payload": {"deformed": deformed, "intensity": intensity},
                    })

            elif msg_type == "ping":
                await manager.send(session_id, {"type": "pong"})

            elif msg_type == "request_report":
                # Button-triggered report: generate PDF and deliver as base64 over WebSocket
                # This avoids all CORS and browser-navigation issues
                try:
                    pdf_bytes = generate_pdf_report(state.model_dump())
                    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                    await manager.send(session_id, {
                        "type": "report_ready",
                        "payload": {
                            "session_id": session_id,
                            "pdf_base64": pdf_b64,
                            "filename": f"tower_report_{session_id[:8]}.pdf",
                        },
                    })
                except Exception as pdf_err:
                    logger.error(f"PDF generation error: {pdf_err}")
                    await manager.send(session_id, {
                        "type": "error",
                        "payload": {"message": f"Report generation failed: {pdf_err}"},
                    })

    except WebSocketDisconnect:
        manager.disconnect(session_id)
