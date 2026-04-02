# SKILL — Agent-for-Agents

## Core Capability

End-to-end AI agent creation: from a natural-language description to
deployable Lyzr ADK Python code, via a structured multi-agent pipeline.

---

## Skill: Build an AI Agent

**Trigger**: User describes an agent they want to create.

**Pipeline**:
1. `OrchestratorAgent` runs a 6-state requirement-gathering conversation
2. `OrchestratorAgent` calls `generate_diagram` tool → architecture PNG
3. User confirms requirements
4. `CodeGeneratorAgent` generates complete Lyzr ADK code package
5. Files saved → ZIP download available

**Output**: Runnable Lyzr ADK agent code (ZIP)

---

## Skill: Gather Requirements (6-State Conversation)

**Agent**: OrchestratorAgent
**States**:

| State | Goal |
|-------|------|
| `intro` | Understand the agent's core purpose and target users |
| `requirements` | Capture tools, triggers, and integrations |
| `tech` | Confirm Lyzr ADK + LLM provider selection |
| `details` | Multi-user, storage, RAG, guardrails |
| `review` | Confirm all requirements with user |
| `architecture` | Generate diagram, signal readiness |

**Memory**: 30-message session window per project (Lyzr ADK `memory=30`)
**Structured Output**: `OrchestratorOutput` (Pydantic) — state + requirements + message

---

## Skill: Generate Lyzr ADK Code

**Agent**: CodeGeneratorAgent
**Input**: Completed `Requirements` object from OrchestratorAgent
**Output**:

| File | Purpose |
|------|---------|
| `agent.py` | Main entry point with `studio.create_agent()` |
| `tools/*.py` | One file per tool with mock + real API pattern |
| `requirements.txt` | `lyzr-adk` + tool deps |
| `.env.example` | All required env vars |
| `README.md` | Setup + run instructions |

**Guardrails**: `reflection=True` — agent self-reviews before returning code
**Structured Output**: `CodeGeneratorOutput` (Pydantic) — file list + next steps

---

## Tools Available

| Tool | Purpose |
|------|---------|
| `generate_diagram` | Architecture diagram via MCP bridge → Python diagrams fallback |
| `search_lyzr_docs` | Fetch docs.lyzr.ai snippets at generation time |
| `get_lyzr_code_template` | Return correct Lyzr ADK boilerplate patterns |

---

## Limitations

- Generates Lyzr ADK code only (not Strands, LangChain, CrewAI, etc.)
- Diagram generation requires `uvx` + `awslabs.aws-diagrams-mcp-server` OR `diagrams` Python lib
- No frontend generated — API + agent layer only
- Long generation (60s+) runs as background task — use `/generate/status` to poll
