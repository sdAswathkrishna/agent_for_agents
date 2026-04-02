"""
CLI entry point for Agent-for-Agents (Lyzr ADK version).

Run this directly to test the full agent pipeline without the FastAPI server.
This is the simplest way to demo the rebuild vs Strands.

Usage:
    python main.py
    python main.py --project-id existing-id
"""

import os
import sys
import json
import asyncio
import argparse
from dotenv import load_dotenv
from lyzr import Studio

load_dotenv()


def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        print(f"✗ Missing env var: {key}")
        print("  Copy .env.example → .env and fill in your keys.")
        sys.exit(1)
    return val


async def _init_db():
    from storage.db import init_db
    await init_db()


async def run_cli(project_id: str = None):
    _require_env("LYZR_API_KEY")

    await _init_db()

    from storage import db, artifacts
    from agents.orchestrator import OrchestratorAgent
    from agents.code_generator import CodeGeneratorAgent
    from models.schemas import (
        ConversationState, ProjectStatus, Requirements
    )

    with Studio(api_key=os.getenv("LYZR_API_KEY")) as studio:

        orchestrator = OrchestratorAgent(studio)
        code_gen     = CodeGeneratorAgent(studio)

        # Create or load project
        if project_id:
            project = await db.get_project(project_id)
            if not project:
                print(f"✗ Project '{project_id}' not found. Starting fresh.")
                project = await db.create_project("CLI Session")
        else:
            project = await db.create_project("CLI Session")

        print(f"\n{'='*60}")
        print(f"  Agent-for-Agents — Lyzr ADK")
        print(f"  Project ID: {project.project_id}")
        print(f"  State:      {project.conversation_state.value}")
        print(f"{'='*60}")
        print("\nType your message. Type 'generate' when ready to generate code.")
        print("Type 'quit' to exit.\n")

        # ── Conversation Loop ──────────────────────────────────────────────
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break

            if not user_input:
                continue

            if user_input.lower() == "quit":
                print(f"\nProject saved. Resume with: python main.py --project-id {project.project_id}")
                break

            if user_input.lower() == "generate":
                if project.conversation_state not in (
                    ConversationState.ARCHITECTURE, ConversationState.COMPLETE
                ) and not project.diagram_path:
                    print("⚠ Complete the requirement gathering first (finish the conversation).\n")
                    continue

                print("\n→ Generating Lyzr ADK agent code...")
                print("  (This may take 30-60 seconds)\n")

                output = code_gen.generate(
                    requirements=project.requirements,
                    session_id=f"{project.project_id}_codegen",
                )

                if output.error:
                    print(f"✗ Generation failed: {output.error}\n")
                    continue

                # Save artifacts
                metas = await artifacts.save_generated_files(
                    project.project_id, output.files
                )
                await db.update_project(
                    project_id=project.project_id,
                    status=ProjectStatus.GENERATED,
                )

                print(f"✓ Generated {len(output.files)} files:\n")
                for f in output.files:
                    print(f"  📄 {f.path}")

                print(f"\nSummary: {output.summary}\n")
                if output.next_steps:
                    print("Next steps:")
                    for i, step in enumerate(output.next_steps, 1):
                        print(f"  {i}. {step}")

                print(f"\nFiles saved to: ./artifacts/{project.project_id}/")

                zip_path = artifacts.create_zip(
                    project.project_id,
                    project.name or "agent"
                )
                if zip_path:
                    print(f"ZIP ready:      {zip_path}\n")
                break

            # ── Chat with orchestrator ─────────────────────────────────────
            output = orchestrator.chat(
                message=user_input,
                session_id=project.project_id,
                current_state=project.conversation_state.value,
                current_requirements=project.requirements.model_dump(),
            )

            print(f"\nAgent: {output.message}\n")

            if output.diagram_path:
                print(f"  📐 Diagram: {output.diagram_path}\n")

            # Update project state
            new_status = project.status
            if output.conversation_state == ConversationState.ARCHITECTURE:
                new_status = ProjectStatus.DESIGNING

            project = await db.update_project(
                project_id=project.project_id,
                status=new_status,
                conversation_state=output.conversation_state,
                requirements=output.extracted_requirements,
                diagram_path=output.diagram_path,
            )

            if output.is_complete:
                print("✓ Requirements complete! Type 'generate' to produce your agent code.\n")


def main():
    parser = argparse.ArgumentParser(description="Agent-for-Agents CLI (Lyzr ADK)")
    parser.add_argument("--project-id", help="Resume an existing project")
    args = parser.parse_args()

    asyncio.run(run_cli(project_id=args.project_id))


if __name__ == "__main__":
    main()
