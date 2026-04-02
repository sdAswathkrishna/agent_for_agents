"""
SQLite storage for projects.
Replaces DynamoDB from the Strands version — removes all AWS infra dependency
for the Lyzr rebuild. aiosqlite gives async access compatible with FastAPI.
"""

import aiosqlite
import json
import os
from datetime import datetime
from typing import Optional

from models.schemas import Project, ProjectStatus, ConversationState, Requirements

DB_PATH = os.getenv("DB_PATH", "./agent_for_agents.db")


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    project_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'gathering',
    conversation_state  TEXT NOT NULL DEFAULT 'intro',
    requirements        TEXT NOT NULL DEFAULT '{}',
    diagram_path        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    approved_at         TEXT
);
"""


async def init_db() -> None:
    """Create tables on startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE)
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD helpers
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_project(row: tuple) -> Project:
    (project_id, name, status, conv_state,
     requirements_json, diagram_path,
     created_at, updated_at, approved_at) = row

    return Project(
        project_id=project_id,
        name=name,
        status=ProjectStatus(status),
        conversation_state=ConversationState(conv_state),
        requirements=Requirements(**json.loads(requirements_json)),
        diagram_path=diagram_path,
        created_at=created_at,
        updated_at=updated_at,
        approved_at=approved_at,
    )


async def create_project(name: str) -> Project:
    project = Project(name=name)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO projects
              (project_id, name, status, conversation_state,
               requirements, diagram_path, created_at, updated_at, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.project_id,
                project.name,
                project.status.value,
                project.conversation_state.value,
                project.requirements.model_dump_json(),
                project.diagram_path,
                project.created_at,
                project.updated_at,
                project.approved_at,
            ),
        )
        await db.commit()
    return project


async def get_project(project_id: str) -> Optional[Project]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_project(row) if row else None


async def list_projects() -> list[Project]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_project(r) for r in rows]


async def update_project(
    project_id: str,
    status:             Optional[ProjectStatus]      = None,
    conversation_state: Optional[ConversationState]  = None,
    requirements:       Optional[Requirements]        = None,
    diagram_path:       Optional[str]                 = None,
    approved_at:        Optional[str]                 = None,
) -> Optional[Project]:
    project = await get_project(project_id)
    if not project:
        return None

    if status             is not None: project.status             = status
    if conversation_state is not None: project.conversation_state = conversation_state
    if requirements       is not None: project.requirements       = requirements
    if diagram_path       is not None: project.diagram_path       = diagram_path
    if approved_at        is not None: project.approved_at        = approved_at
    project.updated_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE projects SET
              status=?, conversation_state=?, requirements=?,
              diagram_path=?, updated_at=?, approved_at=?
            WHERE project_id=?
            """,
            (
                project.status.value,
                project.conversation_state.value,
                project.requirements.model_dump_json(),
                project.diagram_path,
                project.updated_at,
                project.approved_at,
                project_id,
            ),
        )
        await db.commit()
    return project


async def delete_project(project_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM projects WHERE project_id = ?", (project_id,)
        )
        await db.commit()
    return True
