# BuilderAI — Testing Guide

> Use this guide to test the system end to end, from GitAgent spec validation through to a running generated agent.
> Estimated time: 20–25 minutes for both paths.

---

## Prerequisites

```bash
python >= 3.11
pip install -r requirements.txt
npm install -g @open-gitagent/gitagent
cp .env.example .env
# Add LYZR_API_KEY and OPENAI_API_KEY to .env
```

---

## PATH A — GitAgent CLI

This path validates the agent spec and proves portability before touching the UI.

### 1. Validate the spec

```bash
gitagent validate
```

Expected: all green checkmarks, `Validation passed (0 warnings)`.

### 2. Inspect the agent

```bash
gitagent info
```

Check that model, skills, tools, runtime, and Soul preview all appear correctly.

### 3. Run from local directory

```bash
source .env
gitagent run -d . -a lyzr -p "I want to build an invoice processing agent for my finance team"
```

Expected: Agent responds with `[STATE 1/6: intro]` and starts asking about purpose and target users.

### 4. Run from GitHub

```bash
gitagent run -r https://github.com/sdAswathkrishna/agent_for_agents -a lyzr \
  -p "I want to build a Slack bot that monitors CI/CD pipelines"
```

Expected: GitAgent clones the repo, reads agent.yaml, connects to Lyzr, and starts the same 6-state conversation — from a clean URL with no local files.

### 5. Export to other frameworks

```bash
gitagent export --format lyzr
gitagent export --format claude-code
gitagent export --format system-prompt
gitagent export --format openai
gitagent export --format crewai
gitagent export --format openclaw
```

Expected: each command outputs a valid definition in the target framework's format.

---

## PATH B — BuilderAI Web UI

This path walks through the full workflow using the web interface.

### 1. Start the server

```bash
uvicorn main_api:app --reload --port 8000
```

### 2. Open the UI

Navigate to `http://localhost:8000/ui/` in your browser. You should see the BuilderAI interface — sidebar on the left, chat panel in the centre, and the Builder panel on the right.

### 3. Create a new project

Click **New** in the sidebar. Give your agent a name — for example, `Customer Support Agent`. Press Enter or click Create.

### 4. Chat through the requirements

The agent will greet you and ask about what you want to build. Answer each question naturally. The conversation moves through six stages: intro, requirements, tech stack, details, review, and architecture. A small label in the chat header shows which stage you are in.

For a customer support agent, try answers like:
- **What it does:** "Answer customer questions from a knowledge base and escalate unresolved issues to a human agent"
- **Tools needed:** "Search knowledge base, escalate to human, update ticket status"
- **Integrations:** "Zendesk"
- **LLM:** "GPT-4o"
- **Users:** "End customers via a web chat widget"

Keep answering until the agent presents a full architecture summary.

### 5. Generate the agent

Once the architecture stage is reached, a **Generate Agent** button appears inline in the chat. Click it. The right panel switches to the Builder view and animates through generation steps — initialising, writing tools, assembling the agent, packaging files.

Generation takes around 20–30 seconds.

### 6. Review the generated files

When generation completes, the right panel switches automatically to the **Files** tab. Click any file in the tree on the left to view its content. Check that:

- `agent.py` contains real Lyzr ADK code — `from lyzr import Studio`, `studio.create_agent(...)`, tool registrations, and a working chat loop
- `tools/*.py` files contain real implementation code with actual API calls, not placeholder returns or TODO comments
- `requirements.txt` lists the correct dependencies
- `agent.yaml`, `SOUL.md`, `RULES.md`, and `skills/*/SKILL.md` files are present

### 7. Download the ZIP

Click the **Download ZIP** button in the top-right corner of the topbar. It is greyed out until generation completes, then turns active. Save and unzip locally.

### 8. Validate the generated spec

```bash
cd /path/to/unzipped-agent
gitagent validate
```

Expected: 0 errors, 0 warnings.

---

## What to Look For

**`gitagent validate` passes with 0 warnings** — the agent.yaml, SOUL.md, skills, and tool definitions are all spec-compliant.

**`gitagent run -r` returns a response** — GitAgent clones the repo, reads the spec, and starts the conversation from a clean URL. Proves framework-agnostic portability.

**The Generate Agent button appears inline** — only shown after the architecture stage is reached, confirming the OrchestratorAgent FSM advanced through all six states correctly.

**Generation completes and the Files tab populates** — both Lyzr ADK agents (Orchestrator and CodeGenerator) ran successfully end to end.

**`agent.py` imports `from lyzr import Studio`** — the generated code is real Lyzr ADK, not pseudocode or stubs.

**The generated `agent.yaml` passes `gitagent validate`** — the CodeGeneratorAgent is producing spec-compliant GitAgent output, not just Python code.

---

## Common Issues & Quick Fixes

**`gitagent run` returns an empty response or "No API key" error**
Source your `.env` before running: `source .env` — or export directly: `export LYZR_API_KEY=sk-...`.

**Generation stays on "Generating…" indefinitely**
Check that both `LYZR_API_KEY` and `OPENAI_API_KEY` are set correctly in `.env`. Restart the server after any `.env` change.

**Generated tool files contain TODO comments or mock return values**
The code generator agent was created with old instructions. Remove `LYZR_CODE_GENERATOR_AGENT_ID` from `.env` and restart the server — it will recreate the agent with the updated instructions on startup.

**`gitagent validate` on generated files shows errors**
Most commonly the `tools` array in `agent.yaml` contains path-style values like `tools/search-knowledge-base.yaml` instead of bare names like `search-knowledge-base`. If you see this, the project was generated before the codegen fix was applied — regenerate it.

**Download ZIP button stays grey**
Generation has not completed. Check the Builder panel for a failed step and look at the server logs for the root cause.

**`RuntimeError: This event loop is already running`**
Already fixed via `ThreadPoolExecutor` in `main_api.py`. If you see this, pull the latest from `main`.
