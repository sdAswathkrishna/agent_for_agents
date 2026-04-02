"""
CodeGeneratorAgent — Lyzr ADK implementation.

Replaces the async Strands + BedrockAgentCoreApp code-generator container.

KEY DIFFERENCES FROM STRANDS VERSION:
  Strands:
    - Docker container on AgentCore Runtime (separate deployment)
    - Fully async: handler returned immediately, wrote result.json to S3
    - Backend polled S3 every 2s until _generation_result.json appeared
    - Response was raw text with embedded JSON — multi-step extraction needed:
        1. Try <json>...</json> tags
        2. Try direct JSON parse
        3. Try ```json...``` blocks
        4. Brace-matching fallback
    - Generated Strands SDK code (now changed to Lyzr ADK code)
    - Rules template loaded from S3 (s3://bucket/templates/rules/)
    - Used AgentCore Docs MCP server for API reference

  Lyzr ADK:
    - Plain Python class, runs in-process — no container, no S3, no polling
    - FastAPI BackgroundTasks handles async — result stored in local dict
    - Structured output via response_model=CodeGeneratorOutput — clean extraction
    - Generates Lyzr ADK code (not Strands)
    - Rules/prompt loaded from local prompts/code_generator_system.txt
    - Uses lyzr_docs_tool.py for API reference lookups

POSITIVE: No async polling complexity. Structured output eliminates JSON extraction.
NEGATIVE: Long-running jobs tie up the process (BackgroundTasks workaround needed).
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from lyzr import Studio

from models.schemas import CodeGeneratorOutput, GeneratedFile, Requirements
from tools.lyzr_docs_tool import search_lyzr_docs, get_lyzr_code_template

load_dotenv()

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "code_generator_system.txt"
_ENV_PATH    = Path(__file__).parent.parent / ".env"


def _persist_agent_id(env_key: str, agent_id: str) -> None:
    """Persist agent ID to .env so subsequent runs reuse the same agent (no duplicates)."""
    env_text = _ENV_PATH.read_text() if _ENV_PATH.exists() else ""
    if env_key not in env_text:
        with open(_ENV_PATH, "a") as f:
            f.write(f"\n{env_key}={agent_id}\n")
        os.environ[env_key] = agent_id


class CodeGeneratorAgent:
    """
    Wraps the Lyzr ADK agent that generates deployable Lyzr ADK code.

    Runs synchronously inside a FastAPI BackgroundTask — no S3 polling loop needed.
    Results are stored in an in-memory dict and retrieved by job ID.
    """

    def __init__(self, studio: Studio):
        self._studio = studio
        self._agent  = None
        self._build()

    def _build(self) -> None:
        instructions = _PROMPT_PATH.read_text()

        # NOTE: response_model intentionally omitted — same reason as OrchestratorAgent.
        # Lyzr ADK strict JSON mode requires all fields in `required`; Pydantic defaults
        # produce empty `required` → OpenAI rejects. See comparison.md for full details.
        #
        # GET-OR-CREATE: reuse persisted agent ID to avoid platform duplicates.
        existing_id = os.getenv("LYZR_CODE_GENERATOR_AGENT_ID")
        if existing_id:
            self._agent = self._studio.agents.get(existing_id)
        else:
            self._agent = self._studio.create_agent(
                name="CodeGeneratorAgent",
                provider=os.getenv("LLM_PROVIDER", "openai/gpt-4o"),
                role="Expert Lyzr ADK engineer and code generator",
                goal=(
                    "Generate complete, production-ready Lyzr ADK agent code from "
                    "a requirements specification. Output all necessary files."
                ),
                instructions=instructions + _CODE_GEN_JSON_FOOTER,
                temperature=0.2,
                memory=20,
            )
            _persist_agent_id("LYZR_CODE_GENERATOR_AGENT_ID", self._agent.id)

        # Lyzr ADK tools — Python functions, not MCP servers
        # In Strands we'd inject the AgentCore Docs MCP server here
        self._agent.add_tool(search_lyzr_docs)
        self._agent.add_tool(get_lyzr_code_template)

    def generate(
        self,
        requirements: Requirements,
        session_id: str,
        refinement_request: Optional[str] = None,
    ) -> CodeGeneratorOutput:
        """
        Generate Lyzr ADK agent code from requirements.

        Args:
            requirements:        Completed requirements from OrchestratorAgent
            session_id:          Session ID for memory context
            refinement_request:  Optional user refinement (re-generation)

        Returns:
            CodeGeneratorOutput with list of GeneratedFile objects
        """
        prompt = _build_generation_prompt(requirements, refinement_request)

        result = self._agent.run(prompt, session_id=session_id)

        # Parse from raw response text.
        # response_model is not used (OpenAI strict schema rejects fields with defaults).
        # The _CODE_GEN_JSON_FOOTER in instructions forces JSON-only output.
        # _extract_output_from_text() handles the fallback chain.
        raw_text = result.response if hasattr(result, "response") else str(result)
        return _extract_output_from_text(raw_text)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_generation_prompt(
    requirements: Requirements,
    refinement_request: Optional[str] = None,
) -> str:
    base = f"""
Generate a complete Lyzr ADK agent based on these requirements.

REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

GENERATION INSTRUCTIONS:
- Tech stack: Lyzr ADK (Python)
- LLM provider: {requirements.tech_stack.value if hasattr(requirements.tech_stack, 'value') else 'lyzr-adk'}
- Use search_lyzr_docs() to verify any API you're unsure about
- Use get_lyzr_code_template() to start from a correct base structure
- Generate agent.py as the main entry point
- Generate tools/ directory with one file per tool
- Generate requirements.txt, .env.example, README.md

SPECIFIC REQUIREMENTS TO IMPLEMENT:
Problem:      {requirements.problem}
Target users: {requirements.target_users}
Tools needed: {', '.join(requirements.tools) if requirements.tools else 'none specified'}
Triggers:     {', '.join(requirements.triggers) if requirements.triggers else 'chat interface'}
Integrations: {', '.join(requirements.integrations) if requirements.integrations else 'none'}

MULTI-USER: {'Yes — use session_id=user_id in every agent.run() call' if requirements.multi_user.enabled else 'No — single user'}
{f'Roles: {requirements.multi_user.roles}' if requirements.multi_user.enabled else ''}

STORAGE:
{_format_storage(requirements)}

Return the CodeGeneratorOutput with all files in the `files` list.
"""

    if refinement_request:
        base += f"\n\nREFINEMENT REQUEST:\n{refinement_request}\nApply these changes to the generated code."

    return base.strip()


def _format_storage(requirements: Requirements) -> str:
    lines = []
    if requirements.aws_services.dynamodb.enabled:
        lines.append(f"- DynamoDB tables: {requirements.aws_services.dynamodb.tables}")
    if requirements.aws_services.s3.enabled:
        lines.append(f"- S3 storage: scope={requirements.aws_services.s3.scope}")
    if requirements.aws_services.aurora_vector.enabled:
        lines.append(f"- Aurora Vector DB: {requirements.aws_services.aurora_vector.table_name}")
    return "\n".join(lines) if lines else "- No persistent storage required"


# ─────────────────────────────────────────────────────────────────────────────
# Fallback extraction (replicates Strands multi-method extraction)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_output_from_text(text: str) -> CodeGeneratorOutput:
    """
    Extract CodeGeneratorOutput from raw text response.

    Extraction chain:
    1. Delimiter format  ---META_START/END--- and ---FILE_START/END---
       (primary — avoids JSON escaping issues with code content)
    2. <json>...</json> tags (legacy fallback)
    3. ```json...``` markdown blocks (legacy fallback)
    4. Return error output
    """
    import re

    # Method 1: Delimiter format (primary — code content not inside JSON)
    meta_match  = re.search(r"---META_START---\s*(.*?)\s*---META_END---",  text, re.DOTALL)
    file_matches = re.findall(r"---FILE_START:\s*(.+?)---\n(.*?)---FILE_END---", text, re.DOTALL)

    if file_matches:
        files = []
        for path, content in file_matches:
            path    = path.strip()
            content = content.rstrip("\n")
            ftype   = "readme" if path.lower().endswith(".md") else \
                      "config" if path.endswith((".yaml", ".yml", ".toml", ".cfg", ".env", ".env.example")) else \
                      "code"
            files.append(GeneratedFile(path=path, content=content, type=ftype))

        summary    = ""
        next_steps = []
        if meta_match:
            try:
                import json_repair
                meta = json_repair.loads(meta_match.group(1))
                summary    = meta.get("summary", "")
                next_steps = meta.get("next_steps", [])
            except Exception:
                pass

        return CodeGeneratorOutput(
            files=files,
            summary=summary or f"Generated {len(files)} file(s) for the agent.",
            next_steps=next_steps,
        )

    # Method 2: <json>...</json> tags
    match = re.search(r"<json>(.*?)</json>", text, re.DOTALL)
    if match:
        try:
            import json_repair
            data = json_repair.loads(match.group(1))
            if isinstance(data, dict):
                return _dict_to_output(data)
        except Exception:
            pass

    # Method 3: Markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            import json_repair
            data = json_repair.loads(match.group(1))
            if isinstance(data, dict):
                return _dict_to_output(data)
        except Exception:
            pass

    # Method 4: Return error
    return CodeGeneratorOutput(
        files=[],
        summary="Code generation failed — could not parse structured output.",
        next_steps=[],
        error=f"Raw response (first 500 chars): {text[:500]}",
    )


def _dict_to_output(data: dict) -> CodeGeneratorOutput:
    files = [
        GeneratedFile(
            path=f.get("path", "unknown.py"),
            content=f.get("content", ""),
            type=f.get("type", "code"),
        )
        for f in data.get("files", [])
    ]
    return CodeGeneratorOutput(
        files=files,
        summary=data.get("summary", ""),
        next_steps=data.get("next_steps", data.get("nextSteps", [])),
        error=data.get("error"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON output mandate — appended to instructions (same approach as orchestrator)
# Forces the LLM to output ONLY a valid JSON object, not prose.
# ─────────────────────────────────────────────────────────────────────────────

_CODE_GEN_JSON_FOOTER = """

═══════════════════════════════════════════════════════════════════
CRITICAL OUTPUT FORMAT — FOLLOW EXACTLY
═══════════════════════════════════════════════════════════════════

Use this EXACT delimiter format. Do NOT use JSON for file content (escaping breaks it).

Step 1: Output a metadata JSON block:
---META_START---
{
  "summary": "2-3 sentence description of what was generated",
  "next_steps": ["pip install -r requirements.txt", "cp .env.example .env", "python agent.py"],
  "error": null
}
---META_END---

Step 2: For each file, use this delimiter format:
---FILE_START: agent.py---
# full file content here
from lyzr import Studio
import os
# ... rest of code ...
---FILE_END---

---FILE_START: tools/order_lookup.py---
# tool code here
def order_lookup(order_id: str) -> str:
    ...
---FILE_END---

Step 3: Repeat ---FILE_START: path--- ... ---FILE_END--- for every file.

Files to generate: agent.py, tools/*.py, requirements.txt, .env.example, README.md

NEVER put file content inside JSON. ALWAYS use the ---FILE_START/END--- delimiters.
"""
