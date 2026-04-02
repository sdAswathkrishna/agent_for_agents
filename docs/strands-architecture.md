# Agent-for-Agents — Strands SDK Architecture Reference
> Saved from analysis of /Users/aswathkrishna.sd/agent-for-agents
> Use this as the source of truth when rebuilding in Lyzr ADK

---

## 1. WHAT THE APP DOES

A full-stack application where users describe an agent they want to build.
The system gathers requirements via guided conversation, generates an architecture
diagram, and produces deployable Python code — all through two AI agents.

**Two-Phase Flow:**
- **PLAN Phase** — Orchestrator Agent: conversational requirement gathering (6 states)
- **EXECUTE Phase** — Code Generator Agent: produces ready-to-deploy code as JSON

---

## 2. OVERALL ARCHITECTURE

```
Frontend (Next.js)
    ↓  JWT (Cognito)
Backend API (AWS Chalice / Lambda)
    ↓  boto3 AgentCore Runtime invocation
┌─────────────────┐    ┌──────────────────────┐
│ ORCHESTRATOR    │    │ CODE GENERATOR        │
│ AGENT           │    │ AGENT                 │
│ (AgentCore)     │    │ (AgentCore, async)    │
│ MCP Tools:      │    │ MCP Tools:            │
│  - AWS Docs     │    │  - AWS Docs           │
│  - AWS Diagrams │    │  - AgentCore Docs     │
│  - CloudWatch   │    │                       │
│                 │    │ Output: JSON w/ files  │
│ Output: reqs    │    │ Written to S3          │
│ + diagram PNG   │    │                       │
└─────────────────┘    └──────────────────────┘
         └──────────────────┘
                  ↓
           S3 Artifact Storage
```

---

## 3. STRANDS SDK KEY PATTERNS

### Agent Creation
```python
from strands import Agent
from strands.models.bedrock import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-west-2",
    temperature=0.7,
    max_tokens=4096
)

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=all_tools   # list from MCP clients
)

result = agent(user_message)
response_text = str(result)
```

### MCP Tool Integration (CRITICAL: Must use context manager)
```python
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

aws_docs_client = MCPClient(
    lambda: stdio_client(StdioServerParameters(
        command="uvx",
        args=["awslabs.aws-documentation-mcp-server@latest"]
    ))
)

# MUST use with block
with aws_docs_client, agentcore_docs_client:
    tools = aws_docs_client.list_tools_sync() + agentcore_docs_client.list_tools_sync()
    agent = Agent(model=model, system_prompt=prompt, tools=tools)
    result = agent(message)
```

### BedrockAgentCoreApp Entrypoint (CRITICAL SYNTAX)
```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint          # NO PARENTHESES — @app.entrypoint() CRASHES
def handler(event: dict, context: dict) -> dict:
    return {"response": response_text, "raw_output": response_text}

if __name__ == "__main__":
    app.run()
```

### AgentCore Memory Sessions
```python
from bedrock_agentcore.memory.session import MemorySessionManager
from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

memory_manager = MemorySessionManager(
    memory_id=os.environ['AGENTCORE_MEMORY_ID'],
    region_name='us-west-2'
)

session = memory_manager.create_memory_session(
    actor_id=user_id,
    session_id=f"{user_id}_{project_id}"
)

turns = session.get_last_k_turns(k=50)
session.add_turns(messages=[ConversationalMessage(content, MessageRole.USER)])
```

### AgentCore Runtime Invocation (from backend)
```python
response = bedrock_agentcore_client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:...",
    runtimeSessionId=session_id,
    payload=json.dumps({
        'prompt': user_message,
        'session_id': session_id,
        'current_state': current_state,
        'current_requirements': current_requirements
    }).encode('utf-8'),
    contentType='application/json',
    accept='application/json'
)

streaming_body = response['response']
chunks = [chunk for chunk in streaming_body.iter_chunks()]
response_data = json.loads(b''.join(chunks).decode('utf-8'))
```

---

## 4. ORCHESTRATOR AGENT — 6-STATE CONVERSATION FLOW

**States (in order):**
1. `intro`         — Greet user, ask what agent they want
2. `requirements`  — AWS services, invocation methods
3. `tech`          — Tech stack selection (python-strands or python-chalice)
4. `details`       — Multi-user setup, AWS service specs, integrations, error handling
5. `review`        — Summarize requirements, get confirmation
6. `architecture`  — Generate architecture diagram (calls diagram MCP tool → PNG)

**Response Format (REQUIRED every turn):**
```
<state>
{
  "conversationState": "intro|requirements|tech|details|review|architecture",
  "extractedRequirements": { /* full requirements dict */ },
  "isComplete": false
}
</state>
```

**MCP Tools available:**
- AWS Documentation (search, read, recommend)
- AWS Diagrams (generate_diagram, list_icons, examples)
- AgentCore Documentation (search, fetch, runtime ops)
- CloudWatch (alarms, metrics, logs)

---

## 5. CODE GENERATOR AGENT — ASYNC PATTERN

**Why async?** Code generation takes 60-120s. API Gateway has a 29s timeout.

**Async Flow:**
1. Handler receives payload → validates → starts background thread → returns `{"status": "processing"}`
2. Background thread: agent runs → produces JSON → writes `_generation_result.json` to S3
3. Backend polls S3 for result → stores files → finalizes

**Input Payload:**
```json
{
  "project_id": "uuid",
  "requirements": { /* full requirements dict */ },
  "rules_content": "large markdown template string",
  "refinement_request": "optional"
}
```

**Output Format (written to S3):**
```json
{
  "files": [
    { "path": "agent.py", "content": "...", "type": "code" },
    { "path": "tools/my_tool.py", "content": "...", "type": "code" },
    { "path": "README.md", "content": "...", "type": "readme" }
  ],
  "summary": "What was generated",
  "nextSteps": ["Deploy with...", "..."],
  "error": null
}
```

**Response Extraction Fallbacks (multiple methods):**
1. `<json>...</json>` XML tags
2. Direct JSON parse
3. ` ```json...``` ` markdown blocks
4. Brace-matching algorithm

---

## 6. REQUIREMENTS DATA STRUCTURE

```python
requirements = {
    "problem": str,
    "targetUsers": str,
    "tools": list[str],
    "triggers": list[str],
    "techStack": "python-strands|python-chalice",
    "multiUser": {
        "enabled": bool,
        "authentication": str,
        "dataModel": "shared|isolated",
        "isolatedData": list[str],
        "roles": list[str],
        "adminCapabilities": list[str]
    },
    "awsServices": {
        "dynamodb": {"operations": list, "tables": list},
        "lambda": {"tools": list},
        "s3": {"operations": list, "scope": "all|specific"},
        "apiGateway": {"enabled": bool, "type": "REST|HTTP", "endpoints": list},
        "auroraVectorDb": {
            "enabled": bool,
            "tableName": str,
            "embeddingModel": str,
            "embeddingDimensions": int,
            "operations": list,
            "topK": int,
            "metadataFilters": list
        }
    },
    "integrations": {"oauth": None, "apis": list},
    "errorHandling": {}
}
```

---

## 7. STATUS STATE MACHINE

```
gathering → designing → generating → generated → approved
                ↑            ↓             ↓
                └────────────┘             └──→ refine → generating
```

---

## 8. BACKEND ENDPOINTS

| Method | Path | Purpose |
|--------|------|---------|
| POST | /projects | Create project |
| GET | /projects | List user projects |
| GET | /projects/{id} | Get project + history |
| POST | /projects/{id}/chat/stream | SSE streaming chat |
| POST | /projects/{id}/chat | Async chat |
| GET | /projects/{id}/chat/status/{reqId} | Poll chat status |
| POST | /projects/{id}/generate | Start code generation |
| GET | /projects/{id}/generate/status/{reqId} | Poll generation status |
| GET | /projects/{id}/artifacts | List generated files |
| GET | /projects/{id}/artifacts/{path} | Get file content |
| GET | /projects/{id}/download | Get ZIP download URL |
| POST | /projects/{id}/refine | Refine generated code |
| POST | /projects/{id}/approve | Approve code |

---

## 9. KEY GOTCHAS / LESSONS FROM STRANDS BUILD

1. **MCP clients MUST be used in `with` blocks** — leaked connections cause hangs
2. **`@app.entrypoint` NOT `@app.entrypoint()`** — parentheses crash the runtime
3. **DynamoDB returns Decimal** — must convert before JSON serialization
4. **API Gateway 29s timeout** — use async pattern for anything over 10s
5. **Docker CMD must be** `opentelemetry-instrument python -m agent` for AgentCore
6. **AgentCore session IDs** format: `{userId}_{projectId}`
7. **Code generator is fully async** — handler returns immediately, result polled from S3
8. **RBAC with contextvars, NOT threading.local** — Lambda reuses threads
9. **State extraction** — orchestrator embeds `<state>JSON</state>` in response, backend parses it
10. **Diagram PNG stored separately in S3** then copied to artifacts folder on approval

---

## 10. WHAT LYZR ADK NEEDS TO REPLACE / REPLICATE

| Strands Component | Lyzr ADK Equivalent |
|---|---|
| `Agent(model, system_prompt, tools)` | `studio.create_agent(name, provider, role, goal, instructions)` |
| `BedrockModel(model_id, region)` | `provider="gpt-4o"` or `"claude-3-5-sonnet"` param |
| `MCPClient(lambda: stdio_client(...))` | `agent.add_tool(python_function)` or Tool class |
| `agent(message)` | `agent.run(message, session_id=...)` |
| `AgentCore Memory Sessions` | `agent memory=N param` + `session_id` in run() |
| `AgentCore Runtime (container)` | Lyzr Studio API (cloud-hosted) |
| `BedrockAgentCoreApp + @entrypoint` | `Studio(api_key=...)` context manager |
| `MCP tools via uvx processes` | Python functions via `agent.add_tool()` |
| `S3 for artifacts` | Local filesystem or retain S3 |
| `DynamoDB for projects` | Retain DynamoDB OR simplify to local SQLite for demo |
| `AWS Cognito auth` | Simplify: API key auth or remove auth for demo |
| `Chalice backend` | FastAPI or Flask (simpler, no AWS dependency) |
| `Next.js frontend` | Retain OR simplify to CLI for demo |
