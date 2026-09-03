#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prepare-prototype-work.sh [options]

Locate and validate a React prototype reference app without changing it.

Options:
  --project-root PATH   Project/worktree root. Defaults to the Git top-level or cwd.
  --app-root PATH       React reference app root. Required unless discovery finds exactly one app.
  -h, --help            Show this help.
USAGE
}

fail() {
  printf '[prototype-work] ERROR: %s\n' "$*" >&2
  exit 1
}

absolute_path() {
  local path="$1"
  if [ -d "$path" ]; then
    (cd "$path" && pwd -P)
  else
    fail "Path does not exist: $path"
  fi
}

find_project_root() {
  if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
    git rev-parse --show-toplevel
  else
    pwd -P
  fi
}

check_manifest() {
  local package_file="$1"
  local check="$2"
  local status

  if node -e '
    const fs = require("fs");
    const packageFile = process.argv[1];
    const check = process.argv[2];
    let manifest;
    try {
      manifest = JSON.parse(fs.readFileSync(packageFile, "utf8"));
    } catch {
      process.exit(2);
    }

    if (check === "react") {
      const dependencyGroups = [
        manifest.dependencies,
        manifest.devDependencies,
      ];
      const hasReactDependency = dependencyGroups.some((dependencies) =>
        dependencies &&
        typeof dependencies === "object" &&
        !Array.isArray(dependencies) &&
        (
          typeof dependencies.react === "string" ||
          typeof dependencies["@vitejs/plugin-react"] === "string"
        )
      );
      process.exit(hasReactDependency ? 0 : 1);
    }

    if (check === "dev") {
      const scripts = manifest.scripts;
      const devScript =
        scripts && typeof scripts === "object" && !Array.isArray(scripts)
          ? scripts.dev
          : undefined;
      process.exit(
        typeof devScript === "string" && devScript.trim().length > 0 ? 0 : 1
      );
    }

    process.exit(3);
  ' "$package_file" "$check"; then
    return 0
  else
    status=$?
  fi

  case "$status" in
    1)
      return 1
      ;;
    2)
      fail "Invalid package.json at $package_file"
      ;;
    *)
      fail "Could not inspect package.json at $package_file"
      ;;
  esac
}

is_react_package() {
  local package_file="$1"
  check_manifest "$package_file" react
}

has_dev_script() {
  local package_file="$1"
  check_manifest "$package_file" dev
}

validate_prototype_app() {
  local app_root="$1"
  local package_file="$app_root/package.json"

  [ -f "$package_file" ] ||
    fail "Prototype app package.json not found at $package_file"
  is_react_package "$package_file" ||
    fail "Prototype app at $app_root is not a React app"
  has_dev_script "$package_file" ||
    fail "Prototype app package.json must define scripts.dev"
}

locate_prototype_app() {
  local project_root="$1"
  local designs_dir="$project_root/designs"

  [ -d "$designs_dir" ] ||
    fail "No designs/ directory found under $project_root. Ask the user for the reference app path, then rerun with --app-root."

  local package_file
  local app_root
  local package_files
  local -a candidates=()

  if ! package_files="$(
    find "$designs_dir" \
      -type d \
      -name node_modules \
      -prune \
      -o \
      -type f \
      -name package.json \
      -print |
      sort
  )"; then
    fail "Could not scan $designs_dir for React prototype apps"
  fi

  while IFS= read -r package_file; do
    [ -n "$package_file" ] || continue
    if is_react_package "$package_file"; then
      app_root="${package_file%/package.json}"
      candidates+=("$app_root")
    fi
  done <<<"$package_files"

  case "${#candidates[@]}" in
    0)
      fail "Could not find a React package.json under $designs_dir. Ask the user for the reference app path, then rerun with --app-root."
      ;;
    1)
      printf '%s\n' "${candidates[0]}"
      ;;
    *)
      printf '[prototype-work] React prototype app candidates:\n' >&2
      printf '  %s\n' "${candidates[@]}" >&2
      fail "Multiple React prototype apps found under $designs_dir. Ask the user for the reference app path, then rerun with --app-root."
      ;;
  esac
}

PROJECT_ROOT=""
APP_ROOT=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root|--app-root)
      option="$1"
      [ "$#" -ge 2 ] && [ -n "$2" ] ||
        fail "Option $option requires a path"
      case "$2" in
        -*)
          fail "Option $option requires a path"
          ;;
      esac
      if [ "$option" = "--project-root" ]; then
        PROJECT_ROOT="$2"
      else
        APP_ROOT="$2"
      fi
      shift 2
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

command -v node >/dev/null 2>&1 ||
  fail "An active Node runtime is required to inspect prototype package.json files"

if [ -z "$APP_ROOT" ]; then
  APP_ROOT="$(locate_prototype_app "$PROJECT_ROOT")"
fi
APP_ROOT="$(absolute_path "$APP_ROOT")"
validate_prototype_app "$APP_ROOT"

printf 'app-root: %s\n' "$APP_ROOT"
printf 'package-json: %s/package.json\n' "$APP_ROOT"
printf 'dev-script: present\n'
