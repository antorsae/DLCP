#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/flash_control_safe.sh [options]

Safe control-flash wrapper. Enforces:
  1) bootloader-integrity preflight
  2) explicit operator confirmation
  3) CRC verify enabled (never disabled here)

Options:
  --hex PATH              Control HEX to flash
  --bootloader-ref PATH   Trusted reference HEX for bootloader check
  --python PATH           Python interpreter (default: .venv_ep0/bin/python or python3)
  --vid INT               USB VID (decimal or 0x...)
  --pid INT               USB PID (decimal or 0x...)
  --path STR              hidapi path for specific device selection
  --pace-ms INT           Inter-report delay in ms (default: 0, ACK-paced like HFD)
  --init-delay-ms INT     Delay before first 0x42 data report in ms (default: 0)
  --report-timeout-ms INT Timeout waiting for each 0x42 ACK (default: 5000)
  --live-timeout-s INT    Kill the live flash subprocess after this many seconds (default: 180)
  --preflight-only        Run checks only; do not flash
  --yes                   Skip confirmation prompt for live flash
  -h, --help              Show this help

Unsafe flags are intentionally refused:
  --no-verify --skip-bootloader-check --force-unsafe
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_HEX="${ROOT_DIR}/firmware/patched/releases/DLCP_Control_V1.72.hex"
DEFAULT_BOOT_REF="${ROOT_DIR}/firmware/stock/control/DLCP Control Firmware V1.6b.hex"
DEFAULT_PYTHON="${ROOT_DIR}/.venv_ep0/bin/python"

HEX="${DEFAULT_HEX}"
BOOT_REF="${DEFAULT_BOOT_REF}"
if [[ -x "${DEFAULT_PYTHON}" ]]; then
  PYTHON="${DEFAULT_PYTHON}"
else
  PYTHON="python3"
fi

VID=""
PID=""
HID_PATH=""
PACE_MS=""
INIT_DELAY_MS=""
REPORT_TIMEOUT_MS=""
LIVE_TIMEOUT_S="180"
PREFLIGHT_ONLY=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hex)
      [[ $# -ge 2 ]] || { echo "error: --hex requires a value" >&2; exit 2; }
      HEX="$2"
      shift 2
      ;;
    --bootloader-ref)
      [[ $# -ge 2 ]] || { echo "error: --bootloader-ref requires a value" >&2; exit 2; }
      BOOT_REF="$2"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 ]] || { echo "error: --python requires a value" >&2; exit 2; }
      PYTHON="$2"
      shift 2
      ;;
    --vid)
      [[ $# -ge 2 ]] || { echo "error: --vid requires a value" >&2; exit 2; }
      VID="$2"
      shift 2
      ;;
    --pid)
      [[ $# -ge 2 ]] || { echo "error: --pid requires a value" >&2; exit 2; }
      PID="$2"
      shift 2
      ;;
    --path)
      [[ $# -ge 2 ]] || { echo "error: --path requires a value" >&2; exit 2; }
      HID_PATH="$2"
      shift 2
      ;;
    --pace-ms)
      [[ $# -ge 2 ]] || { echo "error: --pace-ms requires a value" >&2; exit 2; }
      PACE_MS="$2"
      shift 2
      ;;
    --init-delay-ms)
      [[ $# -ge 2 ]] || { echo "error: --init-delay-ms requires a value" >&2; exit 2; }
      INIT_DELAY_MS="$2"
      shift 2
      ;;
    --report-timeout-ms)
      [[ $# -ge 2 ]] || { echo "error: --report-timeout-ms requires a value" >&2; exit 2; }
      REPORT_TIMEOUT_MS="$2"
      shift 2
      ;;
    --live-timeout-s)
      [[ $# -ge 2 ]] || { echo "error: --live-timeout-s requires a value" >&2; exit 2; }
      LIVE_TIMEOUT_S="$2"
      shift 2
      ;;
    --preflight-only)
      PREFLIGHT_ONLY=1
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --no-verify|--skip-bootloader-check|--force-unsafe)
      echo "error: unsafe flag '$1' is not allowed in scripts/flash_control_safe.sh" >&2
      exit 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option '$1'" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${PYTHON}" == */* ]]; then
  [[ -x "${PYTHON}" ]] || { echo "error: python interpreter not executable: ${PYTHON}" >&2; exit 2; }
else
  command -v "${PYTHON}" >/dev/null 2>&1 || { echo "error: python interpreter not found: ${PYTHON}" >&2; exit 2; }
fi

[[ -f "${HEX}" ]] || { echo "error: control HEX not found: ${HEX}" >&2; exit 2; }
[[ -f "${BOOT_REF}" ]] || { echo "error: bootloader reference HEX not found: ${BOOT_REF}" >&2; exit 2; }

common_cmd=("${PYTHON}" "-m" "dlcp_fw.flash.dlcp_control_flash" "--hex" "${HEX}" "--bootloader-ref" "${BOOT_REF}")
[[ -n "${VID}" ]] && common_cmd+=("--vid" "${VID}")
[[ -n "${PID}" ]] && common_cmd+=("--pid" "${PID}")
[[ -n "${HID_PATH}" ]] && common_cmd+=("--path" "${HID_PATH}")
[[ -n "${PACE_MS}" ]] && common_cmd+=("--pace-ms" "${PACE_MS}")
[[ -n "${INIT_DELAY_MS}" ]] && common_cmd+=("--init-delay-ms" "${INIT_DELAY_MS}")
[[ -n "${REPORT_TIMEOUT_MS}" ]] && common_cmd+=("--report-timeout-ms" "${REPORT_TIMEOUT_MS}")

echo "[safe-flash] running preflight"
preflight_cmd=("${common_cmd[@]}" "--preflight-only" "-v")
(
  cd "${ROOT_DIR}"
  "${preflight_cmd[@]}"
)

if [[ ${PREFLIGHT_ONLY} -eq 1 ]]; then
  echo "[safe-flash] preflight-only requested; no USB writes performed"
  exit 0
fi

if [[ ${ASSUME_YES} -ne 1 ]]; then
  read -r -p "[safe-flash] preflight passed. Proceed with live control flash? [y/N] " reply
  case "${reply}" in
    y|Y|yes|YES)
      ;;
    *)
      echo "[safe-flash] aborted by operator"
      exit 1
      ;;
  esac
fi

echo "[safe-flash] starting live control flash"
flash_cmd=("${common_cmd[@]}" "-v")
(
  cd "${ROOT_DIR}"
  "${PYTHON}" -c '
import subprocess
import sys

timeout_s = float(sys.argv[1])
cmd = sys.argv[2:]
try:
    completed = subprocess.run(cmd, timeout=timeout_s)
except subprocess.TimeoutExpired:
    print(
        f"[safe-flash] live control flash timed out after {timeout_s:g}s; "
        "CONTROL is likely not in UP+DOWN bootloader mode or the selected "
        "MAIN is not connected to CONTROL. For manual bootloader entry, "
        "power-cycle while holding UP+DOWN for at least 6s and do not press "
        "SELECT; retry if the LCD returns to Volume.",
        file=sys.stderr,
        flush=True,
    )
    raise SystemExit(124)
raise SystemExit(completed.returncode)
' "${LIVE_TIMEOUT_S}" "${flash_cmd[@]}"
)
echo "[safe-flash] done"
