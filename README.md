# Task Workbench

A small, local task runner for turning ad-hoc automation checks into repeatable task seeds.

A task seed is a JSON or YAML file that describes:

1. a command to run,
2. one or more verifiers that judge the result, and
3. short notes that should be written into a run report.

Each run writes a ledger and a return note under `.workbench/runs/` (or a custom `--runs-dir`). The goal is not to replace full evaluation frameworks, CI systems, or benchmark suites. It is a lightweight way to package a concrete task with objective checks so it can be rerun and inspected later.

## What it is

- A deterministic local runner for task seed files.
- A verifier gate: success is decided by verifier results, not by a model or operator saying the task "looks done".
- A run artifact writer: each run produces `ledger.jsonl`, `return_note.md`, `stdout.txt`, and `stderr.txt`.
- A simple place to add project-specific Python verifiers.

## What it is not

- Not an agent framework.
- Not a benchmark leaderboard.
- Not a replacement for CI.
- Not a general sandbox. Commands run on your machine; review task seeds before running them.

## Quick start

```bash
git clone https://github.com/huangzesen/task-workbench.git
cd task-workbench
python3 -m workbench.run examples/hello_file.task.yaml --workspace /tmp/task-workbench-demo
```

The last printed line is the run directory, for example:

```text
/tmp/task-workbench-demo/.workbench/runs/20260531T120000Z-abc12345
```

Inspect:

```bash
cat /tmp/task-workbench-demo/.workbench/runs/*/return_note.md
cat /tmp/task-workbench-demo/.workbench/runs/*/ledger.jsonl
```

Run the smoke tests:

```bash
bash tests/test_smoke.sh
```

YAML task files require `PyYAML`. JSON task files work with the Python standard library.

## Task seed example

```yaml
name: hello-file-demo
goal: Create a small artifact and verify that it contains the expected text.
params:
  output: hello_seed.txt
  text: write it down, verify it
command_argv:
  - python3
  - -c
  - "from pathlib import Path; import sys; out,text=sys.argv[1],sys.argv[2]; Path('demo_out').mkdir(exist_ok=True); Path('demo_out', out).write_text(text + chr(10), encoding='utf-8')"
  - "{{ params.output }}"
  - "{{ params.text }}"
verifiers:
  - type: python
    call: workbench.verifiers.files:file_contains
    params:
      path: demo_out/{{ params.output }}
      contains: "{{ params.text }}"
```

Prefer `command_argv` over shell command strings. Legacy `command` strings are rejected unless a task explicitly sets `allow_shell: true`.



## Project origin

Task Workbench grew out of a small set of collision experiments: taking workflow patterns from the [Wan-Wu-Sheng / 万物生 skill](https://github.com/9s5bz2jvd2-lang/wusheng), comparing them with lessons from the Bun porting experiment, and then distilling the resulting artifacts into a minimal reusable harness.

The public version was shaped through LingTai-style long-running tool collaboration and Work Buddy feedback, but the repository itself is intentionally presented as an ordinary, domain-neutral utility. It does not include the original domain materials or private experiment records; only the general runner, verifier patterns, examples, and tests are kept here.

## Design choices and relative differences

This prototype does not claim a new category of tool. The useful choices are small and practical:

- **Task seeds over chat history**: a task is saved as a JSON/YAML file with parameters, command, verifiers, evidence notes, and gotchas, so it can be rerun without reconstructing context from a conversation.
- **Verifier-first completion**: a run passes only when verifiers pass. The runner records failures as first-class artifacts instead of treating them as informal notes.
- **Run ledger plus return note**: every run leaves both machine-readable events (`ledger.jsonl`) and a short human-readable report (`return_note.md`).
- **Negative controls are part of the examples**: the repository includes seeds that should fail, so verifier behavior can be checked against known red cases.
- **Shell execution is opt-in**: parameterized tasks should use `command_argv`; legacy shell strings fail closed unless `allow_shell: true` is set.
- **Generic JSON artifact gate**: before writing a domain-specific semantic verifier, `json_collection_health` can catch common structural problems such as parse errors, count mismatches, duplicate stems, duplicate IDs, and missing dotted fields.

These are design tradeoffs, not claims of novelty. Mature CI, evaluation, and benchmark tools cover larger parts of the space. Task Workbench is meant to be a compact local harness for cases where a small reproducible seed and objective verifier are enough.

## Included verifiers

### `workbench.verifiers.files:file_contains`

Checks that a workspace-relative file exists and contains a string.

### `workbench.verifiers.json_integrity:json_collection_health`

A domain-neutral JSON artifact gate. It checks:

- directory existence and workspace containment,
- parseable JSON files,
- minimum or exact file counts,
- duplicate filename stems,
- duplicate IDs for an optional dotted `id_field`, and
- required dotted fields.

Example:

```bash
python3 -m workbench.run examples/generic_json_integrity.task.json --workspace /tmp/task-workbench-json
```

Negative-control examples are included so failures can be tested deliberately:

```bash
python3 -m workbench.run examples/hello_file_should_fail.task.json --workspace /tmp/task-workbench-red
python3 -m workbench.run examples/generic_json_duplicate_should_fail.task.json --workspace /tmp/task-workbench-dup
```

Both should exit with code `2` and write a failed return note.

## Output files

A run directory contains:

- `ledger.jsonl` — structured events for the run,
- `return_note.md` — human-readable summary,
- `stdout.txt` — command stdout,
- `stderr.txt` — command stderr.

The return note includes command status, verifier results, declared evidence, gotchas, and reusable follow-up notes from the task seed.

## Safety notes

- Review task seeds before running them.
- Use `command_argv` whenever possible; it avoids shell interpolation.
- `command` with shell execution is blocked unless `allow_shell: true` is set.
- Verifier file paths are resolved under the provided workspace and cannot escape it through `..`.
- This is a convenience harness, not a security boundary.

## Prior art and positioning

This project is intentionally small. It overlaps with ideas from CI checks, evaluator harnesses, prompt/eval tools, benchmark runners, and task-specific verifiers. Its narrow purpose is to make a local task reproducible with an objective pass/fail gate and inspectable run artifacts.

Use a mature tool when you need hosted dashboards, multi-model evaluation, large benchmark management, browser automation, distributed execution, or production CI integration.

## Repository status

Prototype. APIs and task file fields may change.
