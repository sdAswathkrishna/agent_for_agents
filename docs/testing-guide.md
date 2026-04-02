# Agent-for-Agents — End-to-End Manual Testing Guide

> Follow this guide to experience the full workflow as a real user.
> Estimated time: 15–20 minutes to complete all paths.

---

## Prerequisites

```bash
python >= 3.11
pip install -r requirements.txt
npm install -g @open-gitagent/gitagent   # GitAgent CLI
cp .env.example .env
# Add LYZR_API_KEY and OPENAI_API_KEY to .env
```

---

## PATH A — GitAgent CLI (Fastest, ~3 min)

This is the showcase path. Runs the agent directly through the GitAgent standard
without touching any Python or API — pure portability proof.

### Step 1 — Validate the spec
```bash
gitagent validate
```
**Expected output:**
```
✓ agent.yaml — valid
✓ SOUL.md — valid
✓ tools/generate-diagram.yaml — valid
✓ tools/get-lyzr-template.yaml — valid
✓ tools/search-lyzr-docs.yaml — valid
✓ skills/ — valid
✓ Validation passed (0 warnings)
```

### Step 2 — Inspect the agent definition
```bash
gitagent info
```
Check that model, skills, tools, runtime and Soul preview all appear correctly.

### Step 3 — Run from local directory
```bash
source .env
gitagent run -d . -a lyzr -p "I want to build an invoice processing agent for my finance team"
```
**Expected:** Agent responds with `[STATE 1/6: intro]` and asks about purpose + target users.

### Step 4 — Run from GitHub (portability test)
```bash
gitagent run -r https://github.com/sdAswathkrishna/agent_for_agents -a lyzr \
  -p "I want to build a Slack bot that monitors CI/CD pipelines"
```
**Expected:** GitAgent clones the repo, reads agent.yaml, connects to Lyzr, and
starts the same 6-state conversation — from a clean URL with no local files.

### Step 5 — Export to other frameworks
```bash
gitagent export --format lyzr          # Lyzr Studio JSON payload
gitagent export --format claude-code   # CLAUDE.md compatible system prompt
gitagent export --format system-prompt # Universal flat prompt
gitagent export --format openai        # OpenAI agents format
gitagent export --format crewai        # CrewAI agent definition
gitagent export --format openclaw      # OpenClaw format
```
**Expected:** Each command outputs a valid definition in the target framework's format.

---

## PATH B — FastAPI (Full Workflow, ~10 min)

This path exercises the complete multi-agent pipeline end to end.

### Step 1 — Start the server
```bash
uvicorn main_api:app --reload --port 8000
```
Open `http://localhost:8000/docs` in a browser — the Swagger UI shows all endpoints.

### Step 2 — Health check
```bash
curl http://localhost:8000/health
```
**Expected:**
```json
{"status": "ok", "framework": "lyzr-adk"}
```

### Step 3 — Create a new project
```bash
curl -s -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Customer Support Agent"}' | python3 -m json.tool
```
**Expected:** JSON with `project_id`, `status: "gathering"`, `conversation_state: "intro"`.
Save the `project_id` for the next steps.

```bash
PROJECT_ID="<paste project_id here>"
```

### Step 4 — State 1/6: Intro
```bash
curl -s -X POST http://localhost:8000/projects/$PROJECT_ID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want a chatbot that answers customer questions from a knowledge base"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))"
```
**Expected:** Questions about purpose and target users.

### Step 5 — State 2/6: Requirements
```bash
curl -s -X POST http://localhost:8000/projects/$PROJECT_ID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Purpose: reduce support ticket volume. Users: end customers via a web chat widget"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))"
```
**Expected:** Questions about tools and integrations needed.

### Step 6 — State 3/6: Tech stack
```bash
curl -s -X POST http://localhost:8000/projects/$PROJECT_ID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tools: search knowledge base, escalate to human, update ticket status. Integrations: Zendesk"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))"
```
**Expected:** Questions about LLM preference and multi-user setup.

### Step 7 — States 4–5: Details + Review
Continue answering the agent's questions naturally. When the agent presents a summary
and asks for confirmation, reply:
```bash
curl -s -X POST http://localhost:8000/projects/$PROJECT_ID/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Yes, that looks correct. Proceed."}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))"
```

### Step 8 — State 6/6: Architecture + Generate
Once the agent signals it's ready (State: architecture), trigger code generation:
```bash
curl -s -X POST http://localhost:8000/projects/$PROJECT_ID/generate \
  -H "Content-Type: application/json" \
  -d '{}'
```
**Expected:** `{"status": "started", "message": "Code generation in progress"}`

### Step 9 — Poll until complete
```bash
# Run this until status = "completed"
curl -s http://localhost:8000/projects/$PROJECT_ID/generate/status \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status'))"
```
**Expected** (after ~20–30 seconds):
```
status: completed
```

### Step 10 — Inspect generated files
```bash
ls artifacts/$PROJECT_ID/
# agent.py  tools/  requirements.txt  .env.example  README.md
cat artifacts/$PROJECT_ID/agent.py
cat artifacts/$PROJECT_ID/tools/*.py
```
**Expected:** A complete, runnable Lyzr ADK project targeting the described agent.

### Step 11 — Download as ZIP
```bash
curl -s http://localhost:8000/projects/$PROJECT_ID/download --output generated_agent.zip
unzip -l generated_agent.zip
```

---

## PATH C — CLI Interactive Mode (~5 min)

The CLI mode gives a conversational, terminal-native experience.

```bash
python main.py
```

Type your agent description and follow the prompts. When all 6 states are complete,
the CLI will prompt: `Type 'generate' to produce the Lyzr ADK code.`

```
> generate
```

The generated files appear in `artifacts/<project_id>/`.

---

## What to Look For

| Checkpoint | What it proves |
|------------|---------------|
| `gitagent validate` → 0 warnings | The agent.yaml + SOUL.md + skills + tools are spec-compliant |
| `gitagent run -r github.com/...` returns a response | Framework-agnostic portability — the GitAgent standard works from a URL |
| `gitagent export --format openai` produces valid JSON | Same agent definition works in OpenAI Agents format |
| `/health` returns `"framework": "lyzr-adk"` | Lyzr ADK agents are initialised correctly on startup |
| `/projects/{id}/generate/status` → `completed` | Both Lyzr ADK agents (Orchestrator + CodeGenerator) completed successfully |
| `artifacts/` contains `agent.py` + `tools/*.py` | CodeGeneratorAgent produced a complete, multi-file Lyzr ADK project |
| Generated `agent.py` imports `from lyzr import Studio` | Output is actually valid Lyzr ADK code, not pseudocode |

---

## Streaming Test (Bonus)

```bash
curl -s -N -X POST http://localhost:8000/projects/$PROJECT_ID/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What tools does this agent need?"}'
```
**Expected:** SSE events streaming in real time:
```
data: {"type": "token", "content": "Based"}
data: {"type": "token", "content": " on"}
...
data: {"type": "done"}
```

---

## Common Issues & Quick Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: This event loop is already running` | Sync/async conflict | Already fixed via ThreadPoolExecutor in main_api.py |
| Generation status stuck at `running` | CodeGeneratorAgent timeout | Check LYZR_API_KEY and OPENAI_API_KEY in .env |
| `gitagent run` returns empty response | LYZR_API_KEY not exported | `source .env` before running |
| `gitagent validate` shows skill errors | SKILL.md missing frontmatter | All SKILL.md files have valid `---` frontmatter — re-pull from repo |
| KB returns no results (NexaFlow project only) | Score threshold too high | Set `_KB_SCORE_THRESHOLD=0.2` in `agents/chat_agent.py` |
