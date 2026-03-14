#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

run_compose_common_subshell() {
  local cmd="$1"
  (cd "$ROOT_DIR" && bash -lc "$cmd")
}

echo "[contract] parse_compose_args should honor --dev/--build..."
run_compose_common_subshell '
  source scripts/compose-common.sh
  parse_compose_args --dev --build
  test "$MODE" = "dev"
  test "$BUILD_FLAG" = "--build"
'

echo "[contract] ensure_encryption_key_configured should fail when key is missing..."
tmp_env_missing="$(mktemp)"
set +e
run_compose_common_subshell "
  BACKEND_ENV_FILE=\"$tmp_env_missing\"
  source scripts/compose-common.sh
  unset ENCRYPTION_KEY
  ensure_encryption_key_configured
" >/tmp/entrypoint_missing_key.out 2>&1
rc_missing=$?
set -e
rm -f "$tmp_env_missing"
if [[ "$rc_missing" -eq 0 ]]; then
  echo "expected failure for missing ENCRYPTION_KEY"
  exit 1
fi
grep -q "缺少 ENCRYPTION_KEY" /tmp/entrypoint_missing_key.out

echo "[contract] ensure_encryption_key_configured should pass when key is set..."
tmp_env_ok="$(mktemp)"
cat >"$tmp_env_ok" <<'EOF'
ENCRYPTION_KEY=test-key
EOF
run_compose_common_subshell "
  BACKEND_ENV_FILE=\"$tmp_env_ok\"
  source scripts/compose-common.sh
  load_backend_env
  ensure_encryption_key_configured
"
rm -f "$tmp_env_ok"

echo "[contract] ok"
