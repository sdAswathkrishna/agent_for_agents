# Agent-for-Agents (Lyzr ADK)

> A meta-agent that builds other AI agents.
> Describe what you want — get production-ready Lyzr ADK code.

Built with **Lyzr ADK** · Packaged as a **GitAgent** · Rebuilt from AWS AgentCore + Strands SDK

[![GitAgent](https://img.shields.io/badge/GitAgent-standard-purple)](https://gitagent.sh)
[![Lyzr ADK](https://img.shields.io/badge/Lyzr-ADK-blue)](https://docs.lyzr.ai/lyzr-adk/overview)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What It Does

You describe the agent you want to build. This system guides you through a
**6-state conversation**, generates an **architecture diagram**, then produces
**ready-to-run Lyzr ADK Python code** — complete with tools, README, and .env.example.

```
You: "I want a customer support agent that looks up orders and drafts emails"
            ↓
[OrchestratorAgent]  →  6-state requirement gathering
            ↓
[OrchestratorAgent]  →  architecture diagram (PNG)
            ↓
[CodeGeneratorAgent] →  agent.py + tools/*.py + README.md
            ↓
Download ZIP → run immediately
```

---

## Architecture

| Component | Strands Version | Lyzr ADK Version |
|---|---|---|
| Agents | 2 Docker containers on AgentCore | 2 Python objects in-process |
| Backend | AWS Chalice → Lambda | FastAPI → uvicorn |
| Memory | AWS AgentCore MemorySessionManager | Lyzr `session_id` param |
| Tools | MCP servers (native MCPClient) | Python functions (add_tool) |
| Storage | DynamoDB + S3 | SQLite + local filesystem |
| Auth | AWS Cognito JWT | None (demo mode) |
| Structured output | Regex parse `<state>JSON</state>` | Pydantic `response_model` |
| Deploy | `agentcore launch` (5-10 min) | `python main.py` (instant) |

---

## Quick Start

### 1. Prerequisites

```bash
python >= 3.11
```

### 2. Install

```bash
cd agent-for-agents-lyzr
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env:
#   LYZR_API_KEY=...     (get at studio.lyzr.ai/account)
#   OPENAI_API_KEY=...
```

### 4. Run CLI (simplest)

```bash
python main.py
```

Then chat naturally. When requirements are gathered, type `generate`.

### 5. Run API Server

```bash
uvicorn main_api:app --reload --port 8000
```

API docs: http://localhost:8000/docs

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects` | Create a new agent project |
| GET | `/projects` | List all projects |
| POST | `/projects/{id}/chat` | Send message to orchestrator |
| POST | `/projects/{id}/chat/stream` | Streaming SSE chat |
| POST | `/projects/{id}/generate` | Generate Lyzr ADK code |
| GET | `/projects/{id}/generate/status` | Poll generation status |
| GET | `/projects/{id}/artifacts` | List generated files |
| GET | `/projects/{id}/artifacts/{path}` | Get file content |
| GET | `/projects/{id}/download` | Download ZIP |
| POST | `/projects/{id}/refine` | Refine generated code |
| POST | `/projects/{id}/approve` | Approve and close |

---

## Run as GitAgent

```bash
npm install -g @open-gitagent/gitagent

# With Lyzr adapter
gitagent lyzr run -d . -p "I want to build a customer support agent"

# With Claude adapter
gitagent run -d . -a claude

# Export as system prompt
gitagent export --format system-prompt
```

---

## Diagram Generation (MCP Integration Test)

This project deliberately tests Lyzr ADK's ability to connect with external MCP servers.
The `tools/diagram_tool.py` implements a **manual MCP bridge** — the key pattern
difference between Strands (native MCPClient) and Lyzr ADK.

**To enable MCP diagrams:**
```bash
# Install uvx (if not already installed)
pip install uv

# Set in .env:
DIAGRAM_TOOL_MODE=mcp
```

**Fallback chain:**
1. `mcp` mode → spawn `awslabs.aws-diagrams-mcp-server@latest`
2. `local` mode → Python `diagrams` library
3. Stub → text description file

See `tools/diagram_tool.py` for the full bridge implementation and inline comparison
notes vs Strands' native `MCPClient`.

---

## Project Structure

```
agent-for-agents-lyzr/
├── agent.yaml                    # GitAgent manifest
├── SOUL.md                       # Agent identity
├── SKILL.md                      # Agent capabilities
├── RULES.md                      # Hard constraints
├── main.py                       # CLI entry point
├── main_api.py                   # FastAPI backend
│
├── agents/
│   ├── orchestrator.py           # OrchestratorAgent (6-state conversation)
│   └── code_generator.py         # CodeGeneratorAgent (Lyzr ADK code output)
│
├── tools/
│   ├── diagram_tool.py           # MCP bridge → diagram generation
│   └── lyzr_docs_tool.py         # Lyzr docs search + templates
│
├── models/
│   └── schemas.py                # Pydantic models (OrchestratorOutput, etc.)
│
├── storage/
│   ├── db.py                     # SQLite (replaces DynamoDB)
│   └── artifacts.py              # Local filesystem (replaces S3)
│
├── prompts/
│   ├── orchestrator_system.txt   # 6-state conversation prompt
│   └── code_generator_system.txt # Lyzr ADK code generation rules
│
├── skills/
│   ├── gather-requirements/SKILL.md
│   └── generate-agent-code/SKILL.md
│
├── docs/
│   ├── comparison.md             # Strands vs Lyzr ADK (detailed)
│   ├── strands-architecture.md   # Original Strands app reference
│   ├── lyzr-adk-reference.md     # Lyzr ADK code snippets
│   └── gitagent-reference.md     # GitAgent schema reference
│
├── artifacts/                    # Generated agent code saved here
├── knowledge/                    # Add RAG documents here
├── .env.example
└── requirements.txt
```

---

## Comparison: Strands vs Lyzr ADK

See [`docs/comparison.md`](docs/comparison.md) for the full breakdown.

**Quick highlights from rebuilding this app:**

| Dimension | Strands wins | Lyzr ADK wins |
|---|---|---|
| MCP support | ✅ Native `MCPClient` | — |
| Structured output | — | ✅ `response_model=Pydantic` |
| Setup speed | — | ✅ 10 min vs 2-3 hours |
| Deployment | ✅ Enterprise containers | — |
| Memory API | — | ✅ Just `session_id=` |
| Responsible AI | — | ✅ `reflection=True` built-in |
| GitAgent | — | ✅ Native adapter |

---

## Built By

Rebuilt from 6 months of production experience with AWS AgentCore + Strands SDK
(17 agents deployed). Part of the [Lyzr GitAgent Challenge](https://www.lyzr.ai).

---

## License

MIT
