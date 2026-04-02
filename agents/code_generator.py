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
    import re as _re
    env_text = _ENV_PATH.read_text() if _ENV_PATH.exists() else ""
    # Only skip if the key exists as an ACTIVE (uncommented) line — not a comment
    active_pattern = _re.compile(rf"^\s*{_re.escape(env_key)}\s*=", _re.MULTILINE)
    if not active_pattern.search(env_text):
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
    import re as _re

    # Derive agent name: take first 4 meaningful words from the problem description
    _words = _re.findall(r"[a-z0-9]+", requirements.problem.lower())
    _stop  = {"a", "an", "the", "that", "this", "and", "or", "for", "to", "of", "with", "using", "via", "i", "we"}
    _key   = [w for w in _words if w not in _stop][:4]
    agent_name = "-".join(_key) if _key else "my-agent"

    # Derive skill names from the FULL tools list — no cap
    skill_names = []
    if requirements.tools:
        for t in requirements.tools:
            skill_names.append(_re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-"))
    if not skill_names:
        # Infer tool names from problem when tools list is empty (e.g. after shortcut trigger)
        # Use first 2 key words to form a sensible default tool name
        _tool_base = "-".join(_key[:2]) if len(_key) >= 2 else "process-request"
        skill_names = [_tool_base]

    # Derive tool yaml names (same as tools, kebab-case)
    tool_yaml_names = skill_names[:]

    # LLM provider — use the user's preference if captured, else default
    llm_provider = getattr(requirements, "llm_provider", None) or "openai/gpt-4o"

    base = f"""
Generate a complete, portable AI agent package based on these requirements.
The package MUST include BOTH: (A) Lyzr ADK runtime code AND (B) GitAgent spec files.

REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

═══════════════════════════════════
PART A — LYZR ADK CODE FILES
═══════════════════════════════════
- Tech stack: Lyzr ADK (Python)
- LLM provider: {llm_provider} — use this EXACT string in studio.create_agent(provider="{llm_provider}")
- Use search_lyzr_docs() to verify any API you're unsure about
- Use get_lyzr_code_template() to start from a correct base structure
- Generate: agent.py, tools/*.py, requirements.txt, .env.example, README.md
- requirements.txt MUST always include: lyzr-adk, python-dotenv, httpx, pydantic
- .env.example MUST contain EVERY environment variable referenced in ANY tool file — no exceptions

SPECIFIC REQUIREMENTS:
Problem:      {requirements.problem}
Target users: {requirements.target_users}
Tools needed: {', '.join(requirements.tools) if requirements.tools else 'none specified — infer sensible tool names from the problem description'}
Triggers:     {', '.join(requirements.triggers) if requirements.triggers else 'chat_ui'}
Integrations: {', '.join(requirements.integrations) if requirements.integrations else 'none'}
Storage:      {', '.join(requirements.storage) if requirements.storage else _format_storage(requirements)}

MULTI-USER: {'Yes — use session_id=user_id in every agent.run() call' if requirements.multi_user.enabled else 'No — single user'}
{f'Roles: {requirements.multi_user.roles}' if requirements.multi_user.enabled else ''}

═══════════════════════════════════
PART B — GITAGENT SPEC FILES (CRITICAL)
═══════════════════════════════════
Generate these GitAgent open-standard files so the agent passes `gitagent validate`:

1. agent.yaml  — root spec file. STRICT SCHEMA RULES (violations cause validate to fail):
   - `name`: string, kebab-case e.g. "{agent_name}"
   - `version`: string e.g. "1.0.0"
   - `description`: string (one sentence)
   - `skills`: ARRAY OF STRINGS — each string is a folder name under skills/
     CORRECT:   skills:\n  - {skill_names[0]}
     WRONG:     skills:\n  - name: {skill_names[0]}   ← objects are INVALID
   - `tools`: ARRAY OF BARE TOOL NAMES — no path prefix, no .yaml extension
     Pattern must match "^[a-z][a-z0-9-]*$" — only lowercase letters, digits, hyphens
     gitagent resolves tools automatically: it looks for tools/<name>.yaml on disk.
     CORRECT:   tools:\n  - {tool_yaml_names[0]}
     WRONG:     tools:\n  - tools/{tool_yaml_names[0]}.yaml  ← path prefix INVALID
     WRONG:     tools:\n  - {tool_yaml_names[0]}.yaml        ← .yaml extension INVALID
     WRONG:     tools:\n  - name: {tool_yaml_names[0]}       ← objects are INVALID
   - `runtime`: OBJECT (not a string)
     CORRECT:   runtime:\n  max_turns: 50\n  timeout: 300
     WRONG:     runtime: "lyzr"  ← strings are INVALID
   - `model`: object with `preferred` field only
     CORRECT:   model:\n  preferred: openai/gpt-4o
   - `author`: string (your name or "generated")
   - Do NOT include: repository, env, input, output, agents array, or any extra fields

2. SOUL.md  — agent identity. Plain markdown, NO frontmatter needed.
   Write 3–5 paragraphs describing: who this agent is, its personality,
   communication style, and what it values. Be specific to the use case.

3. RULES.md  — hard constraints. Plain markdown, NO frontmatter needed.
   Write 5–8 numbered rules the agent must NEVER violate.
   Keep rules specific and concrete (not generic AI safety platitudes).

4. skills/{skill_names[0]}/SKILL.md  — one SKILL.md per skill folder.
   STRICT FRONTMATTER RULES (violations cause validate to fail):
   - The file MUST begin with YAML frontmatter delimited by ---
   - ONLY TWO frontmatter fields are allowed: name and description. No others.
     Adding ANY other field (version, author, states, triggers, etc.) causes "additional properties" errors.
     CORRECT frontmatter (exactly this, nothing more):
       ---
       name: "skill-name"
       description: "One sentence description of this skill."
       ---
     WRONG (extra fields cause validate to fail):
       ---
       name: "skill-name"
       version: "1.0.0"     ← INVALID extra field
       description: "..."
       author: "generated"  ← INVALID extra field
       ---
   - After frontmatter, write a markdown description of what this skill does.

   Generate one SKILL.md for each skill: {', '.join(f'skills/{s}/SKILL.md' for s in skill_names)}

5. tools/<tool-name>.yaml  — one YAML per tool (MCP-compatible schema).
   FILE NAMING RULE: Use pure kebab-case for ALL file names — hyphens only, NO underscores.
   The .yaml filename must exactly match the bare name used in agent.yaml tools array.
   If agent.yaml says `- search-knowledge-base`, the file is `tools/search-knowledge-base.yaml`.
   Use this exact structure:
   ```
   name: tool-name
   description: "What this tool does"
   input_schema:
     type: object
     properties:
       param_name:
         type: string
         description: "Parameter description"
     required: [param_name]
   implementation:
     type: script
     path: tools/tool_name.py
     runtime: python3
   annotations:
     read_only: true
     idempotent: true
   ```
   Generate one tool YAML for each tool: {', '.join(f'tools/{t}.yaml' for t in tool_yaml_names)}
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

Use this EXACT delimiter format. Do NOT use JSON for file content.

Step 1: Output a metadata JSON block:
---META_START---
{
  "summary": "2-3 sentence description of what was generated",
  "next_steps": ["pip install -r requirements.txt", "cp .env.example .env", "gitagent validate", "python agent.py"],
  "error": null
}
---META_END---

Step 2: For EVERY file, use this delimiter format:
---FILE_START: agent.py---
# file content here
---FILE_END---

Step 3: Repeat for ALL files. You MUST output ALL of these:

LYZR ADK FILES:
  agent.py
  tools/<tool_name>.py        (one per tool)
  requirements.txt
  .env.example
  README.md

GITAGENT SPEC FILES (required for portability):
  agent.yaml                         (spec-compliant — see schema rules above)
  SOUL.md                            (agent identity, plain markdown)
  RULES.md                           (hard constraints, plain markdown)
  skills/<skill-name>/SKILL.md       (one per skill — YAML frontmatter required, all values MUST be strings)
  tools/<tool-name>.yaml             (one per tool — MCP input_schema format)

NEVER put file content inside JSON. ALWAYS use ---FILE_START/END--- delimiters.
Output ALL files — Lyzr ADK code AND GitAgent spec files together.
"""
