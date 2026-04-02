"""
Pydantic schemas shared across agents, API, and storage.
These models replace the DynamoDB + Decimal patterns from the Strands version.
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class ConversationState(str, Enum):
    INTRO        = "intro"
    REQUIREMENTS = "requirements"
    TECH         = "tech"
    DETAILS      = "details"
    REVIEW       = "review"
    ARCHITECTURE = "architecture"
    COMPLETE     = "complete"


class ProjectStatus(str, Enum):
    GATHERING   = "gathering"
    DESIGNING   = "designing"
    GENERATING  = "generating"
    GENERATED   = "generated"
    APPROVED    = "approved"


class TechStack(str, Enum):
    LYZR_ADK = "lyzr-adk"       # Primary — what the code generator now targets
    STRANDS  = "python-strands"  # Legacy option kept for comparison


# ─────────────────────────────────────────────────────────────────────────────
# Requirements sub-models
# ─────────────────────────────────────────────────────────────────────────────

class MultiUserConfig(BaseModel):
    enabled:            bool       = False
    authentication:     str        = ""
    data_model:         str        = "isolated"   # shared | isolated
    isolated_data:      list[str]  = Field(default_factory=list)
    roles:              list[str]  = Field(default_factory=list)
    admin_capabilities: list[str]  = Field(default_factory=list)


class DynamoDBConfig(BaseModel):
    enabled:    bool       = False
    operations: list[str]  = Field(default_factory=list)
    tables:     list[str]  = Field(default_factory=list)


class S3Config(BaseModel):
    enabled:    bool       = False
    operations: list[str]  = Field(default_factory=list)
    scope:      str        = "specific"   # all | specific


class AuroraVectorConfig(BaseModel):
    enabled:             bool       = False
    table_name:          str        = "documents"
    embedding_model:     str        = ""
    embedding_dimensions: int       = 1536
    operations:          list[str]  = Field(default_factory=list)
    top_k:               int        = 5
    metadata_filters:    list[str]  = Field(default_factory=list)


class AWSServices(BaseModel):
    dynamodb:     DynamoDBConfig     = Field(default_factory=DynamoDBConfig)
    s3:           S3Config           = Field(default_factory=S3Config)
    aurora_vector: AuroraVectorConfig = Field(default_factory=AuroraVectorConfig)


class Requirements(BaseModel):
    problem:        str       = ""
    target_users:   str       = ""
    tools:          list[str] = Field(default_factory=list)
    triggers:       list[str] = Field(default_factory=list)
    tech_stack:     TechStack = TechStack.LYZR_ADK
    multi_user:     MultiUserConfig  = Field(default_factory=MultiUserConfig)
    aws_services:   AWSServices      = Field(default_factory=AWSServices)
    integrations:   list[str]        = Field(default_factory=list)
    error_handling: dict             = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator structured output
# NOTE: Lyzr ADK response_model replaces the <state>JSON</state> embedding
#       pattern used in the Strands version. Cleaner and type-safe.
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorStateModel(BaseModel):
    """
    Lightweight Pydantic model for OrchestratorAgent structured output.

    NOTE: NOT used as response_model (see orchestrator.py lesson).
    Used only for parsing the agent's JSON text response in _build_output().

    requirements is a plain dict (not a JSON-encoded string) to avoid the
    nested-quotes escaping problem: LLM generates "requirements_json": "{"key": "val"}"
    which breaks JSON parsing. A plain object avoids this entirely.
    """
    message:            str           = ""
    conversation_state: str           = "intro"   # plain string, not enum
    is_complete:        bool          = False
    diagram_path:       Optional[str] = None
    requirements:       Optional[dict] = None     # flat dict of requirements gathered


class OrchestratorOutput(BaseModel):
    """
    Full output returned by OrchestratorAgent.chat() to callers.
    Built by combining OrchestratorStateModel + parsed Requirements.
    """
    message:                 str               = ""
    conversation_state:      ConversationState = ConversationState.INTRO
    extracted_requirements:  Requirements      = Field(default_factory=Requirements)
    is_complete:             bool              = False
    diagram_path:            Optional[str]     = None


# ─────────────────────────────────────────────────────────────────────────────
# Code Generator structured output
# ─────────────────────────────────────────────────────────────────────────────

class GeneratedFile(BaseModel):
    path:    str   # e.g. "agent.py", "tools/my_tool.py"
    content: str
    type:    str   = "code"   # code | config | readme | yaml


class CodeGeneratorOutput(BaseModel):
    """
    Structured output from the CodeGeneratorAgent.

    `files`       → list of generated files (path + content)
    `summary`     → 2-3 sentence description of what was generated
    `next_steps`  → ordered list of deploy/test steps
    `error`       → non-null if generation failed
    """
    files:      list[GeneratedFile] = Field(default_factory=list)
    summary:    str                 = ""
    next_steps: list[str]           = Field(default_factory=list)
    error:      Optional[str]       = None


# ─────────────────────────────────────────────────────────────────────────────
# Project model (stored in SQLite)
# ─────────────────────────────────────────────────────────────────────────────

class Project(BaseModel):
    project_id:          str              = Field(default_factory=lambda: str(uuid.uuid4()))
    name:                str              = ""
    status:              ProjectStatus    = ProjectStatus.GATHERING
    conversation_state:  ConversationState = ConversationState.INTRO
    requirements:        Requirements     = Field(default_factory=Requirements)
    diagram_path:        Optional[str]    = None
    created_at:          str              = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at:          str              = Field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_at:         Optional[str]    = None


class ArtifactMeta(BaseModel):
    path:        str
    type:        str       = "code"
    size_bytes:  int       = 0
    created_at:  str       = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ─────────────────────────────────────────────────────────────────────────────
# API request / response bodies
# ─────────────────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = "My Agent"


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message:            str
    conversation_state: ConversationState
    is_complete:        bool             = False
    diagram_path:       Optional[str]    = None


class GenerateResponse(BaseModel):
    status:     str              # "started" | "completed" | "failed"
    message:    str              = ""
    artifacts:  list[ArtifactMeta] = Field(default_factory=list)
