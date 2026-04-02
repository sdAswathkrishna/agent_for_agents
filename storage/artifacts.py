"""
Local filesystem artifact storage.
Replaces S3 from the Strands version.

Structure:
  ./artifacts/{project_id}/
      agent.py
      tools/
          my_tool.py
      requirements.txt
      README.md
      diagram/
          architecture.png
"""

import os
import json
import zipfile
import aiofiles
from pathlib import Path
from typing import Optional

from models.schemas import ArtifactMeta, GeneratedFile

ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "./artifacts")


def _project_dir(project_id: str) -> Path:
    return Path(ARTIFACTS_DIR) / project_id


async def save_artifact(
    project_id: str,
    file_path: str,
    content: str | bytes,
    file_type: str = "code",
) -> ArtifactMeta:
    """Write a single artifact file to disk."""
    full_path = _project_dir(project_id) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "wb" if isinstance(content, bytes) else "w"
    async with aiofiles.open(full_path, mode) as f:
        await f.write(content)

    return ArtifactMeta(
        path=file_path,
        type=file_type,
        size_bytes=full_path.stat().st_size,
    )


async def save_generated_files(
    project_id: str,
    files: list[GeneratedFile],
) -> list[ArtifactMeta]:
    """Persist all files returned by the CodeGeneratorAgent."""
    metas = []
    for gf in files:
        meta = await save_artifact(project_id, gf.path, gf.content, gf.type)
        metas.append(meta)
    return metas


async def get_artifact(project_id: str, file_path: str) -> Optional[str]:
    """Read artifact content as string (text files only)."""
    full_path = _project_dir(project_id) / file_path
    if not full_path.exists():
        return None
    async with aiofiles.open(full_path, "r") as f:
        return await f.read()


async def list_artifacts(project_id: str) -> list[ArtifactMeta]:
    """List all artifacts for a project."""
    base = _project_dir(project_id)
    if not base.exists():
        return []

    metas = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(base))
            ext = p.suffix.lower()
            file_type = (
                "readme"  if p.name.lower().startswith("readme") else
                "yaml"    if ext in (".yaml", ".yml")            else
                "config"  if ext == ".json"                      else
                "code"
            )
            metas.append(ArtifactMeta(
                path=rel,
                type=file_type,
                size_bytes=p.stat().st_size,
            ))
    return metas


async def delete_project_artifacts(project_id: str) -> None:
    """Remove all artifacts for a project."""
    import shutil
    base = _project_dir(project_id)
    if base.exists():
        shutil.rmtree(base)


def create_zip(project_id: str, project_name: str) -> Optional[str]:
    """
    Zip all artifacts for a project and return the zip path.
    Synchronous — call via executor if needed inside async context.
    """
    base = _project_dir(project_id)
    if not base.exists():
        return None

    zip_path = base.parent / f"{project_name}-agent.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in base.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(base))
    return str(zip_path)


async def save_diagram(project_id: str, diagram_bytes: bytes, filename: str = "architecture.png") -> str:
    """Save a diagram PNG and return its relative path."""
    rel_path = f"diagram/{filename}"
    await save_artifact(project_id, rel_path, diagram_bytes, "diagram")
    return str(_project_dir(project_id) / rel_path)
