# Strands SDK vs Lyzr ADK — Developer Comparison
> Written from 6 months of production experience with AWS AgentCore + Strands,
> then rebuilding the Agent-for-Agents application in Lyzr ADK.

---

## TL;DR

| Question | Strands (AWS AgentCore) | Lyzr ADK |
|---|---|---|
| First agent running | ~2-3 hours (AWS setup) | ~10 minutes (pip install) |
| Best for | AWS-native, enterprise, compliance | Fast iteration, multi-LLM, GitAgent |
| MCP support | ✅ Native, first-class | ⚠️ Manual bridge required |
| Structured output | ❌ Parse from text | ✅ Pydantic `response_model` |
| Memory | ✅ AWS-managed sessions | ✅ `session_id` param (simpler) |
| Responsible AI | ❌ Build it yourself | ✅ Built-in (`reflection`, `bias_check`) |
| Deployment | Containers on AgentCore Runtime | API call to Lyzr Studio |
| Cost model | AWS per-token + infra | Lyzr token credits |
| GitAgent compatible | ❌ No adapter | ✅ Native adapter |

---

## 1. Setup & First Agent

### Strands
```bash
# Prerequisites
brew install awscli
aws configure  # IAM user, access keys, region
pip install strands-agents bedrock-agentcore boto3

# Create a model
from strands import Agent
from strands.models.bedrock import BedrockModel

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-west-2",        # must match your Bedrock enabled region
    temperature=0.7,
    max_tokens=4096
)
agent = Agent(model=model, system_prompt="You are helpful.")
result = agent("Hello!")
```
**Time to first response**: ~2-3 hours (AWS account setup, Bedrock model access request, IAM roles)

### Lyzr ADK
```bash
pip install lyzr-adk python-dotenv

from lyzr import Studio
studio = Studio(api_key="your-key")
agent = studio.create_agent(
    name="MyAgent", provider="gpt-4o",
    role="Assistant", goal="Help users", instructions="Be helpful."
)
result = agent.run("Hello!")
```
**Time to first response**: ~10 minutes (sign up at studio.lyzr.ai, get API key, pip install)

**Winner: Lyzr ADK** — Zero infrastructure setup.

---

## 2. MCP Tool Integration

This is the **most significant technical difference**.

### Strands — Native MCP (First-Class)
```python
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

# One block registers ALL tools from an MCP server
aws_docs_client = MCPClient(
    lambda: stdio_client(StdioServerParameters(
        command="uvx",
        args=["awslabs.aws-documentation-mcp-server@latest"]
    ))
)

with aws_docs_client:
    tools = aws_docs_client.list_tools_sync()  # Gets 20+ tools at once
    agent = Agent(model=model, system_prompt=prompt, tools=tools)
    result = agent("Search AWS docs for Lambda pricing")
```

**What's happening**: Strands spawns the MCP subprocess, negotiates the MCP protocol,
discovers all tools, and injects them directly. The agent sees 20+ tools in one line.

### Lyzr ADK — Manual Bridge Required
```python
# Must write bridge code per MCP server
async def _call_mcp_server(query: str) -> str:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async with stdio_client(StdioServerParameters(
        command="uvx",
        args=["awslabs.aws-documentation-mcp-server@latest"]
    )) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_docs", {"query": query})
            return result.content[0].text

def search_aws_docs(query: str) -> str:
    """Search AWS documentation for the given query."""
    return asyncio.run(_call_mcp_server(query))

agent.add_tool(search_aws_docs)  # Register ONE tool per MCP call
```

**What's happening**: No native MCP client in Lyzr ADK. Must manually:
1. Write an async bridge function using the `mcp` library
2. Handle asyncio event loop conflicts (FastAPI + asyncio nesting issues)
3. Register each tool individually — no bulk tool discovery
4. Repeat for every MCP server you want to use

**Verdict**:
- Strands: 5 lines to register an entire MCP server
- Lyzr ADK: ~30 lines of bridge code per MCP server, registered one tool at a time
- **Winner: Strands** — Native MCP is a massive DX advantage for tool-heavy agents

**Note**: This was the hardest part of the rebuild. The `diagram_tool.py` bridge
took significantly more effort than the equivalent Strands `MCPClient` setup.
Lyzr's approach IS workable but adds non-trivial complexity.

---

## 3. Memory & Sessions

### Strands — AWS-Managed
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

# Explicit turn management
turns = session.get_last_k_turns(k=50)
session.add_turns(messages=[ConversationalMessage(content, MessageRole.USER)])
```

**Characteristics**:
- Fully managed by AWS — persists across restarts
- Explicit turn management — you control what's stored
- Sessions can be explicitly deleted
- Billed separately (AgentCore Memory)
- Required `AGENTCORE_MEMORY_ID` env var + IAM permissions

### Lyzr ADK — Simple `session_id`
```python
# Memory is fully automatic — just pass session_id
response = agent.run("Hello", session_id="user123_project456")
response = agent.run("What did I say?", session_id="user123_project456")  # remembers
```

**Characteristics**:
- Dead simple — one parameter handles everything
- Managed by Lyzr Studio API — no AWS resources
- No explicit session deletion (use a new session_id)
- `memory=N` param controls window size (1-50 messages)
- Zero IAM or infrastructure configuration

**Verdict**:
- Strands: more control and explicit session lifecycle management
- Lyzr ADK: dramatically simpler — works correctly in 99% of cases
- **Winner: Lyzr ADK** — The `session_id` pattern is the right abstraction.

---

## 4. Structured Output

### Strands — Text Parsing (Fragile)
```python
# Agent returns raw text. You embed a JSON block and parse it out.
result = agent("Analyze this and return JSON with field1, field2")
response_text = str(result)

# Multi-method extraction (real code from our Strands build):
import re
match = re.search(r"<json>(.*?)</json>", response_text, re.DOTALL)
if match:
    data = json.loads(match.group(1))
else:
    try:
        data = json.loads(response_text.strip())
    except:
        match = re.search(r"```json\s*(.*?)```", response_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            # brace matching fallback...
```

This is actual production code. Four fallback methods because the model
sometimes formats the JSON block differently.

### Lyzr ADK — Native Pydantic
```python
from pydantic import BaseModel

class AnalysisOutput(BaseModel):
    field1: str
    field2: list[str]
    confidence: float

agent = studio.create_agent(..., response_model=AnalysisOutput)
result = agent.run("Analyze this")
data: AnalysisOutput = result.structured_output  # always correct type
```

**Verdict**:
- Strands: multi-step parsing with 4 fallback methods in production code
- Lyzr ADK: `response_model=YourPydanticModel` — one line, always structured
- **Winner: Lyzr ADK** — Eliminates an entire category of production bugs.

---

## 5. Responsible AI / Guardrails

### Strands — Build It Yourself
```python
# Strands has no built-in guardrails. You implement them manually:
def check_pii(text: str) -> bool:
    # Your PII detection logic
    pass

def moderate_content(text: str) -> str:
    # Your moderation logic
    pass

# Then wrap every agent response:
result = agent(message)
clean_result = moderate_content(str(result))
```

### Lyzr ADK — Built-In
```python
agent = studio.create_agent(
    ...,
    reflection=True,    # Agent reviews its own response before returning
    bias_check=True,    # Detect and mitigate biased outputs
    # PII handling, toxicity detection via Lyzr Studio settings
)
```

**Verdict**:
- Strands: RAI is your responsibility — no scaffolding provided
- Lyzr ADK: Core RAI features are single parameters
- **Winner: Lyzr ADK** — Especially valuable for enterprise use cases.

---

## 6. Deployment

### Strands (AWS AgentCore)
```bash
# Docker build + push + deploy — required for every change
agentcore launch --agent agent_for_agents_orchestrator --auto-update-on-conflict

# What happens under the hood:
# 1. Builds Docker image
# 2. Pushes to ECR
# 3. Creates/updates AgentCore Runtime
# 4. Configures IAM roles
# 5. Provisions container infrastructure
```

Typical iteration cycle: **5-10 minutes** per code change.

Requirements:
- Dockerfile
- ECR repository
- IAM execution role
- AWS CLI + credentials
- `.bedrock_agentcore.yaml` config
- Container must listen on port 8080

### Lyzr ADK
```bash
pip install lyzr-adk
python main.py   # or uvicorn main_api:app
```

No containers. No cloud deployment. Agents run in-process.

Iteration cycle: **instant** (Python restart).

**Verdict**:
- Strands: Enterprise production-grade — container isolation, IAM, VPC support
- Lyzr ADK: Radically simpler — runs on a laptop with no cloud account
- **Winner: Lyzr ADK for dev speed, Strands for enterprise production**

---

## 7. Multi-Agent Orchestration

### Strands
```python
# Agents are separate deployments. Orchestration = separate container calling another.
response = bedrock_agentcore_client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:...",
    runtimeSessionId=session_id,
    payload=json.dumps({"prompt": message}).encode(),
    contentType='application/json',
)
# Read streaming response body...
```

Each agent is a deployed container. Communication is via HTTP.

### Lyzr ADK
```python
# All agents live in-process. Multi-agent = sequential Python.
r1 = agent1.run(user_input)
r2 = agent2.run(r1.response)
r3 = agent3.run(f"Step1: {r1.response}\nStep2: {r2.response}")
print(r3.response)
```

**Verdict**:
- Strands: True distributed agents — each independently scalable and deployable
- Lyzr ADK: In-process pipeline — simpler but not independently scalable
- **Winner: Strands for distributed/production, Lyzr ADK for simplicity**

---

## 8. Observability

### Strands
- CloudWatch Logs (automatic from container)
- CloudWatch Metrics
- OpenTelemetry instrumentation (`opentelemetry-instrument python -m agent`)
- AWS X-Ray tracing optional

### Lyzr ADK
- Lyzr Studio dashboard (token usage, agent activity)
- Standard Python logging to stdout
- No built-in distributed tracing

**Winner: Strands** — CloudWatch + X-Ray is a complete enterprise observability stack.

---

## 9. Cost Model

### Strands (AWS AgentCore)
- **LLM tokens**: AWS Bedrock per-token pricing
- **AgentCore Runtime**: Container compute (per invocation)
- **AgentCore Memory**: Storage pricing
- **Other**: S3, DynamoDB, ECR, CloudWatch
- Total for this project: **~$50-80/month** (idle containers + dev usage)

### Lyzr ADK
- **LLM tokens**: Lyzr credits (covers API calls to OpenAI/Anthropic)
- **No infrastructure**: No containers, no managed services
- Total for comparable usage: **Lyzr pricing tier** (no infra overhead)

**Winner: Lyzr ADK** — No infrastructure cost. Pay only for what you use.

---

## 10. Real-World Friction Points

### Strands — Actual Pain Points Experienced
1. **`@app.entrypoint` vs `@app.entrypoint()`** — Parentheses cause a silent crash.
   No error message, just wrong behavior. Cost 2 hours to debug.

2. **MCP `with` block requirement** — Leaked MCP connections hang the container.
   All MCP clients must be inside `with` blocks. Not obvious from docs.

3. **DynamoDB Decimal** — Every DynamoDB response needs decimal conversion before
   JSON serialization. Causes `TypeError: Object of type Decimal is not JSON serializable`.

4. **API Gateway 29s timeout** — Code generator takes 60-120s. Required building
   the full async pattern: return requestId → background thread → S3 poll loop.

5. **Container cold start** — First invocation after idle takes 10-15s.
   Subsequent calls are fast, but demos suffer.

6. **IAM debugging** — When something doesn't work in AgentCore, the error is often
   an IAM permission issue surfacing as a cryptic 403. Takes time to trace.

### Lyzr ADK — Friction Points Found in Rebuild
1. **No native MCP support** — Biggest pain point. The bridge pattern works but
   adds ~30 lines of async code per MCP server. Strands does it in 5.

2. **`response_model` uses OpenAI strict JSON mode** — When you set `response_model`,
   Lyzr ADK passes your Pydantic schema as `response_format` to the OpenAI API using
   strict JSON mode. OpenAI requires ALL fields to be in `required`. Pydantic models
   with any defaults produce empty `required` arrays — OpenAI rejects the call:
   ```
   "Invalid schema for response_format: 'required' is required to be supplied
   and to be an array including every key in properties. Missing 'message'."
   ```
   **Fix**: Remove `response_model`, add a JSON mandate to instructions, parse
   `result.response` manually. Adds friction but works reliably.

3. **JSON-inside-JSON breaks code generation** — When asking an LLM to output code
   files as JSON string values (e.g., `"content": "def foo():\n..."`), the LLM
   produces literal newlines and unescaped quotes, making the outer JSON invalid.
   Even `json_repair` fails when the code has `os.getenv("KEY")` patterns.
   **Fix**: Delimiter format (`---FILE_START: path---` / `---FILE_END---`) that
   keeps file content outside of JSON entirely. Much more reliable.

4. **asyncio + sync conflict** — Lyzr ADK is synchronous. Inside FastAPI (async),
   calling `agent.run()` requires `loop.run_in_executor()`. Not obvious.

5. **`asyncio.run()` inside existing loop** — `diagram_tool.py` hits this in
   FastAPI. Requires `concurrent.futures.ThreadPoolExecutor` workaround.

6. **Session clearing not exposed** — No `clear_session()` API. Must use a new
   `session_id` to reset context. Minor but inconsistent with Strands.

7. **Some docs pages 404** — `/lyzr-adk/multi-agent`, `/lyzr-adk/knowledge-base`
   returned 404 during rebuild. Had to infer behavior from examples.

8. **No distributed agents** — All agents run in-process. Can't independently
   scale, deploy, or monitor individual agents in production.

---

## Summary: When to Use Which

### Use Strands + AWS AgentCore when:
- You're all-in on AWS
- You need enterprise compliance (VPC, IAM, audit logging)
- You need true distributed/independently scalable agents
- MCP tool ecosystem is critical to your agent's value
- You need CloudWatch observability
- Your team is comfortable with Docker + AWS operations

### Use Lyzr ADK when:
- You want fast iteration and low operational overhead
- You're targeting the GitAgent ecosystem
- You need structured output without custom parsing logic
- Built-in RAI guardrails matter to your use case
- You want multi-LLM provider flexibility (OpenAI, Anthropic, Google in one SDK)
- You're building a demo, prototype, or startup MVP

### The Real Answer
**Build the agent logic in Lyzr ADK. Package it as a GitAgent.
Deploy it anywhere.** The portability is the point.

The Strands/AgentCore stack is excellent production infrastructure.
But Lyzr ADK is where you want to develop, iterate, and share.
These aren't mutually exclusive — they serve different stages of the same lifecycle.

---

*Author: 6 months with Strands SDK + AWS AgentCore (17 production agents deployed),
then full rebuild of Agent-for-Agents in Lyzr ADK.*
*Date: March 2026*
