"""Safety helpers shared by Task Workbench verifiers."""
from __future__ import annotations

from pathlib import Path


def safe_workspace_path(workspace: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``workspace`` and reject path traversal.

    Absolute paths are allowed only if they are still inside the workspace. This
    keeps task/verifier params from reading or writing arbitrary host paths.
    """

    root = workspace.resolve()
    path = Path(rel)
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"path escapes workspace: {rel!r}")
    return resolved
