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

echo "[contract] ensure_encryption_key_configured should persist provided key..."
tmp_env_ok="$(mktemp)"
cat >"$tmp_env_ok" <<'EOF'
ENCRYPTION_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=
EOF
run_compose_common_subshell "
  BACKEND_ENV_FILE=\"$tmp_env_ok\"
  source scripts/compose-common.sh
  load_backend_env
  ensure_encryption_key_configured
"
grep -q "^ENCRYPTION_KEY=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=$" "$tmp_env_ok"
rm -f "$tmp_env_ok"

echo "[contract] ensure_encryption_key_configured should auto-generate key when missing..."
tmp_env_missing="$(mktemp)"
tmp_template="$(mktemp)"
cat >"$tmp_template" <<'EOF'
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/ai_platform?charset=utf8mb4
EOF
run_compose_common_subshell "
  BACKEND_ENV_FILE=\"$tmp_env_missing\"
  BACKEND_ENV_TEMPLATE_FILE=\"$tmp_template\"
  source scripts/compose-common.sh
  unset ENCRYPTION_KEY
  ensure_encryption_key_configured
"
grep -Eq '^ENCRYPTION_KEY=[A-Za-z0-9_-]{43}=$' "$tmp_env_missing"
rm -f "$tmp_env_missing" "$tmp_template"

echo "[contract] ensure_encryption_key_configured should replace placeholder key..."
tmp_env_placeholder="$(mktemp)"
cat >"$tmp_env_placeholder" <<'EOF'
ENCRYPTION_KEY=your-fernet-key-here
EOF
run_compose_common_subshell "
  BACKEND_ENV_FILE=\"$tmp_env_placeholder\"
  source scripts/compose-common.sh
  load_backend_env
  ensure_encryption_key_configured
"
grep -Eq '^ENCRYPTION_KEY=[A-Za-z0-9_-]{43}=$' "$tmp_env_placeholder"
grep -vq '^ENCRYPTION_KEY=your-fernet-key-here$' "$tmp_env_placeholder"
rm -f "$tmp_env_placeholder"

echo "[contract] ok"
