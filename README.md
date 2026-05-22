# AI-OTDIQ — Telecom Tower Engineering Assistant

An **agentic AI application** for telecom tower structural engineers.
Build, modify, simulate, and analyze telecom towers using natural language — powered by a local LLM (Ollama), LangGraph orchestration, and a real-time 3D viewer.

---

## Architecture

```
Frontend (React + TypeScript + React Three Fiber)
    ↕  WebSocket + REST
Backend (FastAPI + LangGraph)
    ↕
Ollama (Local LLM: qwen2.5-coder / llama3)
```

---

## Tech Stack

| Layer      | Technology                              |
|------------|-----------------------------------------|
| Frontend   | React 18, TypeScript, Vite              |
| 3D Viewer  | React Three Fiber, Three.js, Drei       |
| State      | Zustand + Immer                         |
| Charts     | Recharts                                |
| Styling    | TailwindCSS v4                          |
| Backend    | FastAPI, Python 3.11+                   |
| AI Agent   | LangGraph, LangChain, Ollama            |
| Reports    | fpdf2                                   |
| Realtime   | WebSocket (native)                      |

---

## Prerequisites

1. **Python 3.10+**
2. **Node.js 18+**
3. **Ollama** running locally → https://ollama.com

### Pull a model (pick one):
```bash
ollama pull qwen2.5-coder:7b       # Recommended – good tool-calling
ollama pull llama3.1:8b            # Alternative
ollama pull deepseek-coder:6.7b    # Code-focused alternative
```

---

## Quick Start

### Option A: Manual (Recommended for development)

**Terminal 1 – Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Terminal 2 – Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open → **http://localhost:5173**

---

### Option B: Docker Compose

> Requires Ollama running on host machine (not in Docker)

```bash
docker-compose up --build
```

---

## Example Prompts

```
"Create a 90m lattice tower with X-bracing"
"Make it taller — 120 meters"
"Add 3 antennas near the top"
"Add a microwave dish at 70m facing north"
"Run wind analysis at 50 m/s from the west"
"What is the selected component?"
"Make the tower more stable"
"Change to K-bracing"
"Remove antenna_2"
"Generate an engineering report"
"Show wind impact with heavy ice loading"
"Create a 45m monopole tower"
"Build a guyed tower 150m tall"
```

---

## Project Structure

```
AI-OTDIQ/
├── backend/
│   ├── main.py                 # FastAPI app + WebSocket
│   ├── requirements.txt
│   ├── agents/
│   │   └── tower_agent.py      # LangGraph agent workflow
│   ├── tools/
│   │   └── tower_tools.py      # 12 engineering tools
│   ├── engineering/
│   │   ├── geometry.py         # Parametric 3D geometry generators
│   │   ├── wind_analysis.py    # Wind load calculations
│   │   └── report_generator.py # PDF report
│   └── models/
│       └── state.py            # Pydantic state models
└── frontend/
    ├── src/
    │   ├── App.tsx             # Main layout
    │   ├── components/
    │   │   ├── TowerViewer.tsx  # React Three Fiber 3D viewer
    │   │   ├── ChatPanel.tsx    # AI chat interface
    │   │   ├── WindSimPanel.tsx # Wind simulation controls + charts
    │   │   ├── PropertyInspector.tsx
    │   │   └── ComponentTree.tsx
    │   ├── store/
    │   │   └── appStore.ts     # Zustand global state
    │   ├── hooks/
    │   │   └── useWebSocket.ts # WS client + message handler
    │   └── types/
    │       └── index.ts        # TypeScript interfaces
    └── vite.config.ts
```

---

## LangGraph Agent Flow

```
User Input
    → Engineering Context Injection
    → LLM Planning (intent + tool selection)
    → Tool Execution (one of 12 tools)
    → Reflection (error retry if needed)
    → Response Generation
    → WebSocket UI Sync
```

## Available Tools

| Tool | Action |
|------|--------|
| `create_tower` | Parametric tower generation |
| `modify_tower` | Modify existing tower params |
| `add_mount` | Add equipment to tower |
| `remove_mount` | Remove a mounted component |
| `update_mount` | Move/rotate equipment |
| `run_wind_analysis` | 12-direction wind analysis |
| `generate_report` | Trigger PDF download |
| `select_component` | Set active component |
| `explain_component` | Get component description |
| `sync_viewer` | Rebuild full viewer state |
| `retrieve_session_state` | Return full session data |

---

## Wind Analysis

- 12-direction analysis (0°, 30°, 60°, ..., 330°)
- Simplified TIA-222-inspired calculations
- Outputs: base shear, overturning moment, tip deflection, stress ratio
- Visual: original + deformed tower superimposed in 3D
- Realtime intensity slider updates deflection live
- Wind pressure / deflection charts via Recharts
- PDF report with all load cases

---

## Changing the Ollama Model

Edit `backend/agents/tower_agent.py`:

```python
def build_llm(model_name: str = "qwen2.5-coder:7b") -> ChatOllama:
```

Change the default model name to any pulled Ollama model.

---

## Notes

- Session state is in-memory. Restart backend = new session.
- All geometry is procedurally generated (no external 3D assets).
- Wind analysis is simplified for POC — not for production structural design.
- PDF reports are generated server-side and downloaded via `/session/{id}/report`.
