"""
Lyzr documentation search tool — exposed to CodeGeneratorAgent.

Replaces the AgentCore Docs MCP server used in the Strands version.
Uses httpx to fetch and search docs.lyzr.ai at generation time so the
code generator always has up-to-date API references.
"""

import httpx
import re
from typing import Optional


LYZR_DOCS_BASE = "https://docs.lyzr.ai"

# Pages the code generator is most likely to need
_DOC_PAGES = {
    "overview":          "/lyzr-adk/overview",
    "agents":            "/lyzr-adk/agents",
    "tools":             "/lyzr-adk/tools",
    "memory":            "/lyzr-adk/memory",
    "streaming":         "/lyzr-adk/streaming",
    "structured-output": "/lyzr-adk/structured-output",
    "knowledge-base":    "/lyzr-adk/knowledge-base",
    "rai":               "/lyzr-adk/rai",
    "multi-agent":       "/lyzr-adk/multi-agent",
}


def _extract_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _search_text(text: str, query: str, context_chars: int = 600) -> list[str]:
    """Return snippets around each occurrence of the query (case-insensitive)."""
    query_lower = query.lower()
    text_lower  = text.lower()
    snippets    = []
    start = 0
    while True:
        idx = text_lower.find(query_lower, start)
        if idx == -1:
            break
        s = max(0, idx - context_chars // 2)
        e = min(len(text), idx + context_chars // 2)
        snippets.append("..." + text[s:e].strip() + "...")
        start = idx + len(query_lower)
        if len(snippets) >= 3:
            break
    return snippets


def search_lyzr_docs(query: str, page: str = "agents") -> str:
    """
    Search the Lyzr ADK documentation for a query and return relevant snippets.

    Use this tool to look up correct Lyzr ADK API usage, class names,
    method signatures, and code patterns while generating agent code.

    Args:
        query: What to search for, e.g. "add_tool", "session_id", "response_model",
               "create_knowledge_base", "streaming", "memory".
        page:  Which docs page to search. One of:
               overview, agents, tools, memory, streaming, structured-output,
               knowledge-base, rai, multi-agent

    Returns:
        Relevant documentation snippets as a string, or an error message.
    """
    path = _DOC_PAGES.get(page, _DOC_PAGES["agents"])
    url  = LYZR_DOCS_BASE + path

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url)

        if resp.status_code != 200:
            return (
                f"[lyzr_docs] Page '{page}' returned HTTP {resp.status_code}. "
                f"Try page='overview' or refer to https://docs.lyzr.ai"
            )

        text     = _extract_text(resp.text)
        snippets = _search_text(text, query)

        if not snippets:
            # Return first 1000 chars of the page as fallback context
            return (
                f"[lyzr_docs] No exact match for '{query}' on '{page}'. "
                f"Page content (truncated):\n\n{text[:1000]}"
            )

        return (
            f"[lyzr_docs] Results for '{query}' on {url}:\n\n"
            + "\n\n---\n\n".join(snippets)
        )

    except httpx.TimeoutException:
        return f"[lyzr_docs] Timeout fetching {url}. Use cached knowledge."
    except Exception as e:
        return f"[lyzr_docs] Error: {e}. Use cached Lyzr ADK knowledge."


def get_lyzr_code_template(template_name: str) -> str:
    """
    Return a boilerplate code template for common Lyzr ADK patterns.

    Use this before writing agent code to get a correct starting structure.

    Args:
        template_name: One of:
          "basic_agent"         — minimal single-agent setup
          "agent_with_tools"    — agent with custom tool functions
          "agent_with_memory"   — agent with session-scoped memory
          "agent_with_rag"      — agent with knowledge base
          "multi_agent_pipeline"— sequential multi-agent pipeline
          "structured_output"   — agent with Pydantic response_model
          "streaming_agent"     — agent with streaming response

    Returns:
        Python code template as a string.
    """
    templates: dict[str, str] = {

        "basic_agent": '''\
from lyzr import Studio
from dotenv import load_dotenv
import os

load_dotenv()

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    agent = studio.create_agent(
        name="MyAgent",
        provider="openai/gpt-4o",
        role="Your agent role",
        goal="What the agent should achieve",
        instructions="Detailed instructions for the agent behaviour",
        temperature=0.7,
    )
    response = agent.run("Hello!")
    print(response.response)
''',

        "agent_with_tools": '''\
from lyzr import Studio
from dotenv import load_dotenv
import os

load_dotenv()

def my_tool(param: str) -> str:
    """Brief description of what this tool does.

    Args:
        param: Description of the parameter.
    Returns:
        Description of the return value.
    """
    return f"Result for {param}"

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    agent = studio.create_agent(
        name="ToolAgent",
        provider="openai/gpt-4o",
        role="Agent role",
        goal="Agent goal",
        instructions="Use available tools to complete tasks.",
        temperature=0.5,
    )
    agent.add_tool(my_tool)
    response = agent.run("Use the tool with value 'test'")
    print(response.response)
''',

        "agent_with_memory": '''\
from lyzr import Studio
from dotenv import load_dotenv
import os

load_dotenv()

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    agent = studio.create_agent(
        name="MemoryAgent",
        provider="openai/gpt-4o",
        role="Conversational assistant",
        goal="Maintain context across a conversation",
        instructions="Remember what the user has told you. Reference earlier context.",
        temperature=0.7,
        memory=30,              # Keep last 30 messages per session
    )

    SESSION_ID = "user_123_session_456"

    # Turn 1
    r1 = agent.run("My name is Alice.", session_id=SESSION_ID)
    print(r1.response)

    # Turn 2 — agent remembers the name
    r2 = agent.run("What is my name?", session_id=SESSION_ID)
    print(r2.response)
''',

        "agent_with_rag": '''\
from lyzr import Studio
from dotenv import load_dotenv
import os

load_dotenv()

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    kb = studio.create_knowledge_base(
        name="my_knowledge_base",
        vector_store="qdrant",
        embedding_model="text-embedding-3-large",
        llm_model="gpt-4o",
        description="Domain knowledge for the agent",
    )
    # Populate knowledge base
    # kb.add_pdf("path/to/document.pdf")
    # kb.add_website("https://your-docs.com")
    # kb.add_text("Plain text knowledge...")

    agent = studio.create_agent(
        name="RAGAgent",
        provider="openai/gpt-4o",
        role="Knowledge-grounded assistant",
        goal="Answer questions using the knowledge base",
        instructions="Always query the knowledge base before answering. Cite sources.",
        temperature=0.2,
        knowledge_base_ids=[kb.id],
    )
    response = agent.run("What does the documentation say about X?")
    print(response.response)
''',

        "multi_agent_pipeline": '''\
from lyzr import Studio
from dotenv import load_dotenv
import os

load_dotenv()

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    # Agent 1 — first stage
    agent1 = studio.create_agent(
        name="StageOneAgent",
        provider="openai/gpt-4o",
        role="Stage 1 processor",
        goal="Transform raw input into structured data",
        instructions="Process the input and output structured results.",
        temperature=0.3,
    )

    # Agent 2 — second stage (receives output of agent1)
    agent2 = studio.create_agent(
        name="StageTwoAgent",
        provider="openai/gpt-4o",
        role="Stage 2 processor",
        goal="Enrich structured data with additional context",
        instructions="Take the structured input and enrich it.",
        temperature=0.5,
    )

    # Agent 3 — final stage
    agent3 = studio.create_agent(
        name="StageThreeAgent",
        provider="openai/gpt-4o",
        role="Report generator",
        goal="Produce a final formatted report",
        instructions="Synthesize all inputs into a clean final report.",
        temperature=0.4,
    )

    # Sequential pipeline — each agent's output feeds the next
    user_input = "Your input here"
    r1 = agent1.run(user_input)
    r2 = agent2.run(r1.response)
    r3 = agent3.run(r2.response)
    print(r3.response)
''',

        "structured_output": '''\
from lyzr import Studio
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import os

load_dotenv()

class AnalysisResult(BaseModel):
    summary: str
    key_points: List[str]
    sentiment: str          # positive | neutral | negative
    confidence: float       # 0.0 - 1.0
    recommended_action: Optional[str] = None

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    agent = studio.create_agent(
        name="AnalysisAgent",
        provider="openai/gpt-4o",
        role="Data analyst",
        goal="Produce structured analysis of input text",
        instructions=(
            "Analyse the provided text thoroughly. "
            "Return structured output matching the schema exactly."
        ),
        temperature=0.1,
        response_model=AnalysisResult,   # Enforces Pydantic schema
    )
    result = agent.run("Analyse this: \'The product launch was a great success.\'")
    structured: AnalysisResult = result.structured_output
    print(structured.summary)
    print(structured.sentiment)
    print(structured.key_points)
''',

        "streaming_agent": '''\
from lyzr import Studio
from dotenv import load_dotenv
import os

load_dotenv()

with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:
    agent = studio.create_agent(
        name="StreamingAgent",
        provider="openai/gpt-4o",
        role="Streaming assistant",
        goal="Provide real-time streamed responses",
        instructions="Respond naturally to user messages.",
        temperature=0.7,
    )

    print("Response: ", end="", flush=True)
    for chunk in agent.run("Tell me a short story about a robot.", stream=True):
        print(chunk.content, end="", flush=True)
        if chunk.done:
            print()   # newline after stream ends
            break
''',
    }

    template = templates.get(template_name)
    if not template:
        available = ", ".join(templates.keys())
        return f"[lyzr_docs] Unknown template '{template_name}'. Available: {available}"
    return f"# Lyzr ADK Template: {template_name}\n\n```python\n{template}\n```"
