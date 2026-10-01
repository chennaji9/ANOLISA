#!/usr/bin/env bash
set -euo pipefail

# Regression tests for the os-skills `make install` fail-fast behavior.
#
# The install loop copies one directory per skill. Before the fix, a failed
# copy mid-loop was masked whenever a later iteration succeeded, so packaging
# could report success with missing assets. These tests stub `cp` so one copy
# fails and assert that `make install` now propagates the failure.

TEST_TMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP"' EXIT

MAKEFILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() {
    echo "not ok - $*" >&2
    exit 1
}

# ── Fixture component tree with two skills ──────────────────────────────
FIXTURE="$TEST_TMP/component"
mkdir -p "$FIXTURE/skills/alpha" "$FIXTURE/skills/beta"
printf '# Alpha\n' > "$FIXTURE/skills/alpha/SKILL.md"
printf '# Beta\n' > "$FIXTURE/skills/beta/SKILL.md"
printf 'name = "fixture"\n' > "$FIXTURE/component.toml"

STAGE="$TEST_TMP/stage"
STUB_BIN="$TEST_TMP/stubs"
mkdir -p "$STAGE" "$STUB_BIN"

# cp stub: counts invocations and fails the Nth one (CP_FAIL_ON, 0 = never).
cat > "$STUB_BIN/cp" << 'SHEOF'
#!/usr/bin/env bash
count=$(( $(cat "$CP_COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$count" > "$CP_COUNT_FILE"
if [ "${CP_FAIL_ON:-0}" -eq "$count" ]; then
    echo "stub-cp: simulated failure" >&2
    exit 1
fi
exec /bin/cp "$@"
SHEOF
chmod +x "$STUB_BIN/cp"

run_make_install() {
    (
        cd "$FIXTURE"
        PATH="$STUB_BIN:$PATH" \
        CP_COUNT_FILE="$TEST_TMP/cp.count" \
        make --no-print-directory -f "$MAKEFILE_DIR/Makefile" \
            install DESTDIR="" SKILLS_DIR="$STAGE/skills" \
            COMPONENT_DIR="$STAGE/component" >/dev/null 2>&1
    )
}

# ── 1. an early copy failure must fail the install ──────────────────────
CP_FAIL_ON=1 run_make_install && fail "install succeeded despite a copy failure"

# ── 2. a later copy failure must not be masked either ───────────────────
rm -rf "$STAGE"; mkdir -p "$STAGE"
CP_FAIL_ON=2 run_make_install && fail "install succeeded when the second copy failed"

# ── 3. happy path still installs every skill and the manifest ──────────
rm -rf "$STAGE"; mkdir -p "$STAGE"
CP_FAIL_ON=0 run_make_install || fail "install failed with no simulated failure"
[ -f "$STAGE/skills/alpha/SKILL.md" ] || fail "alpha skill missing after install"
[ -f "$STAGE/skills/beta/SKILL.md" ] || fail "beta skill missing after install"
[ -f "$STAGE/component/component.toml" ] || fail "component manifest missing"

echo "ok - install propagates copy failures and still installs cleanly"
