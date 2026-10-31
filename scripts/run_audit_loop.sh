#!/usr/bin/env bash
# ==============================================================================
# Antigravity Dev Suite — Multi-Iteration Autonomous Audit & Self-Healing Loop
# Executes /antigravity-dev-suite:opus-dev audit & fix prompt iteratively.
# ==============================================================================
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -euo pipefail

# Default Configuration
TOTAL_ITERATIONS=10
DELAY_SECONDS="${DELAY_SECONDS:-3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${WORKSPACE_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
LOG_FILE="${LOG_FILE:-${WORKSPACE_DIR}/agy_audit_current.log}"
MODEL=""
PROMPT="/antigravity-dev-suite:opus-dev esegui un audit fortemente critico sulla plugin antigravity-dev-suite per trovare inefficienze, lacune, punti di miglioramento, controindicazioni o errori rispetto all'obiettivo che la plugin si pone. poi esegui un loop in cui implementi tutte le fix, riesegui l'audit lanciato poco fa e se serve implementi le nuove fix. Continua a loopare finchè non ci sono più fix da fare. Se ti aiuta usa /goal."

usage() {
  cat <<EOF
Usage: $(basename "$0") [options] [iterations]

Options:
  -n, --iterations <N>    Number of audit iterations (default: 10)
  -d, --delay <SEC>       Delay in seconds between iterations (default: 3)
  -p, --prompt <STR>      Custom audit prompt
  -m, --model <MODEL>     Specify LLM model (e.g. claude-3-7-sonnet, gemini-2.5-pro)
  -w, --workspace <DIR>   Target workspace directory
  -l, --log <FILE>        Output log file path
  -h, --help              Display this help message
EOF
  exit 0
}

# Parse Command Line Arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--iterations)
      TOTAL_ITERATIONS="$2"
      shift 2
      ;;
    -d|--delay)
      DELAY_SECONDS="$2"
      shift 2
      ;;
    -p|--prompt)
      PROMPT="$2"
      shift 2
      ;;
    -m|--model)
      MODEL="$2"
      shift 2
      ;;
    -w|--workspace)
      WORKSPACE_DIR="$2"
      shift 2
      ;;
    -l|--log)
      LOG_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        TOTAL_ITERATIONS="$1"
        shift
      else
        echo "Unknown option: $1" >&2
        usage
      fi
      ;;
  esac
done

# Resolve AGY Binary
resolve_agy_binary() {
  if [ -n "${AGY_BIN:-}" ] && [ -x "${AGY_BIN}" ]; then
    echo "${AGY_BIN}"
    return 0
  fi

  if command -v agy >/dev/null 2>&1; then
    command -v agy
    return 0
  fi

  local candidate_paths=(
    "/opt/homebrew/bin/agy"
    "/usr/local/bin/agy"
    "${HOME}/.gemini/antigravity-cli/bin/agy"
    "${HOME}/.local/bin/agy"
    "/usr/bin/agy"
  )

  for p in "${candidate_paths[@]}"; do
    if [ -x "${p}" ]; then
      echo "${p}"
      return 0
    fi
  done

  return 1
}

if ! AGY_EXEC="$(resolve_agy_binary)"; then
  echo "❌ Error: 'agy' CLI executable was not found in PATH or standard installation locations." >&2
  exit 1
fi

echo "================================================================================"
echo "🚀 Antigravity Autonomous Audit Loop Engine"
echo "Binary:        ${AGY_EXEC}"
echo "Workspace:     ${WORKSPACE_DIR}"
echo "Iterations:    ${TOTAL_ITERATIONS}"
echo "Delay:         ${DELAY_SECONDS}s between iterations"
[ -n "${MODEL}" ] && echo "Model:         ${MODEL}"
echo "Live Log:      ${LOG_FILE}"
echo "================================================================================"
echo ""

# Handle graceful exit on Ctrl+C / SIGTERM
cleanup() {
  echo ""
  echo "🛑 Received stop signal. Terminated by user."
  exit 130
}
trap cleanup SIGINT SIGTERM

# Move to workspace directory if present
if [ -d "${WORKSPACE_DIR}" ]; then
  cd "${WORKSPACE_DIR}"
fi

# Ensure log file exists
mkdir -p "$(dirname "${LOG_FILE}")"
touch "${LOG_FILE}"

# Prepare agy CLI arguments array
AGY_ARGS=("--dangerously-skip-permissions")
if [ -n "${MODEL}" ]; then
  AGY_ARGS+=("--model" "${MODEL}")
fi
AGY_ARGS+=("-p" "${PROMPT}")

# Main Iteration Loop
for ((i=1; i<=TOTAL_ITERATIONS; i++)); do
  START_TIME=$(date +%s)
  TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
  
  echo "--------------------------------------------------------------------------------" | tee -a "${LOG_FILE}"
  echo "🔄 [Iteration ${i}/${TOTAL_ITERATIONS}] Started at ${TIMESTAMP}" | tee -a "${LOG_FILE}"
  echo "Prompt: ${PROMPT}" | tee -a "${LOG_FILE}"
  echo "--------------------------------------------------------------------------------" | tee -a "${LOG_FILE}"

  # Run agy directly with real-time streaming output
  set +e
  "${AGY_EXEC}" "${AGY_ARGS[@]}" 2>&1 | tee -a "${LOG_FILE}"
  EXIT_CODE="${PIPESTATUS[0]}"
  set -e

  END_TIME=$(date +%s)
  DURATION=$((END_TIME - START_TIME))

  if [ "${EXIT_CODE}" -eq 0 ]; then
    echo "✅ [Iteration ${i}/${TOTAL_ITERATIONS}] Completed successfully (Duration: ${DURATION}s)" | tee -a "${LOG_FILE}"
  else
    echo "⚠️  [Iteration ${i}/${TOTAL_ITERATIONS}] Finished with exit code ${EXIT_CODE} (Duration: ${DURATION}s)" | tee -a "${LOG_FILE}"
  fi

  # Delay before restarting agy if not the last iteration
  if [ "${i}" -lt "${TOTAL_ITERATIONS}" ]; then
    echo "⏳ Waiting ${DELAY_SECONDS}s before launching next iteration..." | tee -a "${LOG_FILE}"
    sleep "${DELAY_SECONDS}"
    echo "" | tee -a "${LOG_FILE}"
  fi
done

echo "================================================================================" | tee -a "${LOG_FILE}"
echo "🎉 All ${TOTAL_ITERATIONS} iterations finished." | tee -a "${LOG_FILE}"
echo "================================================================================" | tee -a "${LOG_FILE}"
