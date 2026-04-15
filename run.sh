#!/usr/bin/env bash
# run.sh — local dev environment launcher for moeen-ai
# Brings up Postgres + Redis, installs deps, inits DB, and starts all processes.
# Usage: bash run.sh
set -euo pipefail

# ─── Phase 0: Settings & Env Defaults ────────────────────────────────────────
# All variables are overridable from the outside:  BACKEND_PORT=9000 bash run.sh
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
DB_PORT_HOST="${DB_PORT_HOST:-5432}"
REDIS_PORT_HOST="${REDIS_PORT_HOST:-6379}"

# Logging — DEBUG by default when launched via run.sh.
# Set LOG_LEVEL=info to quieten, or LOG_LEVEL=warning for production-like output.
export LOG_LEVEL="${LOG_LEVEL:-debug}"
# OpenAI SDK reads OPENAI_LOG to enable its own HTTP tracing (request/response bodies).
export OPENAI_LOG="${OPENAI_LOG:-debug}"

PG_IMAGE="${PG_IMAGE:-postgres:16}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7}"
PG_CONTAINER="${PG_CONTAINER:-moeen-postgres}"
REDIS_CONTAINER="${REDIS_CONTAINER:-moeen-redis}"
PG_DB="${PG_DB:-moeen_dev}"
PG_USER="${PG_USER:-user}"
PG_PASSWORD="${PG_PASSWORD:-pass}"

export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://localhost:${BACKEND_PORT}}"

# Resolve script dir so the script works when called from any directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Phase 1: Load .env + Python venv ────────────────────────────────────────
if [[ -f .env ]]; then
  # Parse .env manually to handle spaces around '=' and inline comments.
  # 'source .env' breaks when lines look like:  KEY = "value"  (space around =)
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Strip leading whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue
    # Strip inline comment (everything after unquoted #)
    local_key="${line%%=*}"
    local_val="${line#*=}"
    # Normalize: trim spaces around key and value
    local_key="${local_key// /}"
    local_val="${local_val# }"
    local_val="${local_val%"${local_val##*[![:space:]]}"}"
    # Strip surrounding quotes from value
    if [[ "$local_val" == \"*\" || "$local_val" == \'*\' ]]; then
      local_val="${local_val:1:${#local_val}-2}"
    fi
    export "${local_key}=${local_val}"
  done < .env
  echo "✅ Loaded .env"
fi

# app.py expects ADMIN_PASSWORD_HASH; .env stores the same bcrypt value as ADMIN_PASSWORD
if [[ -z "${ADMIN_PASSWORD_HASH:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
  export ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD"
fi

# Use .venv if present; fall back to venv (legacy); create .venv if neither exists
if [[ -d .venv ]]; then
  VENV_DIR=".venv"
elif [[ -d venv ]]; then
  VENV_DIR="venv"
else
  echo "📦 Creating Python virtual environment at .venv ..."
  python3 -m venv .venv
  VENV_DIR=".venv"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# ─── Phase 2: Install Python + Frontend deps (parallel, skip if unchanged) ───

# pip — only reinstall when requirements.txt content changes
_pip_install() {
  local hash stamp="${VENV_DIR}/.pip.stamp"
  hash="$(md5 -q requirements.txt 2>/dev/null \
    || md5sum requirements.txt 2>/dev/null | awk '{print $1}')"
  if [[ -f "$stamp" && "$(cat "$stamp")" == "$hash" ]]; then
    echo "✅ Python deps up-to-date"
    return
  fi
  echo "📦 Installing Python deps..."
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  echo "$hash" > "$stamp"
  echo "✅ Python deps ready"
}

# npm — only reinstall when package-lock.json content changes
_npm_install() {
  cd frontend
  local hash stamp="node_modules/.run-sh.stamp"
  hash="$(md5 -q package-lock.json 2>/dev/null \
    || md5sum package-lock.json 2>/dev/null | awk '{print $1}')"
  if [[ -f "$stamp" && "$(cat "$stamp")" == "$hash" ]]; then
    echo "✅ Frontend deps up-to-date"
    return
  fi
  echo "📦 Installing frontend deps..."
  if [[ -f package-lock.json ]]; then
    npm ci --silent
  else
    npm install --silent
  fi
  echo "$hash" > "$stamp"
  echo "✅ Frontend deps ready"
}

_pip_install &  _PIP_PID=$!
_npm_install &  _NPM_PID=$!
wait "$_PIP_PID" "$_NPM_PID"

# ─── Phase 3: Docker Engine check ────────────────────────────────────────────
if ! docker info &>/dev/null; then
  echo "🐳 Docker not running — attempting to start Docker Desktop..."
  open -a "Docker Desktop" 2>/dev/null \
    || open -a Docker     2>/dev/null \
    || { echo "❌ Docker Desktop not found. Please start Docker manually."; exit 1; }
  echo -n "⏳ Waiting for Docker (up to 90s)"
  for i in $(seq 1 90); do
    sleep 1
    if docker info &>/dev/null; then
      echo " — ready."
      break
    fi
    echo -n "."
    if [[ $i -eq 90 ]]; then
      echo ""
      echo "❌ Docker did not become ready within 90 seconds."
      exit 1
    fi
  done
fi
echo "✅ Docker engine ready"

# ─── Phase 4: Start Postgres + Redis ─────────────────────────────────────────

# ── Helper: pull image only when absent; set PULL_IMAGES=1 to force ──────────
ensure_image_current() {
  local image="$1" label="$2"
  # Skip the network round-trip when the image already exists locally
  if [[ "${PULL_IMAGES:-0}" == "0" ]] && docker image inspect "$image" &>/dev/null; then
    echo "✅ ${label} image present (PULL_IMAGES=1 to update)"
    return 0
  fi
  local old_id
  old_id="$(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null || true)"
  echo "🔄 Pulling ${label} image (${image})..."
  docker pull "$image" --quiet
  local new_id
  new_id="$(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null || true)"
  if [[ -z "$old_id" ]]; then
    echo "   ✅ ${label} image installed"
  elif [[ "$old_id" != "$new_id" ]]; then
    echo "   🆕 ${label} image updated  (old: ${old_id:7:12}  new: ${new_id:7:12})"
  else
    echo "   ✅ ${label} image up-to-date"
  fi
}

# ── Helper: remove an old image tag when no container references it ───────────
remove_unused_image_ref() {
  local image="$1"
  if docker image inspect "$image" &>/dev/null; then
    local containers
    containers="$(docker ps -aq --filter "ancestor=${image}" 2>/dev/null || true)"
    if [[ -z "$containers" ]]; then
      echo "   🗑️  Removing unused legacy image: ${image}"
      docker rmi "$image" 2>/dev/null || true
    fi
  fi
}

# ── Helper: recreate container if its running image drifted from the pull ─────
remove_stale_container_if_image_drifted() {
  local container="$1" current_image_id="$2"
  local running_image_id
  running_image_id="$(docker inspect --format '{{.Image}}' "$container" 2>/dev/null || true)"
  if [[ -n "$running_image_id" && "$running_image_id" != "$current_image_id" ]]; then
    echo "   ♻️  ${container} is running a stale image — removing for recreation..."
    docker rm -f "$container" 2>/dev/null || true
  fi
}

ensure_image_current "$PG_IMAGE"    "Postgres" &  _PGPULL=$!
ensure_image_current "$REDIS_IMAGE" "Redis"    &  _RDPULL=$!
wait "$_PGPULL" "$_RDPULL"

PG_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$PG_IMAGE")"
REDIS_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$REDIS_IMAGE")"

remove_stale_container_if_image_drifted "$PG_CONTAINER"    "$PG_IMAGE_ID"
remove_stale_container_if_image_drifted "$REDIS_CONTAINER" "$REDIS_IMAGE_ID"

# ── Start Postgres ────────────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
  echo "✅ Postgres container already running"
elif docker ps -a --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
  echo "▶️  Starting existing Postgres container..."
  docker start "$PG_CONTAINER"
else
  echo "🐘 Creating Postgres container (${PG_IMAGE})..."
  docker run -d \
    --name "$PG_CONTAINER" \
    -e POSTGRES_DB="$PG_DB" \
    -e POSTGRES_USER="$PG_USER" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" \
    -p "${DB_PORT_HOST}:5432" \
    "$PG_IMAGE"
fi

# ── Start Redis ───────────────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
  echo "✅ Redis container already running"
elif docker ps -a --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
  echo "▶️  Starting existing Redis container..."
  docker start "$REDIS_CONTAINER"
else
  echo "🟥 Creating Redis container (${REDIS_IMAGE})..."
  docker run -d \
    --name "$REDIS_CONTAINER" \
    -p "${REDIS_PORT_HOST}:6379" \
    "$REDIS_IMAGE"
fi

# ── TCP-level readiness poll ──────────────────────────────────────────────────
wait_for_port() {
  local host="$1" port="$2" label="$3" timeout="${4:-30}"
  echo -n "⏳ Waiting for ${label} on ${host}:${port}"
  for i in $(seq 1 "$timeout"); do
    if (echo > "/dev/tcp/${host}/${port}") 2>/dev/null; then
      echo " — ready."
      return 0
    fi
    sleep 1
    echo -n "."
  done
  echo ""
  echo "❌ ${label} did not become available within ${timeout}s."
  return 1
}

# ── HTTP-level readiness poll ─────────────────────────────────────────────────
wait_for_http() {
  local url="$1" label="$2" timeout="${3:-30}"
  echo -n "⏳ Waiting for ${label} at ${url}"
  for i in $(seq 1 "$timeout"); do
    if curl --silent --fail "$url" &>/dev/null; then
      echo " — ready."
      return 0
    fi
    sleep 1
    echo -n "."
  done
  echo ""
  echo "❌ ${label} did not respond within ${timeout}s."
  return 1
}

wait_for_port "127.0.0.1" "$DB_PORT_HOST"    "Postgres" 30
wait_for_port "127.0.0.1" "$REDIS_PORT_HOST" "Redis"    20

# ─── Phase 5: Runtime Env + DB Connectivity ──────────────────────────────────
# Rebuild DATABASE_URL from detected host port so it always points to the
# local container, even if .env had a different value.
DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD}@localhost:${DB_PORT_HOST}/${PG_DB}"
export DATABASE_URL

# Detect LAN IP and append to CORS_ORIGINS so other devices on the network
# can reach the API during development.
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null \
  || ip route get 1 2>/dev/null | awk '{print $NF; exit}' \
  || true)"
if [[ -n "$LAN_IP" ]]; then
  export CORS_ORIGINS="${CORS_ORIGINS:+${CORS_ORIGINS},}http://${LAN_IP}:${FRONTEND_PORT}"
  echo "📡 LAN API reachable at http://${LAN_IP}:${BACKEND_PORT}"
fi

echo "🔗 DATABASE_URL → ${DATABASE_URL}"

# Verify psycopg2 can actually connect before proceeding
python3 - <<'PY'
import sys, os
try:
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=5)
    conn.close()
    print("✅ Database connection verified")
except Exception as e:
    # Try a fallback: direct container socket on default port
    fallback = os.environ["DATABASE_URL"].replace(
        f"@localhost:{os.environ.get('DB_PORT_HOST', '5432')}",
        "@localhost:5432"
    )
    try:
        conn = psycopg2.connect(fallback, connect_timeout=5)
        conn.close()
        os.environ["DATABASE_URL"] = fallback
        print(f"✅ Connected via fallback URL: {fallback}")
    except Exception as e2:
        print(f"❌ Database connection failed: {e2}", file=sys.stderr)
        sys.exit(1)
PY

# ─── Phase 5b: DB Init ────────────────────────────────────────────────────────
echo "🗄️  Initialising database schema (idempotent CREATE TABLE IF NOT EXISTS)..."
python3 - <<'PY'
import sys, traceback
try:
    from db import init_db
    init_db()
    print("✅ Database schema ready")
except Exception as e:
    traceback.print_exc()
    # Non-fatal: schema may already exist; surface as a warning, not a crash
    print(f"⚠️  DB init warning (continuing): {e}", file=sys.stderr)
PY

# ─── Phase 6: Start All Processes ────────────────────────────────────────────
PIDS=()

# Trap Ctrl-C / EXIT so all child processes are cleaned up
cleanup() {
  echo ""
  echo "🛑 Stopping all dev processes..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "👋 moeen-ai dev environment stopped."
}
trap cleanup INT TERM EXIT

# ── 6a: Gunicorn ──────────────────────────────────────────────────────────────
echo "🚀 Starting Gunicorn on port ${BACKEND_PORT}..."
# Kill any stale process already occupying the backend port
lsof -ti tcp:"$BACKEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 0.3

gunicorn \
  -b "0.0.0.0:${BACKEND_PORT}" \
  app:app \
  --workers 2 \
  --threads 2 \
  --log-level "${LOG_LEVEL}" \
  --access-logfile - \
  &
PIDS+=($!)

wait_for_http "http://localhost:${BACKEND_PORT}/health" "Gunicorn" 30

# ── 6b: Celery worker ─────────────────────────────────────────────────────────
echo "🌿 Starting Celery worker..."
pkill -f "celery.*tasks.*worker" 2>/dev/null || true
sleep 0.5

celery -A tasks worker \
  --concurrency=2 \
  --max-tasks-per-child=100 \
  --loglevel="${LOG_LEVEL}" \
  &
PIDS+=($!)

# ── 6c: Celery beat ───────────────────────────────────────────────────────────
echo "⏰ Starting Celery beat..."
pkill -f "celery.*tasks.*beat" 2>/dev/null || true
# Remove a stale pidfile that would prevent beat from starting
rm -f celerybeat.pid 2>/dev/null || true
sleep 0.5

celery -A tasks beat \
  --loglevel="${LOG_LEVEL}" \
  &
PIDS+=($!)

# ── 6d: Cloudflare Tunnel ─────────────────────────────────────────────────────
if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  echo "🌐 Starting Cloudflare tunnel..."
  cloudflared tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN" &
  PIDS+=($!)
else
  echo "⚠️  CLOUDFLARE_TUNNEL_TOKEN not set — skipping tunnel"
fi

# ── 6e: Next.js dev server ────────────────────────────────────────────────────
echo "⚡ Starting Next.js frontend..."
(
  cd frontend
  # Auto-bump port if the preferred one is already occupied
  PORT="$FRONTEND_PORT"
  while lsof -ti tcp:"$PORT" &>/dev/null 2>&1; do
    echo "   ⚠️  Port ${PORT} busy — trying $((PORT + 1))"
    PORT=$((PORT + 1))
  done
  export PORT
  export NEXT_PUBLIC_API_BASE_URL="http://localhost:${BACKEND_PORT}"
  npm run dev -- --port "$PORT"
) &
PIDS+=($!)

echo ""
echo "┌──────────────────────────────────────────────────────┐"
echo "│  moeen-ai dev environment is running                 │"
printf "│  Backend:   http://localhost:%-25s│\n" "${BACKEND_PORT}"
printf "│  Frontend:  http://localhost:%-25s│\n" "${FRONTEND_PORT}  (Next.js)"
echo "│                                                      │"
echo "│  Press Ctrl+C to stop everything                    │"
echo "└──────────────────────────────────────────────────────┘"
echo ""

# Keep the launcher alive until all background jobs exit
wait "${PIDS[@]}"
