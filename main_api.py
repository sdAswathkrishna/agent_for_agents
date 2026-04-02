"""
FastAPI backend for Agent-for-Agents (Lyzr ADK version).

Replaces the AWS Chalice/Lambda backend from the Strands version.

DIFFERENCES FROM STRANDS BACKEND:
  Strands:
    - AWS Chalice deploying to Lambda + API Gateway
    - JWT authentication via AWS Cognito (required on all routes)
    - DynamoDB for project storage
    - S3 for artifact storage
    - Async polling pattern: /chat → returns requestId → /chat/status/{id}
    - Streaming via SSE endpoint (/chat/stream)
    - Two separate AgentCore container deployments

  Lyzr ADK:
    - FastAPI running locally (uvicorn) — no cloud deployment needed to test
    - No authentication (removed per requirements)
    - SQLite for project storage (aiosqlite)
    - Local filesystem for artifact storage
    - Synchronous chat (agents respond in-process, no polling needed)
    - Streaming via FastAPI StreamingResponse
    - Both agents live in-process as Python objects

POSITIVE: Runs with `uvicorn main_api:app` — no AWS account needed.
NEGATIVE: Not production-ready as-is (no auth, no horizontal scaling, single process).
"""

import os
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from lyzr import Studio

from models.schemas import (
    Project, ProjectStatus, ConversationState,
    CreateProjectRequest, ChatRequest, ChatResponse,
    GenerateResponse, ArtifactMeta,
)
from storage import db, artifacts
from agents.orchestrator import OrchestratorAgent
from agents.code_generator import CodeGeneratorAgent

load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# App lifecycle — init DB + agents on startup
# ─────────────────────────────────────────────────────────────────────────────

_studio:     Optional[Studio]             = None
_orchestrator: Optional[OrchestratorAgent]  = None
_code_gen:   Optional[CodeGeneratorAgent] = None
_executor = ThreadPoolExecutor(max_workers=4)

# In-memory generation job tracker (replaces S3 polling in Strands version)
_generation_jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _studio, _orchestrator, _code_gen

    # Init DB
    await db.init_db()

    # Init Lyzr Studio + agents once (shared across requests via session_id)
    api_key = os.getenv("LYZR_API_KEY")
    if not api_key:
        raise RuntimeError("LYZR_API_KEY not set. Copy .env.example → .env and add your key.")

    _studio       = Studio(api_key=api_key)
    _orchestrator = OrchestratorAgent(_studio)
    _code_gen     = CodeGeneratorAgent(_studio)

    print("✓ Lyzr agents initialised")
    yield

    _studio.__exit__(None, None, None)
    _executor.shutdown(wait=False)


app = FastAPI(
    title="Agent-for-Agents API (Lyzr ADK)",
    description="Builds AI agents via guided conversation. Powered by Lyzr ADK.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve UI — open http://localhost:8000/ui/ in the browser
_UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
if os.path.isdir(_UI_DIR):
    app.mount("/ui", StaticFiles(directory=_UI_DIR, html=True), name="ui")


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "framework": "lyzr-adk"}


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/projects", response_model=Project)
async def create_project(body: CreateProjectRequest):
    return await db.create_project(body.name)


@app.get("/projects", response_model=list[Project])
async def list_projects():
    return await db.list_projects()


@app.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@app.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await db.delete_project(project_id)
    await artifacts.delete_project_artifacts(project_id)
    return {"deleted": project_id}


# ─────────────────────────────────────────────────────────────────────────────
# Chat — synchronous (replaces async polling from Strands version)
#
# Strands: POST /chat → returns requestId → poll /chat/status/{id} until done
# Lyzr:    POST /chat → runs agent in-process → returns response directly
#
# Trade-off: simpler code, but ties up a thread per request.
#            For demo purposes this is fine. Production would use BackgroundTasks.
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/chat", response_model=ChatResponse)
async def chat(project_id: str, body: ChatRequest):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if project.status not in (ProjectStatus.GATHERING, ProjectStatus.DESIGNING):
        raise HTTPException(400, f"Project is in '{project.status}' state — chat not available")

    # Run orchestrator in thread pool (Lyzr ADK is sync, FastAPI is async)
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        _executor,
        lambda: _orchestrator.chat(
            message=body.message,
            session_id=project_id,
            current_state=project.conversation_state.value,
            current_requirements=project.requirements.model_dump(),
        ),
    )

    # Determine next project status
    new_status = project.status
    if output.conversation_state == ConversationState.ARCHITECTURE:
        new_status = ProjectStatus.DESIGNING
    if output.is_complete:
        new_status = ProjectStatus.DESIGNING

    # Copy diagram to project-specific location so it can be served per-project
    if output.diagram_path:
        import shutil
        from pathlib import Path as _Path
        default_diagram = _Path("./artifacts/diagram/architecture.png")
        if default_diagram.exists():
            dest = artifacts._project_dir(project_id) / "diagram" / "architecture.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(default_diagram), str(dest))

    # Update project in DB
    await db.update_project(
        project_id=project_id,
        status=new_status,
        conversation_state=output.conversation_state,
        requirements=output.extracted_requirements,
        diagram_path=output.diagram_path,
    )

    return ChatResponse(
        message=output.message,
        conversation_state=output.conversation_state,
        is_complete=output.is_complete,
        diagram_path=output.diagram_path,
    )


@app.post("/projects/{project_id}/chat/stream")
async def chat_stream(project_id: str, body: ChatRequest):
    """
    Streaming version of chat — uses Lyzr ADK stream=True.

    NOTE: Lyzr ADK streaming works at the LLM token level.
    The state update in the DB happens after the stream completes.
    """
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    context_prompt = (
        f"[SYSTEM CONTEXT]\n"
        f"Current state: {project.conversation_state.value}\n"
        f"Requirements: {project.requirements.model_dump_json()}\n"
        f"[END CONTEXT]\n\n"
        f"User: {body.message}"
    )

    async def token_stream():
        loop = asyncio.get_event_loop()
        collected = []

        def _stream():
            for chunk in _orchestrator._agent.run(context_prompt, session_id=project_id, stream=True):
                collected.append(chunk.content or "")
                yield f"data: {json.dumps({'content': chunk.content, 'done': chunk.done})}\n\n"
                if chunk.done:
                    break

        for sse_event in await loop.run_in_executor(_executor, lambda: list(_stream())):
            yield sse_event

    return StreamingResponse(token_stream(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Code Generation
#
# Strands: async container invocation → S3 polling until result appears
# Lyzr:   BackgroundTask writes to _generation_jobs dict → poll /generate/status
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/generate")
async def generate_code(project_id: str, background_tasks: BackgroundTasks):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if project.conversation_state not in (
        ConversationState.ARCHITECTURE, ConversationState.COMPLETE
    ) and not project.diagram_path:
        raise HTTPException(400, "Complete requirement gathering before generating code")

    await db.update_project(project_id=project_id, status=ProjectStatus.GENERATING)
    _generation_jobs[project_id] = {"status": "running", "message": "Generation started"}

    background_tasks.add_task(_run_generation, project_id, project)

    return {"status": "started", "message": "Code generation in progress"}


@app.get("/projects/{project_id}/generate/status")
async def generation_status(project_id: str):
    """Poll generation status — replaces S3 polling from Strands version."""
    job = _generation_jobs.get(project_id)
    if not job:
        project = await db.get_project(project_id)
        if project and project.status == ProjectStatus.GENERATED:
            return {"status": "completed", "message": "Code generated"}
        return {"status": "not_found"}
    return job


async def _run_generation(project_id: str, project: Project):
    """
    Background task: run CodeGeneratorAgent and store artifacts.
    Replaces the async S3-write + polling pattern from the Strands version.
    """
    loop = asyncio.get_event_loop()
    try:
        output = await loop.run_in_executor(
            _executor,
            lambda: _code_gen.generate(
                requirements=project.requirements,
                session_id=f"{project_id}_codegen",
            ),
        )

        if output.error:
            _generation_jobs[project_id] = {
                "status": "failed",
                "message": output.error,
            }
            await db.update_project(project_id=project_id, status=ProjectStatus.GATHERING)
            return

        # Save files to local filesystem
        await artifacts.save_generated_files(project_id, output.files)

        await db.update_project(
            project_id=project_id,
            status=ProjectStatus.GENERATED,
        )

        _generation_jobs[project_id] = {
            "status": "completed",
            "message": output.summary,
            "files": [f.path for f in output.files],
            "next_steps": output.next_steps,
        }

    except Exception as e:
        _generation_jobs[project_id] = {"status": "failed", "message": str(e)}
        await db.update_project(project_id=project_id, status=ProjectStatus.GATHERING)


# ─────────────────────────────────────────────────────────────────────────────
# Artifacts
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/diagram")
async def get_diagram(project_id: str):
    """Serve the architecture diagram PNG for a project."""
    from pathlib import Path as _Path
    path = artifacts._project_dir(project_id) / "diagram" / "architecture.png"
    if not path.exists():
        raise HTTPException(404, "No diagram available for this project")
    return FileResponse(str(path), media_type="image/png")


@app.get("/projects/{project_id}/artifacts", response_model=list[ArtifactMeta])
async def list_artifacts(project_id: str):
    return await artifacts.list_artifacts(project_id)


@app.get("/projects/{project_id}/artifacts/{file_path:path}")
async def get_artifact(project_id: str, file_path: str):
    content = await artifacts.get_artifact(project_id, file_path)
    if content is None:
        raise HTTPException(404, f"Artifact '{file_path}' not found")
    return {"path": file_path, "content": content}


@app.get("/projects/{project_id}/files")
async def list_files(project_id: str):
    """
    Return the full file tree + content for all generated artifacts.
    Used by the UI to populate the file viewer panel after generation.
    """
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    file_list = await artifacts.list_artifacts(project_id)
    result = []
    for meta in file_list:
        content = await artifacts.get_artifact(project_id, meta.path)
        result.append({
            "path":  meta.path,
            "type":  meta.type,
            "size":  meta.size_bytes,
            "content": content or "",
        })
    return result


@app.get("/projects/{project_id}/download")
async def download_project(project_id: str):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    loop = asyncio.get_event_loop()
    zip_path = await loop.run_in_executor(
        _executor,
        lambda: artifacts.create_zip(project_id, project.name or "agent"),
    )
    if not zip_path:
        raise HTTPException(404, "No artifacts to download")

    return FileResponse(
        path=zip_path,
        filename=f"{project.name or 'agent'}-lyzr-adk.zip",
        media_type="application/zip",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Refinement & Approval
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/refine")
async def refine_code(project_id: str, body: ChatRequest, background_tasks: BackgroundTasks):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.status != ProjectStatus.GENERATED:
        raise HTTPException(400, "Can only refine generated projects")

    await db.update_project(project_id=project_id, status=ProjectStatus.GENERATING)
    _generation_jobs[project_id] = {"status": "running", "message": "Refinement in progress"}

    async def _run_refinement():
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            _executor,
            lambda: _code_gen.generate(
                requirements=project.requirements,
                session_id=f"{project_id}_codegen",
                refinement_request=body.message,
            ),
        )
        if output.error:
            _generation_jobs[project_id] = {"status": "failed", "message": output.error}
            await db.update_project(project_id=project_id, status=ProjectStatus.GENERATED)
            return
        await artifacts.save_generated_files(project_id, output.files)
        await db.update_project(project_id=project_id, status=ProjectStatus.GENERATED)
        _generation_jobs[project_id] = {
            "status": "completed",
            "message": output.summary,
            "files": [f.path for f in output.files],
        }

    background_tasks.add_task(_run_refinement)
    return {"status": "started"}


@app.post("/projects/{project_id}/approve")
async def approve_project(project_id: str):
    from datetime import datetime
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    updated = await db.update_project(
        project_id=project_id,
        status=ProjectStatus.APPROVED,
        approved_at=datetime.utcnow().isoformat(),
    )
    return {"approved": True, "project_id": project_id}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_api:app", host="0.0.0.0", port=8000, reload=True)
