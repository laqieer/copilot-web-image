"""Local stdio MCP interface to the native Windows/Edge image generator."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

import generate_image as generator


mcp = MCPServer(
    "copilot-web-image",
    instructions=(
        "Generate PNG images through the Microsoft 365 Copilot website on native "
        "Windows with Edge. The user completes sign-in and MFA in the browser. "
        "Use new absolute output paths and never bypass organizational policies."
    ),
)


class ToolArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError(message)


@dataclass
class GeneratedImage:
    path: str
    width: int
    height: int


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
def generate_image(
    prompt: Annotated[str, Field(min_length=1, description="Image description sent to Copilot.")],
    output: Annotated[str, Field(description="Absolute path to a new .png file; never overwritten.")],
    profile_dir: Annotated[
        str | None, Field(description="Absolute Edge user-data directory; defaults to a dedicated profile.")
    ] = None,
    profile_name: Annotated[
        str | None, Field(description="Profile directory name, such as Default, not a path.")
    ] = None,
    account_index: Annotated[
        int | None, Field(ge=1, description="Only use an offered account position explicitly selected by the user.")
    ] = None,
    timeout: Annotated[float, Field(gt=0, le=1800, description="Image-generation timeout in seconds.")] = 240,
    signin_timeout: Annotated[float, Field(gt=0, le=1800, description="Interactive sign-in timeout in seconds.")] = 180,
    diagnostics_dir: Annotated[str | None, Field(description="Absolute directory for private failure screenshots.")] = None,
) -> GeneratedImage:
    """Generate and save a verified PNG using Copilot in visible native Windows Edge.

    Requires an eligible Microsoft 365 account and permission for browser
    automation. Sign-in and MFA remain interactive. Returns only the saved path
    and dimensions; never reads or exports browser credentials or overwrites files.
    """
    for name, value in (
        ("output", output), ("profile_dir", profile_dir), ("diagnostics_dir", diagnostics_dir),
    ):
        if value is not None and not Path(value).is_absolute():
            raise ToolError(f"{name} must be an absolute path on the Windows host")
    argv = ["--prompt=" + prompt, "--output=" + output]
    for name, value in (
        ("profile-dir", profile_dir),
        ("profile-name", profile_name),
        ("account-index", account_index),
        ("timeout", timeout),
        ("signin-timeout", signin_timeout),
        ("diagnostics-dir", diagnostics_dir),
    ):
        if value is not None:
            argv.append(f"--{name}={value}")
    args = generator.parse_arguments(argv, parser_class=ToolArgumentParser)
    try:
        width, height = generator.run_generation(args, progress=sys.stderr)
    except (generator.PlaywrightError, OSError, ValueError, RuntimeError) as error:
        raise ToolError(str(error)) from error
    return GeneratedImage(path=str(args.output), width=width, height=height)


if __name__ == "__main__":
    mcp.run(transport="stdio")
