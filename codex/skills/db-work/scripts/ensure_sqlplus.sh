#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ensure_sqlplus.sh [--wallet-tools] [--no-install]

Ensures the Oracle CLI tools needed by db-work are available.

Behavior:
  - If sqlplus is already installed or discoverable, do nothing.
  - On macOS, install Oracle Instant Client Basic + SQL*Plus from Oracle's
    official DMG packages when sqlplus is missing.
  - With --wallet-tools, also ensure mkstore is available for SEPS wallet
    creation. mkstore is deprecated by Oracle, but db-work uses it because it is
    a leaner macOS ARM setup path than installing a full Oracle Database Client.

Environment:
  DB_WORK_AUTO_INSTALL_SQLPLUS=0       Disable automatic SQLPlus installation.
  DB_WORK_SQLPLUS_INSTALL_MODE=oracle-dmg|homebrew
                                      Default: oracle-dmg.
  DB_WORK_SQLPLUS_BIN=/path/sqlplus    Explicit SQLPlus binary to use.
  DB_WORK_AUTO_INSTALL_MKSTORE=0       Disable automatic mkstore setup.
  DB_WORK_MKSTORE_BIN=/path/mkstore    Explicit mkstore launcher to use.
  DB_WORK_MKSTORE_VERSION=23.26.1.0.0  Oracle wallet library version.
  DB_WORK_ORACLE_HOME=/path            Oracle Home/client root to search first.
USAGE
}

no_install=0
require_wallet_tools=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wallet-tools)
      require_wallet_tools=1
      shift
      ;;
    --no-install)
      no_install=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

tool_path() {
  local tool="$1"
  local candidate override
  local search_dirs=()

  case "$tool" in
    sqlplus)
      override="${DB_WORK_SQLPLUS_BIN:-}"
      ;;
    mkstore)
      override="${DB_WORK_MKSTORE_BIN:-}"
      ;;
    *)
      override=""
      ;;
  esac

  if [[ -n "$override" ]]; then
    if [[ -x "$override" ]]; then
      printf '%s\n' "$override"
      return 0
    fi
    echo "$tool override is not executable: $override" >&2
    return 1
  fi

  if command -v "$tool" >/dev/null 2>&1; then
    command -v "$tool"
    return 0
  fi

  if [[ -n "${DB_WORK_ORACLE_HOME:-}" ]]; then
    search_dirs+=("$DB_WORK_ORACLE_HOME" "$DB_WORK_ORACLE_HOME/bin")
  fi
  if [[ -n "${ORACLE_HOME:-}" ]]; then
    search_dirs+=("$ORACLE_HOME" "$ORACLE_HOME/bin")
  fi

  search_dirs+=("$HOME/.local/bin" "$HOME/.oracle/mkstore/bin")

  for candidate in \
    "$HOME"/Downloads/instantclient_* \
    /opt/oracle/instantclient_* \
    /usr/local/instantclient_* \
    /usr/local/lib/instantclient_* \
    /opt/homebrew/lib/instantclient_*; do
    [[ -d "$candidate" ]] || continue
    search_dirs+=("$candidate" "$candidate/bin")
  done

  if ((${#search_dirs[@]} > 0)); then
    for candidate in "${search_dirs[@]}"; do
      [[ -n "$candidate" && -x "$candidate/$tool" ]] || continue
      printf '%s\n' "$candidate/$tool"
      return 0
    done
  fi

  return 1
}

print_manual_guidance() {
  cat >&2 <<'GUIDANCE'
sqlplus was not found on PATH.

Manual install options:
  macOS:
    - Install Oracle Instant Client Basic and SQL*Plus from Oracle's official
      macOS DMG packages.
    - The db-work auto-installer follows Oracle's DMG flow: download desired
      packages, mount them, run install_ic.sh once, then use the installed
      instantclient directory.

  Linux/Windows:
    - Use the Oracle Instant Client packages approved by your team or DBA.
    - Install only Basic and SQL*Plus for db-work script execution.

After install, make sure sqlplus is on PATH and re-run:
  sqlplus -v
GUIDANCE
}

print_mkstore_guidance() {
  cat >&2 <<'GUIDANCE'
mkstore was not found.

db-work uses Oracle Secure External Password Store wallet setup with mkstore.
mkstore is deprecated by Oracle, but this skill uses it deliberately because it
is a leaner macOS ARM path than requiring a full Oracle Database Client.

Automatic setup needs:
  - Java on PATH
  - curl on PATH
  - network access to Maven Central

The automatic setup downloads Oracle's database security jar to:
  ~/.oracle/mkstore/lib

and creates a local mkstore launcher at:
  ~/.oracle/mkstore/bin/mkstore

Secrets are still entered only in local terminal prompts during wallet setup.
GUIDANCE
}

mkstore_is_usable() {
  local mkstore_bin="$1"
  "$mkstore_bin" -help 2>&1 | grep -q -- '-createCredential'
}

install_sqlplus_with_homebrew() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is not installed, so db-work cannot use Homebrew for SQLPlus." >&2
    return 127
  fi

  echo "Installing Oracle Instant Client SQL*Plus with Homebrew..."
  brew tap InstantClientTap/instantclient
  brew install InstantClientTap/instantclient/instantclient-basic
  brew install InstantClientTap/instantclient/instantclient-sqlplus
}

install_sqlplus_with_oracle_dmg() {
  local arch basic_url sqlplus_url tmpdir dmg url volume installer
  local mounted_volumes=()

  if ! command -v curl >/dev/null 2>&1 || ! command -v hdiutil >/dev/null 2>&1; then
    echo "curl and hdiutil are required for Oracle DMG installation on macOS." >&2
    return 127
  fi

  arch="$(uname -m)"
  case "$arch" in
    arm64)
      basic_url="https://download.oracle.com/otn_software/mac/instantclient/instantclient-basic-macos-arm64.dmg"
      sqlplus_url="https://download.oracle.com/otn_software/mac/instantclient/instantclient-sqlplus-macos-arm64.dmg"
      ;;
    x86_64)
      basic_url="https://download.oracle.com/otn_software/mac/instantclient/instantclient-basic-macos.dmg"
      sqlplus_url="https://download.oracle.com/otn_software/mac/instantclient/instantclient-sqlplus-macos.dmg"
      ;;
    *)
      echo "Unsupported macOS architecture for Oracle Instant Client auto-install: $arch" >&2
      return 127
      ;;
  esac

  tmpdir="$(mktemp -d)"

  cleanup_mounts() {
    local mounted
    if ((${#mounted_volumes[@]} > 0)); then
      for mounted in "${mounted_volumes[@]}"; do
        /usr/bin/hdiutil detach "$mounted" >/dev/null 2>&1 || true
      done
    fi
    rm -rf "$tmpdir"
  }
  trap cleanup_mounts RETURN

  echo "Downloading Oracle Instant Client Basic and SQL*Plus DMGs..."
  for url in "$basic_url" "$sqlplus_url"; do
    dmg="$tmpdir/$(basename "$url")"
    curl -L --fail --show-error --output "$dmg" "$url"
    volume="$(/usr/bin/hdiutil attach -nobrowse -readonly "$dmg" | awk '/\/Volumes\// {for (i=1;i<=NF;i++) if ($i ~ /^\/Volumes\//) {print $i; exit}}')"
    if [[ -z "$volume" ]]; then
      echo "Mounted $dmg, but could not determine the volume path." >&2
      return 127
    fi
    mounted_volumes+=("$volume")
  done

  installer=""
  for volume in "${mounted_volumes[@]}"; do
    if [[ -f "$volume/install_ic.sh" ]]; then
      installer="$volume/install_ic.sh"
      break
    fi
  done

  if [[ -z "$installer" ]]; then
    echo "Could not find install_ic.sh in mounted Oracle Instant Client DMGs." >&2
    return 127
  fi

  echo "Running Oracle Instant Client installer: $installer"
  sh "$installer"
}

ensure_sqlplus() {
  local sqlplus_bin install_mode

  sqlplus_bin="$(tool_path sqlplus || true)"
  if [[ -n "$sqlplus_bin" ]]; then
    echo "sqlplus is available: $sqlplus_bin"
    "$sqlplus_bin" -v
    return 0
  fi

  if [[ "$no_install" == "1" || "${DB_WORK_AUTO_INSTALL_SQLPLUS:-1}" == "0" ]]; then
    print_manual_guidance
    return 127
  fi

  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Automatic SQLPlus installation is currently implemented only for macOS." >&2
    print_manual_guidance
    return 127
  fi

  install_mode="${DB_WORK_SQLPLUS_INSTALL_MODE:-oracle-dmg}"
  case "$install_mode" in
    oracle-dmg)
      install_sqlplus_with_oracle_dmg
      ;;
    homebrew)
      install_sqlplus_with_homebrew
      ;;
    *)
      echo "Unknown DB_WORK_SQLPLUS_INSTALL_MODE: $install_mode" >&2
      return 2
      ;;
  esac

  hash -r
  sqlplus_bin="$(tool_path sqlplus || true)"
  if [[ -n "$sqlplus_bin" ]]; then
    echo "sqlplus installed: $sqlplus_bin"
    "$sqlplus_bin" -v
    echo "For future interactive shells, add this directory to PATH:"
    echo "  export PATH=\"$(dirname "$sqlplus_bin"):\$PATH\""
    return 0
  fi

  echo "SQLPlus installation finished, but sqlplus is still not discoverable." >&2
  print_manual_guidance
  return 127
}

install_mkstore() {
  local version home lib_dir bin_dir artifact jar jar_url launcher

  if ! command -v java >/dev/null 2>&1; then
    echo "Java is required for mkstore setup, but java was not found on PATH." >&2
    print_mkstore_guidance
    return 127
  fi

  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for mkstore setup, but curl was not found on PATH." >&2
    print_mkstore_guidance
    return 127
  fi

  version="${DB_WORK_MKSTORE_VERSION:-23.26.1.0.0}"
  home="${DB_WORK_MKSTORE_HOME:-$HOME/.oracle/mkstore}"
  lib_dir="$home/lib"
  bin_dir="$home/bin"
  artifact="oracle""pki"
  jar="$lib_dir/$artifact-$version.jar"
  jar_url="https://repo.maven.apache.org/maven2/com/oracle/database/security/$artifact/$version/$artifact-$version.jar"
  launcher="$bin_dir/mkstore"

  mkdir -p "$lib_dir" "$bin_dir"
  chmod 700 "$home" "$lib_dir" "$bin_dir" 2>/dev/null || true

  if [[ ! -f "$jar" ]]; then
    echo "Downloading Oracle mkstore wallet library..."
    curl -L --fail --show-error --output "$jar" "$jar_url"
  fi

  cat > "$launcher" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec java -cp "$jar" oracle.security.pki.OracleSecretStoreTextUI "\$@"
EOF
  chmod 700 "$launcher"
  echo "mkstore launcher installed: $launcher"
}

ensure_mkstore() {
  local mkstore_bin

  mkstore_bin="$(tool_path mkstore || true)"
  if [[ -n "$mkstore_bin" ]]; then
    if mkstore_is_usable "$mkstore_bin"; then
      echo "mkstore is available: $mkstore_bin"
      return 0
    fi
    echo "Found mkstore, but it does not appear to support -createCredential: $mkstore_bin" >&2
  fi

  if [[ "$no_install" == "1" || "${DB_WORK_AUTO_INSTALL_MKSTORE:-1}" == "0" ]]; then
    print_mkstore_guidance
    return 127
  fi

  install_mkstore
  hash -r
  mkstore_bin="$(tool_path mkstore || true)"
  if [[ -n "$mkstore_bin" ]]; then
    if mkstore_is_usable "$mkstore_bin"; then
      echo "mkstore installed and usable: $mkstore_bin"
      return 0
    fi
  fi

  echo "mkstore setup finished, but mkstore is still not discoverable or usable." >&2
  print_mkstore_guidance
  return 127
}

ensure_sqlplus

if [[ "$require_wallet_tools" == "1" ]]; then
  ensure_mkstore
fi
