#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

assert_file_contains() {
  local file="$1"
  local needle="$2"
  python3 - "$file" "$needle" <<'PY'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
needle = sys.argv[2]
text = path.read_text(encoding="utf-8")
if needle not in text:
    raise SystemExit(f"missing expected text {needle!r} in {path}")
PY
}

assert_run_passed() {
  local run_dir="$1"
  test -d "$run_dir"
  test -f "$run_dir/ledger.jsonl"
  test -f "$run_dir/return_note.md"
  test -f "$run_dir/stdout.txt"
  test -f "$run_dir/stderr.txt"
  assert_file_contains "$run_dir/ledger.jsonl" '"event": "run_finished"'
  assert_file_contains "$run_dir/ledger.jsonl" '"status": "passed"'
  assert_file_contains "$run_dir/return_note.md" 'status: **passed**'
}

assert_run_failed() {
  local run_dir="$1"
  test -d "$run_dir"
  test -f "$run_dir/ledger.jsonl"
  test -f "$run_dir/return_note.md"
  assert_file_contains "$run_dir/ledger.jsonl" '"event": "run_finished"'
  assert_file_contains "$run_dir/ledger.jsonl" '"status": "failed"'
  assert_file_contains "$run_dir/return_note.md" 'status: **failed**'
}

rm -rf /tmp/ltwb-smoke /tmp/ltwb-smoke-json /tmp/ltwb-smoke-override /tmp/ltwb-smoke-injection /tmp/ltwb-smoke-red /tmp/ltwb-smoke-empty /tmp/ltwb-smoke-shell-reject /tmp/ltwb-smoke-json-integrity /tmp/ltwb-smoke-json-duplicate /tmp/ltwb-runs
mkdir -p /tmp/ltwb-smoke /tmp/ltwb-smoke-json /tmp/ltwb-smoke-override /tmp/ltwb-smoke-injection /tmp/ltwb-smoke-red /tmp/ltwb-smoke-empty /tmp/ltwb-smoke-shell-reject /tmp/ltwb-smoke-json-integrity /tmp/ltwb-smoke-json-duplicate /tmp/ltwb-runs

python3 -m workbench.run examples/hello_file.task.yaml --workspace /tmp/ltwb-smoke --runs-dir /tmp/ltwb-runs/yaml >/tmp/ltwb-smoke-run.txt
run_dir=$(tail -n 1 /tmp/ltwb-smoke-run.txt)
assert_run_passed "$run_dir"
assert_file_contains /tmp/ltwb-smoke/demo_out/hello_seed.txt 'write it down, verify it'
assert_file_contains "$run_dir/return_note.md" 'shell: `False`'

python3 -m workbench.run examples/hello_file.task.json --workspace /tmp/ltwb-smoke-json --runs-dir /tmp/ltwb-runs/json >/tmp/ltwb-smoke-json-run.txt
json_run_dir=$(tail -n 1 /tmp/ltwb-smoke-json-run.txt)
assert_run_passed "$json_run_dir"
assert_file_contains /tmp/ltwb-smoke-json/demo_out/hello_seed_json.txt 'write it down, verify it'

python3 -m workbench.run examples/generic_json_integrity.task.json --workspace /tmp/ltwb-smoke-json-integrity --runs-dir /tmp/ltwb-runs/json-integrity >/tmp/ltwb-smoke-json-integrity-run.txt
json_integrity_run_dir=$(tail -n 1 /tmp/ltwb-smoke-json-integrity-run.txt)
assert_run_passed "$json_integrity_run_dir"
assert_file_contains "$json_integrity_run_dir/return_note.md" 'json_count'

python3 -m workbench.run examples/hello_file.task.json --workspace /tmp/ltwb-smoke-override --runs-dir /tmp/ltwb-runs/override --set text=wrong >/tmp/ltwb-smoke-override-run.txt
override_run_dir=$(tail -n 1 /tmp/ltwb-smoke-override-run.txt)
assert_run_passed "$override_run_dir"
assert_file_contains /tmp/ltwb-smoke-override/demo_out/hello_seed_json.txt 'wrong'

python3 -m workbench.run examples/shell_injection_regression.task.json --workspace /tmp/ltwb-smoke-injection --runs-dir /tmp/ltwb-runs/injection >/tmp/ltwb-smoke-injection-run.txt
injection_run_dir=$(tail -n 1 /tmp/ltwb-smoke-injection-run.txt)
assert_run_passed "$injection_run_dir"
assert_file_contains /tmp/ltwb-smoke-injection/demo_out/injection.txt "'; touch PWNED; echo '"
if [[ -e /tmp/ltwb-smoke-injection/PWNED ]]; then
  echo "shell injection regression created PWNED" >&2
  exit 1
fi

set +e
python3 -m workbench.run examples/hello_file_should_fail.task.json --workspace /tmp/ltwb-smoke-red --runs-dir /tmp/ltwb-runs/red >/tmp/ltwb-smoke-red-run.txt 2>/tmp/ltwb-smoke-red-err.txt
rc=$?
set -e
if [[ "$rc" -ne 2 ]]; then
  echo "expected true-red verifier run to exit 2 but got rc=$rc" >&2
  cat /tmp/ltwb-smoke-red-err.txt >&2
  exit 1
fi
red_run_dir=$(tail -n 1 /tmp/ltwb-smoke-red-run.txt)
assert_run_failed "$red_run_dir"
assert_file_contains "$red_run_dir/return_note.md" 'contains_ok'

set +e
python3 -m workbench.run examples/empty_verifiers.task.json --workspace /tmp/ltwb-smoke-empty --runs-dir /tmp/ltwb-runs/empty >/tmp/ltwb-smoke-empty-run.txt 2>/tmp/ltwb-smoke-empty-err.txt
rc=$?
set -e
if [[ "$rc" -ne 2 ]]; then
  echo "expected empty-verifier run to exit 2 but got rc=$rc" >&2
  cat /tmp/ltwb-smoke-empty-err.txt >&2
  exit 1
fi
empty_run_dir=$(tail -n 1 /tmp/ltwb-smoke-empty-run.txt)
assert_run_failed "$empty_run_dir"
assert_file_contains "$empty_run_dir/return_note.md" 'no verifiers declared'

set +e
python3 -m workbench.run examples/shell_command_rejected.task.json --workspace /tmp/ltwb-smoke-shell-reject --runs-dir /tmp/ltwb-runs/shell-reject >/tmp/ltwb-smoke-shell-reject-run.txt 2>/tmp/ltwb-smoke-shell-reject-err.txt
rc=$?
set -e
if [[ "$rc" -ne 2 ]]; then
  echo "expected shell-command rejection to exit 2 but got rc=$rc" >&2
  cat /tmp/ltwb-smoke-shell-reject-err.txt >&2
  exit 1
fi
shell_reject_run_dir=$(tail -n 1 /tmp/ltwb-smoke-shell-reject-run.txt)
assert_run_failed "$shell_reject_run_dir"
assert_file_contains "$shell_reject_run_dir/return_note.md" 'shell command requires allow_shell'

set +e
python3 -m workbench.run examples/generic_json_duplicate_should_fail.task.json --workspace /tmp/ltwb-smoke-json-duplicate --runs-dir /tmp/ltwb-runs/json-duplicate >/tmp/ltwb-smoke-json-duplicate-run.txt 2>/tmp/ltwb-smoke-json-duplicate-err.txt
rc=$?
set -e
if [[ "$rc" -ne 2 ]]; then
  echo "expected generic duplicate JSON verifier to exit 2 but got rc=$rc" >&2
  cat /tmp/ltwb-smoke-json-duplicate-err.txt >&2
  exit 1
fi
json_duplicate_run_dir=$(tail -n 1 /tmp/ltwb-smoke-json-duplicate-run.txt)
assert_run_failed "$json_duplicate_run_dir"
assert_file_contains "$json_duplicate_run_dir/return_note.md" 'duplicate_json_stems'

echo "smoke ok: yaml=$run_dir json=$json_run_dir json_integrity=$json_integrity_run_dir override=$override_run_dir injection=$injection_run_dir red=$red_run_dir empty=$empty_run_dir shell_reject=$shell_reject_run_dir json_duplicate=$json_duplicate_run_dir"
