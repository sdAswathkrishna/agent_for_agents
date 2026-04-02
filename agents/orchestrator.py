"""
OrchestratorAgent — Lyzr ADK implementation.

KEY DIFFERENCES FROM STRANDS VERSION (documented for comparison.md):

  STRANDS:
    - Docker container on AWS AgentCore Runtime (separate deployment per agent)
    - Invoked via boto3.invoke_agent_runtime() over HTTP
    - MCPClient for MCP tool servers (native first-class support)
    - AWS AgentCore MemorySessionManager for session persistence
    - State extracted by parsing <state>JSON</state> from raw response text
    - @app.entrypoint decorator (no parens — critical gotcha)

  LYZR ADK:
    - Python object in-process inside FastAPI/CLI — zero infrastructure
    - Direct method call: orchestrator.chat(message, session_id, ...)
    - Tools as Python functions via agent.add_tool() — MCP requires manual bridge
    - Memory via session_id param (Lyzr manages it server-side) — much simpler
    - State extraction via response_model (flat Pydantic) — cleaner than regex
    - No deployment config, no IAM, no Docker

RESPONSE_MODEL LESSON LEARNED (updated after full testing):
  response_model in Lyzr ADK passes the Pydantic schema to OpenAI's strict
  response_format JSON mode. OpenAI requires ALL fields to be in `required`,
  but Pydantic fields with defaults produce empty `required` arrays.
  Error: "Invalid schema for response_format: 'required' is required to be
  supplied and to be an array including every key in properties."

  The OrchestratorAgent uses NO response_model. Instead:
    1. _MANDATORY_JSON_HEADER prepended to instructions forces JSON-only output
    2. _build_output() parses result.response as JSON via json_repair
    3. _parse_from_text() is the final fallback (Strands-style <state>JSON</state>)

  The CodeGeneratorAgent (simpler output, no tool loop) works fine with
  response_model=CodeGeneratorOutput — confirmed in testing.
  This is a real developer experience finding documented in comparison.md.
"""

import os
import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from lyzr import Studio

from models.schemas import (
    OrchestratorOutput,
    OrchestratorStateModel,
    ConversationState,
    Requirements,
)
from tools.diagram_tool import generate_diagram

load_dotenv()

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "orchestrator_system.txt"
_ENV_PATH    = Path(__file__).parent.parent / ".env"


def _persist_agent_id(env_key: str, agent_id: str) -> None:
    """
    Append LYZR_*_AGENT_ID=<id> to .env so the next run reuses the same agent.

    Without this, studio.create_agent() runs every startup and litters the
    Lyzr Studio platform with duplicate agent cards (discovered: 32 duplicates
    created during testing before this pattern was added).
    """
    import re as _re
    env_text = _ENV_PATH.read_text() if _ENV_PATH.exists() else ""
    # Only skip if the key exists as an ACTIVE (uncommented) line — not a comment
    active_pattern = _re.compile(rf"^\s*{_re.escape(env_key)}\s*=", _re.MULTILINE)
    if not active_pattern.search(env_text):
        with open(_ENV_PATH, "a") as f:
            f.write(f"\n{env_key}={agent_id}\n")
        os.environ[env_key] = agent_id


class OrchestratorAgent:
    """
    Wraps the Lyzr ADK agent for 6-state requirement gathering.

    One agent instance is reused across all requests.
    Session isolation per project is handled via session_id.
    """

    def __init__(self, studio: Studio):
        self._studio = studio
        self._agent  = None
        self._build()

    def _build(self) -> None:
        instructions = _PROMPT_PATH.read_text()

        # LESSON LEARNED (documented in comparison.md):
        # response_model=OrchestratorStateModel FAILS because Lyzr ADK passes the
        # Pydantic model to OpenAI's strict response_format JSON mode, which requires
        # ALL fields in `required`. Pydantic fields with defaults produce empty `required`,
        # causing: "Invalid schema: 'required' is required to include every key in properties."
        #
        # Fix: Do NOT use response_model for this agent. Instead:
        #   1. Prepend _MANDATORY_JSON_HEADER to force JSON-only output
        #   2. Parse the raw response text as JSON manually in _build_output()
        #
        # GET-OR-CREATE PATTERN (critical for platform hygiene):
        # studio.create_agent() always creates a NEW agent on Lyzr's servers.
        # We store the agent ID in LYZR_ORCHESTRATOR_AGENT_ID (.env) on first run,
        # then reuse it via agents.get(id) on all subsequent runs.
        # Without this, every app restart/test creates a new card on the platform.
        # (Learned the hard way: 32 duplicate agents were created during testing.)
        existing_id = os.getenv("LYZR_ORCHESTRATOR_AGENT_ID")
        if existing_id:
            self._agent = self._studio.agents.get(existing_id)
        else:
            self._agent = self._studio.create_agent(
                name="OrchestratorAgent",
                provider=os.getenv("LLM_PROVIDER", "openai/gpt-4o"),
                role="Expert AI agent architect and requirements engineer",
                goal=(
                    "Guide users through a structured 6-state conversation to gather "
                    "complete requirements for their AI agent, then generate an "
                    "architecture diagram to confirm the design."
                ),
                instructions=_MANDATORY_JSON_HEADER + instructions + _STATE_OUTPUT_INSTRUCTIONS,
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                memory=30,
                # NOTE: response_model intentionally omitted — see lesson above.
            )
            _persist_agent_id("LYZR_ORCHESTRATOR_AGENT_ID", self._agent.id)

        # Register MCP bridge tool — the key cross-framework comparison point
        # Strands: MCPClient(lambda: stdio_client(...)) in 5 lines
        # Lyzr ADK: manual bridge function + add_tool() — see tools/diagram_tool.py
        self._agent.add_tool(generate_diagram)

    def chat(
        self,
        message: str,
        session_id: str,
        current_state: str = "intro",
        current_requirements: Optional[dict] = None,
    ) -> OrchestratorOutput:
        """
        Send a user message and get a full OrchestratorOutput back.

        Args:
            message:               User message
            session_id:            Unique ID per project (replaces AgentCore session)
            current_state:         Current conversation state name
            current_requirements:  Requirements collected so far (as dict)

        Returns:
            OrchestratorOutput with message, next state, updated requirements,
            and optional diagram path.
        """
        reqs_json = json.dumps(current_requirements or {}, indent=2)

        context_prompt = (
            f"[SYSTEM CONTEXT — do not repeat to user]\n"
            f"Current state: {current_state}\n"
            f"Requirements so far:\n{reqs_json}\n"
            f"[END SYSTEM CONTEXT]\n\n"
            f"User: {message}"
        )

        result = self._agent.run(context_prompt, session_id=session_id)

        return self._build_output(result, current_state, current_requirements or {})

    def _build_output(
        self,
        result,
        current_state: str,
        current_requirements: dict,
    ) -> OrchestratorOutput:
        """
        Build full OrchestratorOutput from the agent result.

        Since response_model is not used (see _build docstring), result is an
        AgentResponse. We parse the JSON from result.response directly.
        The _MANDATORY_JSON_HEADER ensures the LLM outputs pure JSON every turn.
        """
        if hasattr(result, "response"):
            response_text = result.response or ""
        else:
            response_text = str(result)

        # Primary path: parse JSON from the response text
        # The mandatory header ensures output IS JSON (no markdown fences, no plain text)
        try:
            import json_repair  # same library Lyzr's ResponseParser uses
            data = json_repair.loads(response_text)
            if isinstance(data, dict):
                state_model = OrchestratorStateModel(**{
                    k: v for k, v in data.items()
                    if k in OrchestratorStateModel.model_fields
                })
                # Parse state string → enum (with fallback)
                try:
                    conv_state = ConversationState(state_model.conversation_state)
                except ValueError:
                    conv_state = ConversationState(current_state)

                # Merge new requirements dict into current requirements
                requirements = _merge_requirements(
                    current_requirements,
                    state_model.requirements,  # now a plain dict, not a JSON string
                )

                return OrchestratorOutput(
                    message=state_model.message or "Please continue.",
                    conversation_state=conv_state,
                    extracted_requirements=requirements,
                    is_complete=state_model.is_complete,
                    diagram_path=state_model.diagram_path,
                )
        except Exception:
            pass

        # Fallback: extract from <state>JSON</state> tags (Strands-style)
        return _parse_from_text(response_text, current_state, current_requirements)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _merge_requirements(current: dict, new_reqs: Optional[dict]) -> Requirements:
    """Merge new requirements dict into current requirements dict."""
    if not new_reqs:
        try:
            return Requirements(**current) if current else Requirements()
        except Exception:
            return Requirements()

    try:
        # Merge: new values override current, but skip null/empty values
        merged = {**current, **{k: v for k, v in new_reqs.items() if v}}
        return Requirements(**merged)
    except Exception:
        try:
            return Requirements(**current)
        except Exception:
            return Requirements()


def _parse_from_text(text: str, current_state: str, current_requirements: dict) -> OrchestratorOutput:
    """
    Fallback: extract state from raw text response.
    Same pattern used in the Strands version for all state extraction.
    Kept as fallback when response_model fails.
    """
    import re

    state    = current_state
    is_done  = False
    req_data = current_requirements.copy()

    match = re.search(r"<state>(.*?)</state>", text, re.DOTALL)
    if match:
        try:
            data  = json.loads(match.group(1))
            state = data.get("conversationState", state)
            is_done = data.get("isComplete", False)
            if "extractedRequirements" in data:
                req_data.update(data["extractedRequirements"])
            # Strip state block from message
            text = re.sub(r"<state>.*?</state>", "", text, flags=re.DOTALL).strip()
        except Exception:
            pass

    try:
        conv_state = ConversationState(state)
    except ValueError:
        conv_state = ConversationState(current_state)

    try:
        requirements = Requirements(**req_data)
    except Exception:
        requirements = Requirements()

    return OrchestratorOutput(
        message=text or "Please continue.",
        conversation_state=conv_state,
        extracted_requirements=requirements,
        is_complete=is_done,
    )


def _fallback_output(text: str, current_state: str, current_requirements: dict) -> OrchestratorOutput:
    try:
        state = ConversationState(current_state)
    except ValueError:
        state = ConversationState.INTRO
    try:
        requirements = Requirements(**current_requirements)
    except Exception:
        requirements = Requirements()
    return OrchestratorOutput(
        message=text,
        conversation_state=state,
        extracted_requirements=requirements,
        is_complete=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MANDATORY JSON header — prepended BEFORE the system prompt so the LLM sees
# the output constraint FIRST, before any conversational instructions.
# Without this, the LLM reads state descriptions and responds conversationally,
# producing plain text that response_model cannot parse.
# ─────────────────────────────────────────────────────────────────────────────

_MANDATORY_JSON_HEADER = """\
ABSOLUTE OUTPUT RULE — THIS OVERRIDES EVERYTHING ELSE:
Every single response you produce MUST be a raw JSON object.
Do NOT write any plain text. Do NOT write markdown. Do NOT start with "Hello".
Your ENTIRE response must start with { and end with }.
NEVER put text before { or after }.
Your conversational message to the user goes inside the "message" field of the JSON.

Example of the ONLY acceptable response format:
{"message": "Hello! Tell me about the agent you want to build.", "conversation_state": "intro", "is_complete": false, "diagram_path": null, "requirements": {"problem": "...", "target_users": "..."}}

Now, here are your operating instructions:

"""


# ─────────────────────────────────────────────────────────────────────────────
# Additional instructions appended to orchestrator system prompt
# Tells the agent exactly what JSON fields to populate in response_model
# ─────────────────────────────────────────────────────────────────────────────

_STATE_OUTPUT_INSTRUCTIONS = """

═══════════════════════════════════════════════════════════════════
STRUCTURED OUTPUT INSTRUCTIONS (CRITICAL — follow exactly)
═══════════════════════════════════════════════════════════════════

You MUST return a valid JSON object every turn with these fields:

{
  "message": "Your full conversational response to the user goes here",
  "conversation_state": "intro",   // one of: intro, requirements, tech, architecture, complete
  "is_complete": false,            // true ONLY after architecture diagram is generated
  "diagram_path": null,            // EXACT PATH extracted from generate_diagram() result — see below
  "requirements": {}               // JSON object of all requirements gathered so far (NOT a string)
}

HOW TO SET diagram_path:
  - Call generate_diagram() to get a result string.
  - The result looks like: "[MATPLOTLIB] Diagram saved to: ./artifacts/diagram/architecture.png"
  - Extract ONLY the file path after "saved to: " — e.g. "./artifacts/diagram/architecture.png"
  - Set diagram_path to THAT PATH STRING — nothing else, no brackets, no prefix.
  - If the result starts with "[STUB]", set diagram_path to null.
  - NEVER invent or guess the path — only use what the tool actually returns.

For the "requirements" field, output a plain JSON OBJECT (not a string) with all
requirements gathered so far. ALWAYS populate "requirements" after every turn.

Example:
"requirements": {
  "problem": "email triage for support inbox",
  "target_users": "support teams",
  "tools": ["triage_email", "classify_priority"],
  "triggers": ["chat_ui"],
  "tech_stack": "lyzr-adk"
}

Only include fields that have actual values. Omit fields with no data yet.

IMPORTANT:
- Put your entire user-facing response in the "message" field
- Valid conversation_state values: intro, requirements, tech, architecture, complete
- Set "is_complete": true ONLY after the architecture diagram is generated
- ALWAYS update "requirements" each turn with the latest cumulative requirements
- "requirements" must be a JSON object, NOT a quoted string
"""
