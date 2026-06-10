#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prepare-prototype-work.sh [options]

Prepare a React prototype reference app before prototype-work starts.

Options:
  --project-root PATH   Project/worktree root. Defaults to git top-level or cwd.
  --app-root PATH       React reference app root. Required when auto-detection under designs/ fails.
  --port PORT           Preview port. Defaults to 5173.
  --force-install       Install dependencies even outside a worktree.
  --skip-install        Skip dependency installation.
  --skip-node-check     Do not activate or validate the project Node version.
  -h, --help            Show this help.
USAGE
}

log() {
  printf '[prototype-work] %s\n' "$*"
}

fail() {
  printf '[prototype-work] ERROR: %s\n' "$*" >&2
  exit 1
}

trim() {
  printf '%s' "$1" | sed 's/#.*//; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

absolute_path() {
  local path="$1"
  if [ -d "$path" ]; then
    (cd "$path" && pwd -P)
  else
    fail "Path does not exist: $path"
  fi
}

read_package_manager_field() {
  local file="$1"
  [ -f "$file" ] || return 0

  if command -v node >/dev/null 2>&1; then
    node -e '
      const fs = require("fs");
      const file = process.argv[1];
      try {
        const value = JSON.parse(fs.readFileSync(file, "utf8")).packageManager;
        if (typeof value === "string") process.stdout.write(value);
      } catch {}
    ' "$file"
    return 0
  fi

  sed -n 's/.*"packageManager"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$file" | head -n 1
}

read_dev_script() {
  local file="$1"
  [ -f "$file" ] || return 0

  if command -v node >/dev/null 2>&1; then
    node -e '
      const fs = require("fs");
      const file = process.argv[1];
      try {
        const value = JSON.parse(fs.readFileSync(file, "utf8")).scripts?.dev;
        if (typeof value === "string") process.stdout.write(value);
      } catch {}
    ' "$file"
  fi
}

pm_name_from_spec() {
  local spec="$1"
  printf '%s' "${spec%@*}"
}

pm_version_from_spec() {
  local spec="$1"
  if [ "$spec" != "${spec%@*}" ]; then
    printf '%s' "${spec##*@}"
  fi
}

find_project_root() {
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    git rev-parse --show-toplevel
  else
    pwd -P
  fi
}

locate_prototype_app() {
  local project_root="$1"
  local designs_dir="$project_root/designs"

  [ -d "$designs_dir" ] || fail "No designs/ directory found under $project_root. Ask the user for the reference app path, then rerun with --app-root."

  local package_file
  while IFS= read -r package_file; do
    if grep -Eq '"react"[[:space:]]*:' "$package_file" || grep -Eq '"@vitejs/plugin-react"[[:space:]]*:' "$package_file"; then
      dirname "$package_file"
      return 0
    fi
  done < <(find "$designs_dir" -mindepth 2 -maxdepth 4 -name package.json -not -path '*/node_modules/*' | sort)

  fail "Could not find a React package.json under $designs_dir. Ask the user for the reference app path, then rerun with --app-root."
}

read_node_version() {
  local project_root="$1"
  local value

  if [ -f "$project_root/.node-version" ]; then
    value="$(trim "$(head -n 1 "$project_root/.node-version")")"
    [ -n "$value" ] && printf '%s' "$value" && return 0
  fi

  if [ -f "$project_root/.nvmrc" ]; then
    value="$(trim "$(head -n 1 "$project_root/.nvmrc")")"
    [ -n "$value" ] && printf '%s' "$value" && return 0
  fi

  if [ -f "$project_root/.tool-versions" ]; then
    value="$(awk '$1 == "nodejs" { print $2; exit }' "$project_root/.tool-versions")"
    value="$(trim "$value")"
    [ -n "$value" ] && printf '%s' "$value" && return 0
  fi
}

activate_node_version() {
  local node_version="$1"
  [ -n "$node_version" ] || return 0

  local expected="${node_version#v}"

  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1090
    . "$HOME/.nvm/nvm.sh"
    log "Using Node $node_version via nvm"
    nvm install "$node_version" >/dev/null
    nvm use "$node_version" >/dev/null
    return 0
  fi

  if command -v node >/dev/null 2>&1; then
    local active
    active="$(node -v | sed 's/^v//')"
    [ "$active" = "$expected" ] || fail "Expected Node $expected, but active node is $active and nvm is unavailable"
    return 0
  fi

  fail "Node $expected is required, but no node executable or nvm installation was found"
}

detect_package_manager() {
  local project_root="$1"
  local app_root="$2"
  local app_spec root_spec

  app_spec="$(read_package_manager_field "$app_root/package.json")"
  if [ -n "$app_spec" ]; then
    printf '%s|%s' "$(pm_name_from_spec "$app_spec")" "$(pm_version_from_spec "$app_spec")"
    return 0
  fi

  if [ -f "$app_root/pnpm-lock.yaml" ]; then
    printf 'pnpm|'
    return 0
  fi

  if [ -f "$app_root/package-lock.json" ] || [ -f "$app_root/npm-shrinkwrap.json" ]; then
    printf 'npm|'
    return 0
  fi

  if [ -f "$app_root/yarn.lock" ]; then
    printf 'yarn|'
    return 0
  fi

  root_spec="$(read_package_manager_field "$project_root/package.json")"
  if [ -n "$root_spec" ]; then
    printf '%s|%s' "$(pm_name_from_spec "$root_spec")" "$(pm_version_from_spec "$root_spec")"
    return 0
  fi

  if [ -f "$project_root/pnpm-lock.yaml" ]; then
    printf 'pnpm|'
    return 0
  fi

  if [ -f "$project_root/package-lock.json" ] || [ -f "$project_root/npm-shrinkwrap.json" ]; then
    printf 'npm|'
    return 0
  fi

  printf 'npm|'
}

ensure_package_manager() {
  local pm="$1"
  local pm_version="$2"

  case "$pm" in
    pnpm)
      if command -v corepack >/dev/null 2>&1; then
        corepack enable >/dev/null 2>&1 || true
        if [ -n "$pm_version" ]; then
          corepack prepare "pnpm@$pm_version" --activate >/dev/null 2>&1 || true
        fi
      fi
      command -v pnpm >/dev/null 2>&1 || fail "pnpm is required but was not found. Install it or enable corepack."
      ;;
    npm)
      command -v npm >/dev/null 2>&1 || fail "npm is required but was not found."
      ;;
    yarn)
      if command -v corepack >/dev/null 2>&1; then
        corepack enable >/dev/null 2>&1 || true
      fi
      command -v yarn >/dev/null 2>&1 || fail "yarn is required but was not found."
      ;;
    *)
      fail "Unsupported package manager '$pm'. Supported managers: pnpm, npm, yarn."
      ;;
  esac
}

is_linked_worktree() {
  local project_root="$1"
  if [ -f "$project_root/.git" ]; then
    return 0
  fi
  return 1
}

install_dependencies() {
  local app_root="$1"
  local pm="$2"

  log "Installing dependencies in $app_root with $pm"
  (
    cd "$app_root"
    case "$pm" in
      pnpm)
        pnpm install
        ;;
      npm)
        if [ -f package-lock.json ] || [ -f npm-shrinkwrap.json ]; then
          npm ci
        else
          npm install
        fi
        ;;
      yarn)
        if [ -f yarn.lock ]; then
          yarn install --frozen-lockfile
        else
          yarn install
        fi
        ;;
    esac
  )
}

build_dev_command() {
  local project_root="$1"
  local app_root="$2"
  local pm="$3"
  local pm_version="$4"
  local node_version="$5"
  local port="$6"
  local dev_script="$7"
  local command_parts=()
  local run_dev_command="$pm run dev"

  if [ -n "$node_version" ] && [ -s "$HOME/.nvm/nvm.sh" ]; then
    command_parts+=("source \"\$HOME/.nvm/nvm.sh\" && nvm use $node_version >/dev/null")
  fi

  command_parts+=("export PATH=\"$app_root/node_modules/.bin:$project_root/node_modules/.bin:\$PATH\"")

  if [ "$pm" = "pnpm" ]; then
    command_parts+=("corepack enable >/dev/null 2>&1 || true")
    if [ -n "$pm_version" ]; then
      command_parts+=("corepack prepare pnpm@$pm_version --activate >/dev/null 2>&1 || true")
    fi
  fi

  if printf '%s' "$dev_script" | grep -Eq '(^|[[:space:]])vite([[:space:]]|$)' && ! printf '%s' "$dev_script" | grep -Eq -- '--port|-p[[:space:]]'; then
    run_dev_command="$run_dev_command -- --host 127.0.0.1 --port $port"
  fi

  command_parts+=("$run_dev_command")

  local launch_command=""
  local part
  for part in "${command_parts[@]}"; do
    if [ -z "$launch_command" ]; then
      launch_command="$part"
    else
      launch_command="$launch_command && $part"
    fi
  done

  printf '%s' "$launch_command"
}

PROJECT_ROOT=""
APP_ROOT=""
PORT="${PROTOTYPE_WORK_PORT:-5173}"
FORCE_INSTALL=0
SKIP_INSTALL="${PROTOTYPE_WORK_SKIP_INSTALL:-0}"
SKIP_NODE_CHECK="${PROTOTYPE_WORK_SKIP_NODE_CHECK:-0}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="${2:-}"
      shift 2
      ;;
    --app-root)
      APP_ROOT="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --force-install)
      FORCE_INSTALL=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --skip-node-check)
      SKIP_NODE_CHECK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

if [ -z "$PROJECT_ROOT" ]; then
  PROJECT_ROOT="$(find_project_root)"
fi

PROJECT_ROOT="$(absolute_path "$PROJECT_ROOT")"

if [ -z "$APP_ROOT" ]; then
  APP_ROOT="$(locate_prototype_app "$PROJECT_ROOT")"
fi

APP_ROOT="$(absolute_path "$APP_ROOT")"

[ -f "$APP_ROOT/package.json" ] || fail "Prototype app package.json not found at $APP_ROOT/package.json"

DEV_SCRIPT="$(read_dev_script "$APP_ROOT/package.json")"
[ -n "$DEV_SCRIPT" ] || fail "Prototype app package.json must define scripts.dev"

NODE_VERSION="$(read_node_version "$PROJECT_ROOT")"
if [ "$SKIP_NODE_CHECK" != "1" ]; then
  activate_node_version "$NODE_VERSION"
elif [ -n "$NODE_VERSION" ]; then
  log "Skipping Node check; project declares Node $NODE_VERSION"
fi

PM_PAIR="$(detect_package_manager "$PROJECT_ROOT" "$APP_ROOT")"
PM="${PM_PAIR%%|*}"
PM_VERSION="${PM_PAIR#*|}"
[ "$PM_VERSION" != "$PM_PAIR" ] || PM_VERSION=""

ensure_package_manager "$PM" "$PM_VERSION"

NEED_INSTALL=0
if [ "$FORCE_INSTALL" = "1" ]; then
  NEED_INSTALL=1
elif is_linked_worktree "$PROJECT_ROOT"; then
  NEED_INSTALL=1
elif [ ! -d "$APP_ROOT/node_modules" ]; then
  NEED_INSTALL=1
fi

if [ "$SKIP_INSTALL" = "1" ]; then
  log "Skipping dependency install by request"
elif [ "$NEED_INSTALL" = "1" ]; then
  install_dependencies "$APP_ROOT" "$PM"
else
  log "Dependencies already present; skipping install"
fi

DEV_COMMAND="$(build_dev_command "$PROJECT_ROOT" "$APP_ROOT" "$PM" "$PM_VERSION" "$NODE_VERSION" "$PORT" "$DEV_SCRIPT")"

log "Ready: app=$APP_ROOT package_manager=$PM node=${NODE_VERSION:-active} port=$PORT"
log "Dev command:"
printf '%s\n' "$DEV_COMMAND"
