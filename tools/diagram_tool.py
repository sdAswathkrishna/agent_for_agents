"""
Diagram generation tool — exposed to OrchestratorAgent via agent.add_tool().

Fallback chain:
  1. MCP mode   — only when DIAGRAM_TOOL_MODE=mcp AND uvx+package are available
  2. Local mode — Python `diagrams` library (requires graphviz system package)
  3. Matplotlib — pure-Python PNG fallback (no system deps)
  4. Text stub  — always succeeds, writes a .txt description

Default is local → matplotlib → stub.  Set DIAGRAM_TOOL_MODE=mcp to re-enable
the AWS Diagrams MCP server path (requires: uvx + awslabs.aws-diagram-mcp-server).

BUG FIXES vs previous version:
  - Coroutine-never-awaited warning: coroutine must be created INSIDE the
    ThreadPoolExecutor thread (via lambda), not in the calling thread.
  - MCP package not available: default is now "local", not "mcp".
  - asyncio.run() inside uvicorn event loop: caught and routed to thread pool.
"""

import os
import json
import asyncio
import textwrap
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# MCP bridge — only used when DIAGRAM_TOOL_MODE=mcp
# ─────────────────────────────────────────────────────────────────────────────

async def _call_mcp_diagram_server(description: str, output_path: str) -> Optional[str]:
    """Spawn the AWS Diagrams MCP server and call generate_diagram."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command="uvx",
            args=["awslabs.aws-diagram-mcp-server@latest"],
            env={**os.environ},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                if "generate_diagram" not in [t.name for t in tools_result.tools]:
                    return None

                result = await session.call_tool(
                    "generate_diagram",
                    arguments={"description": description, "output_path": output_path},
                )

                if result.content:
                    for block in result.content:
                        if hasattr(block, "data"):
                            import base64
                            with open(output_path, "wb") as f:
                                f.write(base64.b64decode(block.data))
                            return output_path
                        if hasattr(block, "text"):
                            return block.text

    except Exception as e:
        print(f"[diagram_tool] MCP server error: {e}")

    return None


def _try_mcp(description: str, output_path: str) -> Optional[str]:
    """
    Run the MCP async call safely regardless of whether there's a running event loop.

    FIX: coroutine must be created INSIDE the thread (via lambda), not passed as
    an already-created coroutine object.  Creating it outside and passing it to
    asyncio.run() in another thread raises 'coroutine was never awaited' when the
    outer call errors before asyncio.run() gets to schedule it.
    """
    try:
        asyncio.get_running_loop()
        # Running inside uvicorn/FastAPI event loop — must use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                lambda: asyncio.run(_call_mcp_diagram_server(description, output_path))
            )
            return future.result(timeout=30)
    except RuntimeError:
        # No running event loop — safe to call asyncio.run() directly
        return asyncio.run(_call_mcp_diagram_server(description, output_path))
    except Exception as e:
        print(f"[diagram_tool] MCP bridge error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Local fallback — Python diagrams library (requires graphviz)
# ─────────────────────────────────────────────────────────────────────────────

def _try_diagrams_library(description: str, output_path: str) -> Optional[str]:
    """Generate PNG via the `diagrams` library.  Returns None if not installed."""
    try:
        from diagrams import Diagram, Cluster
        from diagrams.aws.compute import Lambda
        from diagrams.aws.database import Dynamodb
        from diagrams.aws.storage import S3
        from diagrams.aws.network import APIGateway
        from diagrams.onprem.client import User

        desc_lower = description.lower()
        output_dir  = str(Path(output_path).parent)
        output_stem = Path(output_path).stem

        with Diagram(
            "Agent Architecture",
            filename=str(Path(output_dir) / output_stem),
            outformat="png",
            show=False,
        ):
            user = User("User")
            with Cluster("Agents"):
                main_agent = Lambda("Agent")

            nodes = [main_agent]

            if "dynamodb" in desc_lower or "database" in desc_lower:
                nodes.append(Dynamodb("DynamoDB"))
            if "s3" in desc_lower or "storage" in desc_lower:
                nodes.append(S3("S3"))
            if "api" in desc_lower or "gateway" in desc_lower:
                api = APIGateway("API Gateway")
                user >> api >> main_agent
            else:
                user >> main_agent

        final_path = str(Path(output_dir) / f"{output_stem}.png")
        if Path(final_path).exists():
            return final_path

    except ImportError:
        pass
    except Exception as e:
        print(f"[diagram_tool] diagrams library error: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Matplotlib fallback — pure Python, no system deps
# ─────────────────────────────────────────────────────────────────────────────

def _try_matplotlib(description: str, output_path: str) -> Optional[str]:
    """
    Render a simple architecture PNG using matplotlib.
    No system packages required — matplotlib is already a common dep.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")   # non-interactive backend, safe in server context
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

        desc_lower = description.lower()

        # Determine components to show
        components = ["User"]
        if "api" in desc_lower or "gateway" in desc_lower or "endpoint" in desc_lower:
            components.append("API Layer")
        components.append("Agent")
        if "knowledge" in desc_lower or "rag" in desc_lower or "search" in desc_lower:
            components.append("Knowledge Base")
        if "database" in desc_lower or "dynamodb" in desc_lower or "storage" in desc_lower:
            components.append("Storage")
        if "human" in desc_lower or "escalat" in desc_lower:
            components.append("Human Support")

        n = len(components)
        fig, ax = plt.subplots(figsize=(max(8, n * 2.2), 5))
        ax.set_xlim(0, n)
        ax.set_ylim(0, 3)
        ax.axis("off")
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#1a1a2e")

        box_colors = {
            "User":          "#4ade80",
            "API Layer":     "#60a5fa",
            "Agent":         "#a78bfa",
            "Knowledge Base":"#f59e0b",
            "Storage":       "#f59e0b",
            "Human Support": "#f87171",
        }
        default_color = "#94a3b8"

        box_w, box_h = 1.4, 0.7
        y_center = 1.5
        positions = []

        for i, comp in enumerate(components):
            cx = i + 0.5
            cy = y_center
            positions.append((cx, cy))
            color = box_colors.get(comp, default_color)
            rect = FancyBboxPatch(
                (cx - box_w / 2, cy - box_h / 2), box_w, box_h,
                boxstyle="round,pad=0.06",
                linewidth=1.5,
                edgecolor=color,
                facecolor=color + "22",   # transparent fill
            )
            ax.add_patch(rect)
            ax.text(cx, cy, comp, ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold",
                    wrap=True)

        # Draw arrows between consecutive boxes
        for i in range(len(positions) - 1):
            x1, y1 = positions[i]
            x2, y2 = positions[i + 1]
            ax.annotate(
                "",
                xy=(x2 - box_w / 2 + 0.05, y2),
                xytext=(x1 + box_w / 2 - 0.05, y1),
                arrowprops=dict(
                    arrowstyle="->",
                    color="#94a3b8",
                    lw=1.2,
                    connectionstyle="arc3,rad=0.0",
                ),
            )

        # Title
        ax.set_title(
            "Agent Architecture",
            color="#e2e8f0", fontsize=11, fontweight="bold", pad=10,
        )

        # Description snippet at bottom
        snippet = textwrap.fill(description[:180], width=90)
        fig.text(0.5, 0.04, snippet, ha="center", va="bottom",
                 fontsize=7, color="#64748b", style="italic")

        plt.tight_layout(rect=[0, 0.08, 1, 1])
        plt.savefig(output_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)

        if Path(output_path).exists():
            return output_path

    except ImportError:
        pass
    except Exception as e:
        print(f"[diagram_tool] matplotlib error: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Text stub — always works
# ─────────────────────────────────────────────────────────────────────────────

def _generate_text_stub(description: str, output_path: str) -> str:
    stub_path = str(Path(output_path).with_suffix(".txt"))
    Path(stub_path).parent.mkdir(parents=True, exist_ok=True)
    with open(stub_path, "w") as f:
        f.write(f"Architecture Diagram\n{'=' * 40}\n\n{description}\n")
    return f"[STUB] No diagram library available. Description saved to: {stub_path}"


# ─────────────────────────────────────────────────────────────────────────────
# Public tool — registered with agent.add_tool()
# ─────────────────────────────────────────────────────────────────────────────

def generate_diagram(description: str, output_path: str = "./artifacts/diagram/architecture.png") -> str:
    """
    Generate an architecture diagram PNG from a system description.

    Tries in order:
    1. AWS Diagrams MCP server — only when DIAGRAM_TOOL_MODE=mcp in .env
    2. Python `diagrams` library — local, requires graphviz system package
    3. matplotlib — pure-Python PNG, no system deps required
    4. Text stub — always succeeds

    Args:
        description: Natural-language description of the agent architecture,
                     components, integrations, and data flows.
        output_path: Where to save the PNG.  Parent dirs are created automatically.

    Returns:
        Absolute path to the generated file, or an error string.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    mode = os.getenv("DIAGRAM_TOOL_MODE", "local").lower()

    # ── MCP (explicit opt-in only) ────────────────────────────────────────────
    if mode == "mcp":
        result = _try_mcp(description, output_path)
        if result:
            return f"[MCP] Diagram saved to: {result}"
        print("[diagram_tool] MCP unavailable, falling back to local")

    # ── diagrams library ──────────────────────────────────────────────────────
    result = _try_diagrams_library(description, output_path)
    if result:
        return f"[LOCAL] Diagram saved to: {result}"

    # ── matplotlib fallback ───────────────────────────────────────────────────
    result = _try_matplotlib(description, output_path)
    if result:
        return f"[MATPLOTLIB] Diagram saved to: {result}"

    # ── text stub ─────────────────────────────────────────────────────────────
    return _generate_text_stub(description, output_path)
