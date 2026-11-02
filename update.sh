#!/usr/bin/env bash
# Update the Antigravity Dev Suite in place (git pull) and re-register the hooks.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
if [ -d "${SCRIPT_DIR}/.git" ]; then
  git -C "${SCRIPT_DIR}" pull --ff-only
fi
exec bash "${SCRIPT_DIR}/install.sh" "$@"
