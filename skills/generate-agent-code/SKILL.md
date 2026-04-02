---
name: generate-agent-code
description: "Generate complete, production-ready Lyzr ADK agent code from a requirements specification"
license: MIT
allowed-tools: "search-lyzr-docs get-lyzr-template"
metadata:
  category: code-generation
  framework: lyzr-adk
  output-model: CodeGeneratorOutput
---

## Overview

This skill drives the CodeGeneratorAgent to produce a complete, runnable
Lyzr ADK Python package from a `Requirements` object. Every file must be
correct, complete, and immediately runnable after `pip install -r requirements.txt`.

## Files Always Generated

| File | Required | Description |
|------|----------|-------------|
| `agent.py` | ✅ | Main entry point with Studio + create_agent() |
| `tools/<name>.py` | ✅ per tool | One Python file per tool |
| `requirements.txt` | ✅ | lyzr-adk + all deps |
| `.env.example` | ✅ | All required env vars |
| `README.md` | ✅ | Setup + run + extend instructions |
| `models.py` | if needed | Pydantic output models |
| `storage.py` | if needed | SQLite/DynamoDB helpers |
| `api.py` | if needed | FastAPI wrapper for API trigger |

## Code Quality Standards

### agent.py must:
- Use `with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:`
- Call `studio.create_agent()` with name, provider, role, goal, instructions
- Use `agent.add_tool()` for every tool
- Use `session_id=user_id` in `agent.run()` for multi-user agents
- Include a `main()` function and `if __name__ == "__main__": main()`
- Handle errors — never let exceptions propagate to the user

### tool files must:
- Be standalone — no class wrappers
- Have exactly ONE public function with the tool name
- Have a complete docstring: purpose, args, returns
- Return `str` always (JSON-encoded for structured data)
- Include mock implementation + real API pattern in comments
- Handle all exceptions — return error string, never raise

### Temperature guidelines:
- Analytical/code agents: `0.1 - 0.3`
- Conversational agents: `0.5 - 0.7`
- Creative agents: `0.7 - 1.0`

## Lyzr ADK API Cheat Sheet

```python
# Agent creation
agent = studio.create_agent(
    name="Name", provider="gpt-4o",
    role="Role", goal="Goal", instructions="...",
    temperature=0.7, memory=30,
    response_model=MyPydanticModel,   # optional
    reflection=True,                   # optional
    bias_check=True,                   # optional
    knowledge_base_ids=[kb.id],        # optional
)

# Run
result = agent.run(message, session_id="uid_session")
print(result.response)
print(result.structured_output)   # if response_model set

# Stream
for chunk in agent.run(msg, stream=True):
    print(chunk.content, end="")
    if chunk.done: break

# Tool registration
agent.add_tool(python_function)

# Knowledge base
kb = studio.create_knowledge_base(
    name="kb", vector_store="qdrant",
    embedding_model="text-embedding-3-large", llm_model="gpt-4o"
)
```

## What Not to Generate

- No `from strands import Agent`
- No `from bedrock_agentcore import ...`
- No `@app.entrypoint` decorators
- No AWS container/ECR/Lambda patterns
- No hardcoded credentials
