"""Minimal Task Workbench runner.

Usage:
  python3 -m workbench.run examples/hello_file.task.yaml --workspace /tmp/demo
  python3 -m workbench.run examples/generic_json_integrity.task.json --workspace /tmp/demo-json
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def _parse_scalar(v: str) -> Any:
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_task(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        task = json.loads(text)
    else:
        if yaml is None:
            raise RuntimeError("PyYAML is required for YAML tasks; use .json or install pyyaml in a venv")
        task = yaml.safe_load(text)
    if not isinstance(task, dict):
        raise ValueError(f"task file must parse to an object/dict: {path}")
    return task


def render(obj: Any, ctx: Dict[str, Any]) -> Any:
    if isinstance(obj, str):
        def repl(m: re.Match[str]) -> str:
            key = m.group(1).strip()
            cur: Any = ctx
            for part in key.split('.'):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return m.group(0)
            return str(cur)
        return re.sub(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}", repl, obj)
    if isinstance(obj, list):
        return [render(x, ctx) for x in obj]
    if isinstance(obj, dict):
        return {k: render(v, ctx) for k, v in obj.items()}
    return obj


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **data: Any) -> None:
        rec = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def _normalize_argv(argv: Any) -> List[str]:
    if not isinstance(argv, list) or not argv:
        raise ValueError("command_argv/argv must be a non-empty list")
    return [str(x) for x in argv]


def _display_command(argv: List[str] | None = None, command: str | None = None) -> str:
    if argv is not None:
        return shlex.join(argv)
    return command or ""


def run_argv(argv: List[str], cwd: Path, timeout: int, env: Dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        shell=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env={**os.environ, **env},
    )


def run_shell(command: str, cwd: Path, timeout: int, env: Dict[str, str]) -> subprocess.CompletedProcess[str]:
    # SECURITY(workbench): shell execution is only for trusted/local task seeds
    # with explicit allow_shell=true. Prefer command_argv/argv for all external
    # or parameterized tasks so rendered params cannot become shell syntax.
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env={**os.environ, **env},
    )


def run_verifier(spec: Dict[str, Any], workspace: Path, ctx: Dict[str, Any]) -> Dict[str, Any]:
    typ = spec.get("type")
    rendered = render(spec, ctx)
    if typ == "python":
        mod_name, func_name = rendered["call"].split(":", 1)
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        return func(workspace=workspace, params=rendered.get("params", {}), ctx=ctx)
    if typ == "command":
        timeout = int(rendered.get("timeout_seconds", 60))
        if "argv" in rendered or "command_argv" in rendered:
            argv = _normalize_argv(rendered.get("argv", rendered.get("command_argv")))
            cp = run_argv(argv, workspace, timeout, env={})
            passed = cp.returncode == 0
            return {"passed": passed, "returncode": cp.returncode, "stdout": cp.stdout[-4000:], "stderr": cp.stderr[-4000:], "argv": argv, "command": _display_command(argv=argv), "shell": False}
        if "command" in rendered:
            cmd = str(rendered["command"])
            if not _as_bool(rendered.get("allow_shell"), False):
                return {"passed": False, "reason": "shell verifier requires allow_shell: true; prefer argv", "command": cmd, "shell": True}
            cp = run_shell(cmd, workspace, timeout, env={})
            passed = cp.returncode == 0
            return {"passed": passed, "returncode": cp.returncode, "stdout": cp.stdout[-4000:], "stderr": cp.stderr[-4000:], "command": cmd, "shell": True}
    raise ValueError(f"unknown verifier type: {typ!r}")


def write_return_note(path: Path, task: Dict[str, Any], run_id: str, status: str, ctx: Dict[str, Any], command_result: Dict[str, Any], verifier_results: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append(f"# Return Note — {task.get('name', 'unnamed')}\n")
    lines.append(f"- run_id: `{run_id}`")
    lines.append(f"- status: **{status}**")
    lines.append(f"- created_at: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    lines.append(f"- workspace: `{ctx['workspace']}`")
    lines.append("")
    lines.append("## 1. Work Order")
    lines.append(task.get("goal", "(no goal)"))
    lines.append("")
    lines.append("## 2. Command")
    if command_result:
        lines.append(f"- command: `{command_result.get('command')}`")
        if "shell" in command_result:
            lines.append(f"- shell: `{command_result.get('shell')}`")
        lines.append(f"- returncode: `{command_result.get('returncode')}`")
        if command_result.get("error"):
            lines.append(f"- error: {command_result.get('error')}")
    else:
        lines.append("- no command (verification-only task)")
    lines.append("")
    lines.append("## 3. Verifier Results")
    if verifier_results:
        for i, res in enumerate(verifier_results, 1):
            verdict = "PASS" if res.get("passed") else "FAIL"
            lines.append(f"### {i}. {verdict}")
            lines.append("```json")
            lines.append(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
            lines.append("```")
    else:
        lines.append("- no verifier results recorded")
    lines.append("")
    lines.append("## 4. Evidence")
    for item in task.get("evidence", []):
        lines.append(f"- {render(item, ctx)}")
    if not task.get("evidence"):
        lines.append("- See `ledger.jsonl`, `stdout.txt`, and `stderr.txt` in this run directory.")
    lines.append("")
    lines.append("## 5. Gotchas / Risks")
    for item in task.get("gotchas", []):
        lines.append(f"- {render(item, ctx)}")
    if not task.get("gotchas"):
        lines.append("- None declared by task seed; inspect failures before reusing.")
    lines.append("")
    lines.append("## 6. Return Seeds")
    for item in task.get("return_seeds", []):
        lines.append(f"- {render(item, ctx)}")
    if not task.get("return_seeds"):
        lines.append("- If this run taught a reusable workflow, turn it into a skill/checklist.")
    lines.append("")
    lines.append("## WORKBENCH STATUS")
    lines.append(f"- verifier_count: `{len(verifier_results)}`")
    lines.append("- shell commands require explicit `allow_shell: true`; prefer `command_argv` / verifier `argv`.")
    lines.append("- zero-verifier runs fail unless `allow_no_verifiers: true` is set explicitly.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _finish(run_dir: Path, ledger: Ledger, task: Dict[str, Any], run_id: str, status: str, ctx: Dict[str, Any], cmd_res: Dict[str, Any], verifier_results: List[Dict[str, Any]], rc: int) -> int:
    ledger.write("run_finished", status=status)
    write_return_note(run_dir / "return_note.md", task, run_id, status, ctx, cmd_res, verifier_results)
    print(run_dir)
    return rc


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", type=Path)
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    ap.add_argument("--runs-dir", type=Path, default=None)
    ap.add_argument("--set", dest="sets", action="append", default=[], help="override param as key=value")
    args = ap.parse_args(argv)

    task = load_task(args.task)
    params = dict(task.get("params", {}))
    for item in args.sets:
        if "=" not in item:
            raise SystemExit(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        params[k] = _parse_scalar(v)

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    runs_root = (args.runs_dir.resolve() if args.runs_dir else workspace / ".workbench" / "runs")
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(run_dir / "ledger.jsonl")
    ctx: Dict[str, Any] = {"workspace": str(workspace), "run_id": run_id, "run_dir": str(run_dir), "params": params}

    ledger.write("run_started", run_id=run_id, task=str(args.task), workspace=str(workspace), params=params)

    cmd_res: Dict[str, Any] = {}
    command = task.get("command")
    command_argv = task.get("command_argv", task.get("argv"))
    if command_argv is not None:
        rendered_argv = _normalize_argv(render(command_argv, ctx))
        timeout = int(task.get("timeout_seconds", 300))
        display = _display_command(argv=rendered_argv)
        ledger.write("command_started", command=display, argv=rendered_argv, timeout_seconds=timeout, shell=False)
        cp = run_argv(rendered_argv, workspace, timeout, env={"LTWB_RUN_DIR": str(run_dir)})
        (run_dir / "stdout.txt").write_text(cp.stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(cp.stderr, encoding="utf-8")
        cmd_res = {"command": display, "argv": rendered_argv, "shell": False, "returncode": cp.returncode, "stdout_path": "stdout.txt", "stderr_path": "stderr.txt"}
        ledger.write("command_finished", **cmd_res)
        if cp.returncode != 0 and task.get("fail_fast_on_command_error", True):
            return _finish(run_dir, ledger, task, run_id, "failed", ctx, cmd_res, [], 1)
    elif command:
        if not _as_bool(task.get("allow_shell"), False):
            cmd_res = {"command": str(command), "shell": True, "returncode": None, "error": "shell command requires allow_shell: true; prefer command_argv"}
            (run_dir / "stdout.txt").write_text("", encoding="utf-8")
            (run_dir / "stderr.txt").write_text(cmd_res["error"] + "\n", encoding="utf-8")
            ledger.write("command_rejected", **cmd_res)
            verifier_results = [{"passed": False, "reason": cmd_res["error"], "shell": True}]
            return _finish(run_dir, ledger, task, run_id, "failed", ctx, cmd_res, verifier_results, 2)
        rendered_cmd = render(str(command), ctx)
        timeout = int(task.get("timeout_seconds", 300))
        ledger.write("command_started", command=rendered_cmd, timeout_seconds=timeout, shell=True)
        cp = run_shell(rendered_cmd, workspace, timeout, env={"LTWB_RUN_DIR": str(run_dir)})
        (run_dir / "stdout.txt").write_text(cp.stdout, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(cp.stderr, encoding="utf-8")
        cmd_res = {"command": rendered_cmd, "shell": True, "returncode": cp.returncode, "stdout_path": "stdout.txt", "stderr_path": "stderr.txt"}
        ledger.write("command_finished", **cmd_res)
        if cp.returncode != 0 and task.get("fail_fast_on_command_error", True):
            return _finish(run_dir, ledger, task, run_id, "failed", ctx, cmd_res, [], 1)
    else:
        (run_dir / "stdout.txt").write_text("", encoding="utf-8")
        (run_dir / "stderr.txt").write_text("", encoding="utf-8")

    verifier_results: List[Dict[str, Any]] = []
    for spec in task.get("verifiers", []):
        ledger.write("verifier_started", verifier=spec)
        try:
            res = run_verifier(spec, workspace, ctx)
        except Exception as exc:  # fail closed; keep a return note instead of crashing
            res = {
                "passed": False,
                "reason": "verifier exception",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "verifier": spec,
            }
        verifier_results.append(res)
        ledger.write("verifier_finished", result=res)

    if not verifier_results and not _as_bool(task.get("allow_no_verifiers"), False):
        verifier_results.append({"passed": False, "reason": "no verifiers declared; set allow_no_verifiers: true only for explicitly unchecked tasks"})
        ledger.write("verifier_finished", result=verifier_results[-1])

    status = "passed" if verifier_results and all(r.get("passed") for r in verifier_results) else "failed"
    if not verifier_results and _as_bool(task.get("allow_no_verifiers"), False):
        status = "passed" if cmd_res.get("returncode", 0) == 0 else "failed"
    return _finish(run_dir, ledger, task, run_id, status, ctx, cmd_res, verifier_results, 0 if status == "passed" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
