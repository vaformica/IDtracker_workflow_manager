#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --prefix ABSOLUTE_PATH --source ABSOLUTE_REPO_PATH --config ABSOLUTE_CONFIG_PATH [--dry-run]"
}

install_prefix=""
source_repository=""
backend_config=""
dry_run="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      install_prefix="${2:-}"
      shift 2
      ;;
    --source)
      source_repository="${2:-}"
      shift 2
      ;;
    --config)
      backend_config="${2:-}"
      shift 2
      ;;
    --dry-run)
      dry_run="true"
      shift
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$install_prefix" || -z "$source_repository" || -z "$backend_config" ]]; then
  usage
  exit 2
fi

for required_path in "$install_prefix" "$source_repository" "$backend_config"; do
  if [[ "$required_path" != /* ]]; then
    echo "All paths must be absolute: $required_path" >&2
    exit 2
  fi
done

if [[ ! -d "$source_repository" ]]; then
  echo "Source repository does not exist: $source_repository" >&2
  exit 2
fi

if [[ ! -f "$backend_config" ]]; then
  echo "Backend configuration does not exist: $backend_config" >&2
  exit 2
fi

venv_path="$install_prefix/venv"
installed_config="$install_prefix/config/backend.json"

if [[ "$dry_run" == "true" ]]; then
  echo "Would create virtual environment: $venv_path"
  echo "Would install package from: $source_repository"
  echo "Would install configuration only if absent: $installed_config"
  echo "Would run the backend read-only dry-run check"
  exit 0
fi

mkdir -p "$install_prefix/config"
python3 -m venv "$venv_path"
"$venv_path/bin/python" -m pip install --no-deps "$source_repository"

if [[ -e "$installed_config" ]]; then
  echo "Configuration already exists; leaving it unchanged: $installed_config"
else
  install -m 0640 "$backend_config" "$installed_config"
fi

"$venv_path/bin/idtracker-firebird-backend" \
  --config "$installed_config" \
  --dry-run

echo "Backend command:"
echo "$venv_path/bin/idtracker-firebird-backend --config $installed_config --request"
