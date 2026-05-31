from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from workbench.safety import safe_workspace_path


def file_contains(*, workspace: Path, params: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    rel = str(params["path"])
    needle = str(params.get("contains", ""))
    path = safe_workspace_path(workspace, rel)
    ok_exists = path.exists() and path.is_file()
    text = path.read_text(encoding="utf-8") if ok_exists else ""
    ok_contains = needle in text if needle else True
    return {"passed": bool(ok_exists and ok_contains), "path": str(path), "exists": ok_exists, "contains": needle, "contains_ok": ok_contains, "size": len(text)}


def file_absent(*, workspace: Path, params: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    rel = str(params["path"])
    path = safe_workspace_path(workspace, rel)
    exists = path.exists()
    return {"passed": not exists, "path": str(path), "exists": exists}


def json_path_count_at_least(*, workspace: Path, params: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    path = safe_workspace_path(workspace, str(params["path"]))
    min_count = int(params.get("min_count", 1))
    key = params.get("key")
    if not path.exists():
        return {"passed": False, "path": str(path), "reason": "missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cur = data
        if key:
            for part in str(key).split('.'):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return {"passed": False, "path": str(path), "key": key, "reason": f"missing key component: {part}"}
        count = len(cur) if hasattr(cur, "__len__") else int(cur)
    except Exception as exc:
        return {"passed": False, "path": str(path), "key": key, "reason": f"invalid json/count: {exc}"}
    return {"passed": count >= min_count, "path": str(path), "key": key, "count": count, "min_count": min_count}
