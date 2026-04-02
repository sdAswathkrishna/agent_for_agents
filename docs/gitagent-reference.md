# GitAgent Standard — Reference
> Fetched from https://github.com/open-gitagent/gitagent
> Use this when packaging the Lyzr rebuild as a GitAgent

---

## 1. CONCEPT

GitAgent = "Docker for AI agents"
- Repos as agents: clone a repo, get an agent
- Framework-agnostic: same repo runs on Claude, OpenAI, Lyzr, CrewAI, LangChain
- Git-native: version control, branch, diff, rollback your agents
- Only 2 required files: `agent.yaml` + `SOUL.md`

---

## 2. INSTALLATION

```bash
npm install -g @open-gitagent/gitagent
```

---

## 3. AGENT.YAML — FULL SCHEMA

### Required Fields
```yaml
spec_version: "0.1.0"
name: my-agent              # kebab-case
version: 0.1.0              # semver
description: "One-line description"
```

### Model Configuration
```yaml
model:
  preferred: "claude-opus-4-20250514"
  fallback: "claude-sonnet-4-5-20250929"
  constraints:
    temperature: 0.1
    max_tokens: 4096
    top_p: 0.9
```

### Skills & Tools
```yaml
skills:
  - name: analyze-requirements      # maps to skills/analyze-requirements/SKILL.md
  - name: generate-code

tools:
  - name: fetch-jira                # maps to tools/fetch-jira.yaml
  - name: generate-diagram
```

### Sub-Agents (Multi-Agent)
```yaml
agents:
  - name: orchestrator
    delegation: auto
  - name: code-generator
    delegation: explicit
    description: "Generates code from requirements"

# OR with URLs:
agents:
  - name: researcher
    url: ./agents/researcher
  - name: validator
    url: https://github.com/org/validator-agent
    version: "^1.0.0"
```

### Runtime Controls
```yaml
max_turns: 20
timeout_seconds: 120
```

### Full Example (our use case)
```yaml
spec_version: "0.1.0"
name: agent-for-agents
version: 1.0.0
description: >
  Conversational agent that builds other AI agents — gathers requirements,
  generates architecture diagrams, and produces deployable Lyzr ADK code.

author: your-github-username
license: MIT
tags:
  - meta-agent
  - code-generation
  - multi-agent
  - lyzr-adk

model:
  preferred: "gpt-4o"
  fallback: "claude-3-5-sonnet"
  constraints:
    temperature: 0.3
    max_tokens: 8096

runtime: lyzr

skills:
  - name: gather-requirements
  - name: generate-agent-code

agents:
  - name: OrchestratorAgent
    description: "Gathers requirements via guided conversation"
    delegation: explicit
  - name: CodeGeneratorAgent
    description: "Generates deployable Lyzr ADK code"
    delegation: explicit

tools:
  - name: generate-diagram
  - name: search-lyzr-docs

env:
  - LYZR_API_KEY
  - OPENAI_API_KEY

input:
  user_request:
    type: string
    description: "Describe the agent you want to build"
    required: true

output:
  type: code
  description: "Generated Lyzr ADK agent code as downloadable ZIP"
```

---

## 4. SOUL.MD STRUCTURE

```markdown
# Agent Name — Soul

## Identity
[Who/what this agent is. 2-3 sentences.]

## Personality
- **Trait 1**: Description
- **Trait 2**: Description

## Domain Expertise
[What it knows. Bullet list.]

## What It Does Well
[Key strengths. Bullet list.]

## What It Avoids
[Hard limits. Bullet list.]

## Communication Style
[How it formats responses. Emoji use, severity labels, etc.]
```

---

## 5. SKILL.MD STRUCTURE

Each skill lives in `skills/{skill-name}/SKILL.md`:

```markdown
---
name: skill-name
description: "What this skill does"
license: MIT
allowed-tools: "tool1 tool2"
---

## Overview
[What this skill does]

## Instructions
[Step-by-step how to execute this skill]

## Examples
[Usage examples]

## Limitations
[What it can't do]
```

---

## 6. TOOL YAML STRUCTURE

Each tool lives in `tools/{tool-name}.yaml`:

```yaml
name: tool-name
description: "What this tool does"
version: "1.0.0"

input_schema:
  type: object
  properties:
    param1:
      type: string
      description: "Parameter description"
  required: ["param1"]

output_schema:
  type: object
  properties:
    result:
      type: string

implementation:
  type: script
  path: ./tools/tool-name.py
  runtime: python3
  # OR:
  # type: http
  # url: "https://api.example.com/tool"
  # method: POST
```

---

## 7. MULTI-AGENT PROJECT STRUCTURE

```
agent-for-agents/
├── agent.yaml              # Root config
├── SOUL.md                 # Agent identity
├── SKILL.md                # Agent capabilities
├── RULES.md                # Hard constraints
├── main.py                 # Lyzr ADK implementation
├── skills/
│   ├── gather-requirements/
│   │   └── SKILL.md
│   └── generate-agent-code/
│       └── SKILL.md
├── tools/
│   ├── generate-diagram.yaml
│   └── search-lyzr-docs.yaml
├── knowledge/              # RAG documents
├── memory/                 # State management
├── .env.example
└── requirements.txt
```

---

## 8. CLI COMMANDS

```bash
# Init from template
gitagent init --template standard

# Validate structure
gitagent validate

# Run with Lyzr adapter
gitagent lyzr run -d . -p "I want to build a customer support agent"

# Run with Claude adapter
gitagent run -d . -a claude

# Export as system prompt
gitagent export --format system-prompt

# Lyzr-specific commands
gitagent lyzr create -d .
gitagent lyzr update -d .
gitagent lyzr info -d .
```

---

## 9. ADAPTERS AVAILABLE

| Adapter | How to run |
|---|---|
| `system-prompt` | Universal (any LLM) |
| `claude` | `gitagent run -a claude` |
| `openai` | `gitagent run -a openai` |
| `crewai` | `gitagent run -a crewai` |
| `lyzr` | `gitagent lyzr run` |
| `langchain` | `gitagent run -a langchain` |
| `google-adk` | `gitagent run -a google-adk` |

---

## 10. EXAMPLE REPOS TO REFERENCE

1. **minimal** — `agent.yaml` + `SOUL.md` only
2. **standard** — Full working example with skills, tools, knowledge
3. **lyzr-agent** — Lyzr Studio integration with `.gitagent_adapter` marker
4. **nvidia-deep-researcher** — 3-tier agent hierarchy (orchestrator → planner → researcher)
5. **full** — Production-grade with compliance (FINRA, SEC, audit logging)

Find at: `https://github.com/open-gitagent/gitagent/tree/main/examples`
