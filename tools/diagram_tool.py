"""
Diagram generation tool — exposed to OrchestratorAgent via agent.add_tool().

This file is the KEY comparison point between Strands SDK and Lyzr ADK:

  STRANDS: has native MCPClient class with first-class MCP support.
    from strands.tools.mcp import MCPClient
    client = MCPClient(lambda: stdio_client(StdioServerParameters(...)))
    with client:
        tools = client.list_tools_sync()       # direct tool registration
        agent = Agent(model=model, tools=tools) # MCP tools injected natively

  LYZR ADK: no native MCP client. Must bridge manually:
    1. Use the `mcp` Python library to spawn an MCP subprocess
    2. Wrap the result as a regular Python function
    3. Pass the function via agent.add_tool()

  FINDINGS (documented for comparison.md):
    - Lyzr CAN use MCP servers but requires ~30 lines of bridge code per tool
    - Strands registers all MCP tools in one line (list_tools_sync())
    - Lyzr's approach is more explicit but more work; Strands is more ergonomic
    - Both approaches work in production; Strands has a clear DX advantage here

Fallback chain:
  1. MCP mode   → spawn awslabs.aws-diagrams-mcp-server@latest via uvx
  2. Local mode → use Python `diagrams` library directly
  3. Stub mode  → return text description (diagrams lib not installed)
"""

import os
import json
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# MCP bridge — manually calling an MCP stdio server from Lyzr ADK
# This is the "bridge pattern" that compensates for Lyzr's missing MCPClient
# ─────────────────────────────────────────────────────────────────────────────

async def _call_mcp_diagram_server(description: str, output_path: str) -> Optional[str]:
    """
    Bridge: spawn the AWS Diagrams MCP server, call generate_diagram, return path.

    NOTE: In Strands this would be automatic via:
        MCPClient(lambda: stdio_client(StdioServerParameters(command="uvx", args=[...])))
    In Lyzr ADK we must do it manually using the mcp library.
    """
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command="uvx",
            args=["awslabs.aws-diagrams-mcp-server@latest"],
            env={**os.environ},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # List available tools (mirrors Strands list_tools_sync())
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]

                if "generate_diagram" not in tool_names:
                    return None

                result = await session.call_tool(
                    "generate_diagram",
                    arguments={
                        "description": description,
                        "output_path": output_path,
                    },
                )

                # Extract content
                if result.content:
                    for block in result.content:
                        if hasattr(block, "text"):
                            return block.text
                        if hasattr(block, "data"):   # base64 image
                            import base64
                            img_bytes = base64.b64decode(block.data)
                            with open(output_path, "wb") as f:
                                f.write(img_bytes)
                            return output_path

    except FileNotFoundError:
        # uvx not installed — expected in many environments
        return None
    except Exception as e:
        print(f"[diagram_tool] MCP server error: {e}")
        return None

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Local fallback — Python diagrams library
# ─────────────────────────────────────────────────────────────────────────────

def _generate_diagram_local(description: str, output_path: str) -> str:
    """
    Fallback: generate architecture diagram using the Python `diagrams` library.
    Parses key AWS service mentions from the description and renders a PNG.
    """
    try:
        from diagrams import Diagram, Cluster
        from diagrams.aws.compute import Lambda
        from diagrams.aws.database import Dynamodb, RDS
        from diagrams.aws.storage import S3
        from diagrams.aws.network import APIGateway
        from diagrams.aws.ml import Sagemaker
        from diagrams.onprem.client import User
        from diagrams.custom import Custom

        desc_lower = description.lower()

        output_dir  = str(Path(output_path).parent)
        output_name = Path(output_path).stem

        with Diagram(
            "Agent Architecture",
            filename=str(Path(output_dir) / output_name),
            outformat="png",
            show=False,
        ):
            user = User("User")

            with Cluster("Lyzr ADK Agents"):
                orchestrator   = Lambda("OrchestratorAgent")
                code_generator = Lambda("CodeGeneratorAgent")

            nodes = [orchestrator, code_generator]

            if "dynamodb" in desc_lower or "database" in desc_lower:
                db = Dynamodb("DynamoDB")
                nodes.append(db)
            if "s3" in desc_lower or "storage" in desc_lower:
                store = S3("S3 Storage")
                nodes.append(store)
            if "api" in desc_lower or "gateway" in desc_lower:
                api = APIGateway("API Gateway")
                user >> api >> orchestrator
            else:
                user >> orchestrator

            orchestrator >> code_generator

        final_path = str(Path(output_dir) / f"{output_name}.png")
        return final_path

    except ImportError:
        # diagrams library not installed
        return _generate_diagram_stub(description, output_path)


def _generate_diagram_stub(description: str, output_path: str) -> str:
    """
    Last-resort stub: write a text description when no diagram library is available.
    """
    stub_path = output_path.replace(".png", ".txt")
    Path(stub_path).parent.mkdir(parents=True, exist_ok=True)
    with open(stub_path, "w") as f:
        f.write(f"Architecture Diagram (text stub)\n{'='*40}\n\n{description}\n")
    return stub_path


# ─────────────────────────────────────────────────────────────────────────────
# Public tool function — registered with agent.add_tool()
# ─────────────────────────────────────────────────────────────────────────────

def generate_diagram(description: str, output_path: str = "./artifacts/diagram/architecture.png") -> str:
    """
    Generate an architecture diagram from a system description.

    Tries in order:
    1. AWS Diagrams MCP server (uvx awslabs.aws-diagrams-mcp-server@latest)
    2. Python diagrams library (local, no subprocess)
    3. Text stub (always works)

    Args:
        description: Natural-language description of the agent architecture,
                     including AWS services, components, and data flows.
        output_path: File path where the diagram PNG should be saved.

    Returns:
        Absolute path to the generated file, or an error description.
    """
    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    mode = os.getenv("DIAGRAM_TOOL_MODE", "mcp").lower()

    # ── MCP mode ──────────────────────────────────────────────────────────────
    if mode == "mcp":
        try:
            result = asyncio.run(
                _call_mcp_diagram_server(description, output_path)
            )
            if result:
                return f"[MCP] Diagram saved to: {result}"
            # MCP failed → fall through to local
            print("[diagram_tool] MCP unavailable, falling back to local diagrams library")
        except RuntimeError:
            # asyncio.run() inside existing event loop (e.g. Jupyter / FastAPI)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    _call_mcp_diagram_server(description, output_path)
                )
                result = future.result(timeout=30)
            if result:
                return f"[MCP] Diagram saved to: {result}"

    # ── Local mode ────────────────────────────────────────────────────────────
    result = _generate_diagram_local(description, output_path)
    if result.endswith(".txt"):
        return f"[STUB] No diagram library available. Description saved to: {result}"
    return f"[LOCAL] Diagram saved to: {result}"
