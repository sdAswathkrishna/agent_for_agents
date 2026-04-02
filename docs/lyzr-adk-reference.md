# Lyzr ADK — Code Reference
> Fetched from https://docs.lyzr.ai/lyzr-adk/
> Use this when writing Lyzr ADK code

---

## 1. INSTALLATION & SETUP

```bash
pip install lyzr-adk
```

```python
from lyzr import Studio

# Option 1: pass key directly
studio = Studio(api_key="your-lyzr-api-key")

# Option 2: from env var LYZR_API_KEY
studio = Studio()

# Option 3: context manager (auto-cleanup)
with Studio(api_key="your-lyzr-api-key") as studio:
    ...
```

Get API key at: https://studio.lyzr.ai/account

---

## 2. CREATING AN AGENT

```python
agent = studio.create_agent(
    name="Support Bot",
    provider="gpt-4o",               # or "claude-3-5-sonnet", "gemini-pro", etc.
    role="Customer support agent",
    goal="Help customers resolve issues",
    instructions="Be empathetic, concise, and solution-oriented",
    temperature=0.7,                  # 0.0 - 2.0
    memory=30,                        # 1-50 messages
)
```

**Supported Providers:**
- OpenAI: `"gpt-4o"`, `"gpt-4o-mini"`, `"gpt-4-turbo"`, `"o1-preview"`
- Anthropic: `"claude-3-5-sonnet"`, `"claude-3-opus"`, `"claude-3-haiku"`
- Google: `"gemini-pro"`, `"gemini-flash"`
- Groq: `"llama-3.1-70b"`, `"mixtral-8x7b"`
- AWS Bedrock: supported via provider param

**Agent Properties:** `id`, `name`, `provider_id`, `model`, `role`, `goal`,
`instructions`, `temperature`, `top_p`

---

## 3. RUNNING AN AGENT

```python
# Simple run
response = agent.run("I can't login to my account")
print(response.response)

# With session (memory persisted across calls)
response = agent.run("Hello", session_id="user_1_session")
response = agent.run("My name is Bob", session_id="user_1_session")  # remembers name

# Streaming
for chunk in agent.run("Tell me a story", stream=True):
    print(chunk.content, end="", flush=True)
    if chunk.done:
        print("\n--- Done ---")
```

**AgentStream Properties:**
`content`, `delta`, `done`, `session_id`, `chunk_index`, `metadata`,
`structured_data`, `artifact_files`

---

## 4. ADDING TOOLS

```python
# Method 1: Simple function (docstring = description)
def get_weather(city: str) -> str:
    """Get current weather for a city"""
    return f"Weather in {city}: Sunny, 72°F"

agent.add_tool(get_weather)

# Method 2: Tool class (explicit schema)
from lyzr.tools import Tool

weather_tool = Tool(
    name="get_weather",
    description="Get current weather for a city",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name"
            }
        },
        "required": ["city"]
    },
    function=get_weather
)
agent.add_tool(weather_tool)

# Multiple tools
agent.add_tool(tool1)
agent.add_tool(tool2)
agent.add_tool(tool3)
```

**Supported Parameter Types:** `string`, `integer`, `number`, `boolean`,
`array`, `object`

---

## 5. MEMORY MANAGEMENT

```python
# Set at creation
agent = studio.create_agent(
    name="Bot",
    provider="gpt-4o",
    memory=30           # Keep last 30 messages
)

# Add memory after creation
agent.add_memory(max_messages=50)

# Session-scoped memory (different users get separate contexts)
agent.run("Hello", session_id="user_alice")
agent.run("Hello", session_id="user_bob")  # separate context
```

---

## 6. KNOWLEDGE BASE (RAG)

```python
# Create knowledge base
kb = studio.create_knowledge_base(
    name="my_knowledge_base",
    vector_store="qdrant",
    embedding_model="text-embedding-3-large",
    llm_model="gpt-4o",
    description="Engineering standards and patterns"
)

# Add documents
kb.add_pdf("docs/guidelines.pdf")
kb.add_website("https://your-confluence.com/standards")
kb.add_text("Your custom text content here...")

# Attach to agent
agent = studio.create_agent(
    ...,
    knowledge_base_ids=[kb.id]
)
```

---

## 7. STRUCTURED OUTPUT

```python
from pydantic import BaseModel
from typing import List

class RequirementsOutput(BaseModel):
    feature_title: str
    acceptance_criteria: List[str]
    complexity: str   # low | medium | high

agent = studio.create_agent(
    ...,
    response_model=RequirementsOutput
)

result = agent.run("Analyze this ticket...")
structured = result.structured_output  # RequirementsOutput instance
print(structured.feature_title)
```

---

## 8. RESPONSIBLE AI GUARDRAILS

```python
agent = studio.create_agent(
    ...,
    reflection=True,      # Self-review before responding
    bias_check=True,      # Detect and mitigate bias
    # RAI guardrails (toxicity, PII, etc.) are configurable
)
```

---

## 9. MULTI-AGENT PATTERN (Pipeline)

```python
with Studio(api_key=api_key) as studio:
    # Create specialist agents
    agent1 = studio.create_agent(name="Analyzer", provider="gpt-4o", ...)
    agent2 = studio.create_agent(name="Writer", provider="gpt-4o", ...)
    agent3 = studio.create_agent(name="Reviewer", provider="gpt-4o", ...)

    # Sequential pipeline
    result1 = agent1.run(user_input)
    result2 = agent2.run(result1.response)
    result3 = agent3.run(result2.response)

    final = result3.response
```

---

## 10. FULL EXAMPLE — MULTI-AGENT SDLC

```python
from lyzr import Studio
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class RequirementsOutput(BaseModel):
    feature_title: str
    acceptance_criteria: list[str]
    complexity: str

def fetch_jira_ticket(ticket_id: str) -> str:
    """Fetch a Jira ticket by ID"""
    return f"Ticket {ticket_id}: Add OAuth2 login"

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    kb = studio.create_knowledge_base(
        name="sdlc_kb",
        vector_store="qdrant",
        embedding_model="text-embedding-3-large",
        llm_model="gpt-4o"
    )

    req_agent = studio.create_agent(
        name="RequirementsAnalyzer",
        provider="gpt-4o",
        role="Senior business analyst",
        goal="Extract structured requirements from Jira tickets",
        instructions="Parse tickets into structured requirements. Be precise.",
        temperature=0.2,
        memory=10,
        knowledge_base_ids=[kb.id],
        response_model=RequirementsOutput,
        reflection=True,
    )
    req_agent.add_tool(fetch_jira_ticket)

    result = req_agent.run(
        "Fetch and analyze ticket PROJ-101",
        session_id="user_1_project_42"
    )
    print(result.response)
    print(result.structured_output.complexity)
```

---

## 11. KNOWN GAPS / 404s IN DOCS

The following Lyzr ADK docs pages returned 404 — info not confirmed:
- `/lyzr-adk/multi-agent` — No dedicated multi-agent orchestrator class found in docs
- `/lyzr-adk/knowledge-base` — Inferred from examples
- `/lyzr-adk/rai` — RAI params inferred from create_agent signature
- `/lyzr-adk/structured-output` — Inferred from `response_model` param

**Implication:** There is likely NO built-in orchestrator agent class in Lyzr ADK.
Multi-agent orchestration must be implemented manually (sequential pipeline in Python).

---

## 12. LYZR ADK vs STRANDS SDK — QUICK DIFF

| Feature | Strands (AWS) | Lyzr ADK |
|---|---|---|
| Agent creation | `Agent(model, system_prompt, tools)` | `studio.create_agent(name, provider, role, ...)` |
| Model config | `BedrockModel(model_id, region)` | `provider="gpt-4o"` string |
| Tools | `MCPClient` (subprocess MCP servers) | `agent.add_tool(python_function)` |
| Memory | `MemorySessionManager` (AWS managed) | `memory=N` + `session_id` param |
| Multi-agent | `Agent(tools=[other_agent])` possible | Manual pipeline in Python |
| Hosting | AWS AgentCore (container on Lambda) | Lyzr Studio API (cloud, no infra) |
| Cold start | Slow (container warmup) | Fast (API call) |
| Responsible AI | Manual (you build it) | Built-in (`reflection`, `bias_check`) |
| RAG | Bedrock KB (AWS-native) | Qdrant via `create_knowledge_base()` |
| Observability | CloudWatch + OpenTelemetry | Lyzr Studio dashboard |
| Setup complexity | High (IAM, VPC, ECR, containers) | Low (API key, pip install) |
| Vendor lock-in | AWS-locked | Lyzr-hosted, multi-LLM |
| Cost model | AWS per-token + infra costs | Lyzr token credits |
| GitAgent support | No native support | Lyzr adapter exists |
