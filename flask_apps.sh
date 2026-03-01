#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="${ROOT_DIR}/.flask-multi"
PID_DIR="${RUN_DIR}/pids"
LOG_DIR="${RUN_DIR}/logs"

# Format: name|relative_dir|port|venv_dir
APPS=(
  "mycite-ne_mw|mycite-ne_mw|5000|.venv"
  "mycite-le_cvcc|mycite-le_cvcc|5001|.venv"
  "mycite-le_fnd|mycite-le_fnd|5002|.venv"
)

usage() {
  cat <<'EOF'
Usage: ./flask_apps.sh [start|stop|status|restart|run]

Commands:
  start    Start all configured Flask apps in the background.
  stop     Stop all running Flask apps started by this script.
  status   Show running/stopped state for each configured app.
  restart  Stop then start all configured apps.
  run      Start all apps in the foreground; Ctrl+C stops all.
EOF
}

ensure_runtime_dirs() {
  mkdir -p "${PID_DIR}" "${LOG_DIR}"
}

is_running_pid() {
  local pid="$1"
  kill -0 "${pid}" 2>/dev/null
}

start_app() {
  local name="$1"
  local rel_dir="$2"
  local port="$3"
  local venv_dir="$4"
  local app_dir="${ROOT_DIR}/${rel_dir}"
  local pid_file="${PID_DIR}/${name}.pid"
  local log_file="${LOG_DIR}/${name}.log"
  local python_bin="${app_dir}/${venv_dir}/bin/python"

  if [[ -f "${pid_file}" ]]; then
    local existing_pid
    existing_pid="$(cat "${pid_file}")"
    if [[ -n "${existing_pid}" ]] && is_running_pid "${existing_pid}"; then
      echo "[skip] ${name} already running (pid ${existing_pid})"
      return 0
    fi
    rm -f "${pid_file}"
  fi

  if [[ ! -d "${app_dir}" ]]; then
    echo "[warn] ${name} skipped: missing app directory ${app_dir}"
    return 0
  fi

  if [[ ! -x "${python_bin}" ]]; then
    echo "[warn] ${name} skipped: missing venv python ${python_bin}"
    return 0
  fi

  (
    cd "${app_dir}"
    nohup "${python_bin}" -m flask --app app run --host 127.0.0.1 --port "${port}" >"${log_file}" 2>&1 &
    echo $! > "${pid_file}"
  )
  sleep 0.2
  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && is_running_pid "${pid}"; then
    echo "[ok]   ${name} started on http://127.0.0.1:${port} (log: ${log_file})"
    return 0
  fi

  rm -f "${pid_file}"
  echo "[err]  ${name} failed to start (see log: ${log_file})"
}

stop_app() {
  local name="$1"
  local pid_file="${PID_DIR}/${name}.pid"

  if [[ ! -f "${pid_file}" ]]; then
    echo "[skip] ${name} not running (no pid file)"
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -z "${pid}" ]]; then
    rm -f "${pid_file}"
    echo "[skip] ${name} pid file was empty"
    return 0
  fi

  if is_running_pid "${pid}"; then
    kill "${pid}" 2>/dev/null || true
    for _ in {1..20}; do
      if ! is_running_pid "${pid}"; then
        break
      fi
      sleep 0.1
    done
    if is_running_pid "${pid}"; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
    echo "[ok]   ${name} stopped (pid ${pid})"
  else
    echo "[skip] ${name} not running (stale pid ${pid})"
  fi

  rm -f "${pid_file}"
}

show_status() {
  local name="$1"
  local rel_dir="$2"
  local port="$3"
  local pid_file="${PID_DIR}/${name}.pid"
  local app_dir="${ROOT_DIR}/${rel_dir}"

  if [[ ! -f "${pid_file}" ]]; then
    echo "[down] ${name} (${app_dir}) -> http://127.0.0.1:${port}"
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && is_running_pid "${pid}"; then
    echo "[up]   ${name} pid=${pid} -> http://127.0.0.1:${port}"
  else
    echo "[down] ${name} (stale pid file: ${pid}) -> http://127.0.0.1:${port}"
  fi
}

start_all() {
  ensure_runtime_dirs
  for entry in "${APPS[@]}"; do
    IFS='|' read -r name rel_dir port venv_dir <<< "${entry}"
    start_app "${name}" "${rel_dir}" "${port}" "${venv_dir}"
  done
}

stop_all() {
  ensure_runtime_dirs
  for entry in "${APPS[@]}"; do
    IFS='|' read -r name _ <<< "${entry}"
    stop_app "${name}"
  done
}

status_all() {
  ensure_runtime_dirs
  for entry in "${APPS[@]}"; do
    IFS='|' read -r name rel_dir port _ <<< "${entry}"
    show_status "${name}" "${rel_dir}" "${port}"
  done
}

run_foreground() {
  start_all
  trap 'stop_all; exit 0' INT TERM
  echo "All apps started. Press Ctrl+C to stop all."

  while true; do
    local running_count=0
    for entry in "${APPS[@]}"; do
      IFS='|' read -r name _ <<< "${entry}"
      local pid_file="${PID_DIR}/${name}.pid"
      if [[ -f "${pid_file}" ]]; then
        local pid
        pid="$(cat "${pid_file}")"
        if [[ -n "${pid}" ]] && is_running_pid "${pid}"; then
          running_count=$((running_count + 1))
        fi
      fi
    done
    if [[ "${running_count}" -eq 0 ]]; then
      echo "No apps are running. Exiting."
      exit 1
    fi
    sleep 1
  done
}

main() {
  local command="${1:-run}"
  case "${command}" in
    start) start_all ;;
    stop) stop_all ;;
    status) status_all ;;
    restart)
      stop_all
      start_all
      ;;
    run) run_foreground ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
