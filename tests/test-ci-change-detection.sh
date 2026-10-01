#!/usr/bin/env bash
set -euo pipefail

# Regression tests for the change-detection script embedded in
# .github/workflows/ci.yaml.
#
# The detection step must see every commit of an event, not just the head
# commit: before the fix, a push stacking "touch component A" then "touch
# component B" diffed HEAD~1..HEAD only, and component A silently skipped
# CI. These tests extract the exact `run:` script from the workflow with
# PyYAML and replay it against fixture repositories.

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$TEST_DIR/.." && pwd)"
WORKFLOW="$PROJECT_ROOT/.github/workflows/ci.yaml"

TEST_TMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP"' EXIT

fail() {
    echo "not ok - $*" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || fail "python3 required"
python3 -c 'import yaml' 2>/dev/null || fail "PyYAML required"

# ── Extract the detection run-block from the workflow ───────────────────
python3 - "$WORKFLOW" > "$TEST_TMP/detect.sh" << 'PYEOF'
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = yaml.safe_load(fh)

job = doc["jobs"]["detect-changes"]
step = next(s for s in job["steps"] if s.get("name") == "Check which components changed")
# GitHub injects expressions before the shell runs; emulate the only one
# the script uses with an environment-driven placeholder.
print(step["run"].replace("${{ github.event.before }}", "${PUSH_BEFORE:?set PUSH_BEFORE}"))
PYEOF

fixture_repo() {
    git init -q "$TEST_TMP/repo"
    git -C "$TEST_TMP/repo" config user.email t@example.com
    git -C "$TEST_TMP/repo" config user.name t
}

changed_paths() {
    # stdout after "Changed files:" contains only the paths (the boolean
    # exports go to $GITHUB_OUTPUT); blank lines and VAR= lines are dropped
    # defensively in case the embedded script evolves.
    (
        cd "$TEST_TMP/repo"
        GITHUB_EVENT_NAME="${EVENT:-push}" PUSH_BEFORE="${BEFORE:-}" bash "$TEST_TMP/detect.sh" 2>/dev/null
    ) | sed -n '/^Changed files:$/,$p' | sed '1d' | sed -e '/^$/d' -e '/^[A-Z_][A-Z_]*=/d' | sort
}

# The real workflow exports booleans after the changed-file list; the
# extraction above stops at the first blank line, which the fixture
# assertions rely on (paths only).

# ── 1. multi-commit push spans both commits ─────────────────────────────
# BEFORE marks the branch tip the push starts from: the push then stacks
# a blaze commit and a ktuner commit, and the diff must see both.
fixture_repo
echo base > "$TEST_TMP/repo/base.txt" && git -C "$TEST_TMP/repo" add -A && git -C "$TEST_TMP/repo" commit -qm base
BEFORE=$(git -C "$TEST_TMP/repo" rev-parse HEAD)
mkdir -p "$TEST_TMP/repo/src/blaze" "$TEST_TMP/repo/src/ktuner"
echo a > "$TEST_TMP/repo/src/blaze/a.rs" && git -C "$TEST_TMP/repo" add -A && git -C "$TEST_TMP/repo" commit -qm one
echo b > "$TEST_TMP/repo/src/ktuner/b.rs" && git -C "$TEST_TMP/repo" add -A && git -C "$TEST_TMP/repo" commit -qm two
EVENT=push BEFORE="$BEFORE"
got="$(changed_paths || true)"
case "$got" in
    *src/blaze/a.rs*) ;;
    *) fail "multi-commit push missed the earlier commit (got: $got)" ;;
esac
case "$got" in
    *src/ktuner/b.rs*) ;;
    *) fail "multi-commit push missed the head commit (got: $got)" ;;
esac
echo "ok - multi-commit push detects files from every commit"

# ── 2. pull_request merge-commit shape keeps working ────────────────────
rm -rf "$TEST_TMP/repo"
fixture_repo
mkdir -p "$TEST_TMP/repo/src/blaze"
echo base > "$TEST_TMP/repo/base.txt" && git -C "$TEST_TMP/repo" add -A && git -C "$TEST_TMP/repo" commit -qm base
# Emulate the PR merge commit: base is the first parent.
git -C "$TEST_TMP/repo" checkout -qb pr
echo pr > "$TEST_TMP/repo/src/blaze/pr.txt"
git -C "$TEST_TMP/repo" add -A && git -C "$TEST_TMP/repo" commit -qm pr
git -C "$TEST_TMP/repo" checkout -q master 2>/dev/null || git -C "$TEST_TMP/repo" checkout -q main
BASE_SHA=$(git -C "$TEST_TMP/repo" rev-parse HEAD)
git -C "$TEST_TMP/repo" merge -q --no-ff -m merge pr
EVENT=pull_request BEFORE="$BASE_SHA"
got="$(changed_paths || true)"
case "$got" in
    *src/blaze/pr.txt*) ;;
    *) fail "pull_request diff lost the PR change (got: $got)" ;;
esac
case "$got" in
    *base.txt*) fail "pull_request diff included the base's own file (got: $got)" ;;
esac
echo "ok - pull_request merge diff stays scoped to the PR"

# ── 3. unusable base (force push / first push) degrades to head tree ────
BEFORE="0000000000000000000000000000000000000000"
EVENT=push
got="$(changed_paths || true)"
case "$got" in
    *src/blaze/pr.txt*|*base.txt*) ;;
    *) fail "empty-tree fallback should report head-tree files (got: $got)" ;;
esac
echo "ok - unusable base degrades to the head-tree diff"

echo "# ci change-detection checks passed"
