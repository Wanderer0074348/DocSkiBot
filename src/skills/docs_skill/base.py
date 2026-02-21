from pathlib import Path
from langchain_core.tools import BaseTool

WORKSPACE = Path.home() / "AgentWorkspace"
WORKSPACE.mkdir(exist_ok=True)


class WorkspaceTool(BaseTool):
    """Base class for all tools that operate on the agent workspace.
    Inherit from this instead of BaseTool directly — any shared config,
    auth clients, or utilities added here are automatically available
    to every tool without repeating imports.
    """
    workspace: Path = WORKSPACE

    model_config = {"arbitrary_types_allowed": True}
