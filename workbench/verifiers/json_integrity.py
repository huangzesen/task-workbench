from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from workbench.safety import safe_workspace_path


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional_int(params: Dict[str, Any], key: str) -> int | None:
    value = params.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _sample(items: Iterable[Any], limit: int = 20) -> List[Any]:
    out: List[Any] = []
    for item in items:
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _split_fields(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(x) for x in value]


def _get_dotted(data: Any, key: str) -> Any:
    cur = data
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


def _json_files(directory: Path, pattern: str = "**/*.json") -> List[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob(pattern) if p.is_file())


def index_json_files_by_stem(directory: Path, *, pattern: str = "**/*.json") -> Dict[str, Path]:
    """Index JSON files by filename stem and fail closed on duplicate stems.

    This is intentionally domain-neutral: any project that treats
    JSON filename stems as card IDs can reuse it. Duplicate stems are ambiguous
    even when they live in different subdirectories, so they are verifier errors
    rather than warnings.
    """

    by_stem: Dict[str, Path] = {}
    duplicates: Dict[str, List[str]] = {}
    for p in _json_files(directory, pattern):
        stem = p.stem
        if stem in by_stem:
            duplicates.setdefault(stem, [str(by_stem[stem])]).append(str(p))
            continue
        by_stem[stem] = p
    if duplicates:
        duplicate_text = "; ".join(
            f"{stem}: {', '.join(paths)}" for stem, paths in sorted(duplicates.items())
        )
        raise ValueError(f"duplicate JSON stems in generated tree: {duplicate_text}")
    return by_stem


def json_collection_health(*, workspace: Path, params: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Generic JSON artifact integrity gate.

    Checks only machine-verifiable invariants that apply across domains:
    directory/path containment, JSON parseability, minimum/exact counts,
    duplicate filename stems, duplicate values for an optional id field, and
    presence of required fields. Domain-specific correctness belongs in a
    project-specific verifier layered on top.
    """

    rel = str(params["path"])
    directory = safe_workspace_path(workspace, rel)
    pattern = str(params.get("glob", "**/*.json"))
    min_count = int(params.get("min_count", 1))
    expected_count = _optional_int(params, "expected_count")
    require_unique_stem = _as_bool(params.get("unique_stem"), True)
    id_field = str(params.get("id_field", "")).strip()
    require_unique_id = _as_bool(params.get("unique_id"), bool(id_field))
    required_fields = _split_fields(params.get("required_fields"))

    if not directory.exists():
        return {"passed": False, "path": str(directory), "reason": "missing directory"}
    if not directory.is_dir():
        return {"passed": False, "path": str(directory), "reason": "path is not a directory"}

    files = _json_files(directory, pattern)
    failures: List[str] = []
    parse_errors: List[Dict[str, str]] = []
    missing_fields: List[Dict[str, Any]] = []
    ids: Dict[str, str] = {}
    duplicate_ids: Dict[str, List[str]] = {}
    duplicate_stems: Dict[str, List[str]] = {}
    stems: Dict[str, str] = {}

    for path in files:
        stem = path.stem
        if require_unique_stem:
            if stem in stems:
                duplicate_stems.setdefault(stem, [stems[stem]]).append(str(path))
            else:
                stems[stem] = str(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            parse_errors.append({"path": str(path), "error": repr(exc)})
            continue
        if required_fields:
            missing = []
            for field in required_fields:
                try:
                    _get_dotted(data, field)
                except KeyError:
                    missing.append(field)
            if missing:
                missing_fields.append({"path": str(path), "missing": missing})
        if id_field:
            try:
                raw_id = _get_dotted(data, id_field)
            except KeyError:
                missing_fields.append({"path": str(path), "missing": [id_field]})
                continue
            card_id = str(raw_id)
            if require_unique_id:
                if card_id in ids:
                    duplicate_ids.setdefault(card_id, [ids[card_id]]).append(str(path))
                else:
                    ids[card_id] = str(path)

    if len(files) < min_count:
        failures.append("json_count_below_min")
    if expected_count is not None and len(files) != expected_count:
        failures.append("json_count_expected_mismatch")
    if parse_errors:
        failures.append("json_parse_error")
    if duplicate_stems:
        failures.append("duplicate_json_stems")
    if duplicate_ids:
        failures.append("duplicate_json_ids")
    if missing_fields:
        failures.append("required_json_field_missing")

    return {
        "passed": not failures,
        "path": str(directory),
        "glob": pattern,
        "failures": failures,
        "json_count": len(files),
        "min_count": min_count,
        "expected_count": expected_count,
        "unique_stem": require_unique_stem,
        "id_field": id_field or None,
        "unique_id": require_unique_id,
        "required_fields": required_fields,
        "parse_errors_count": len(parse_errors),
        "parse_errors_sample": _sample(parse_errors),
        "duplicate_stems_count": len(duplicate_stems),
        "duplicate_stems_sample": _sample(
            [{"stem": stem, "paths": paths} for stem, paths in sorted(duplicate_stems.items())]
        ),
        "duplicate_ids_count": len(duplicate_ids),
        "duplicate_ids_sample": _sample(
            [{"id": card_id, "paths": paths} for card_id, paths in sorted(duplicate_ids.items())]
        ),
        "missing_fields_count": len(missing_fields),
        "missing_fields_sample": _sample(missing_fields),
        "notes": [
            "This is a domain-neutral JSON artifact gate; project-specific semantic correctness belongs in a layered verifier.",
        ],
    }
