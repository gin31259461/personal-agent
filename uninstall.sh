#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="personal-agent"
APP_USER="personal-agent"
APP_GROUP="personal-agent"
APP_DIR="/opt/personal-agent"
CONFIG_DIR="/etc/personal-agent"
STATE_DIR="/var/lib/personal-agent"
SERVICE_FILE="/etc/systemd/system/personal-agent.service"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || die "run this script as root: sudo ./uninstall.sh [--purge]"
command -v systemctl >/dev/null 2>&1 || die "systemd is required"

PURGE=0
if [[ "${1:-}" == "--purge" ]]; then
  PURGE=1
elif [[ "$#" -gt 0 ]]; then
  die "usage: sudo ./uninstall.sh [--purge]"
fi

systemctl disable --now "${APP_NAME}.service" 2>/dev/null || true
rm -f "${SERVICE_FILE}"
systemctl daemon-reload

rm -rf "${APP_DIR}"

if [[ "${PURGE}" -eq 1 ]]; then
  rm -rf "${CONFIG_DIR}" "${STATE_DIR}"
  userdel "${APP_USER}" 2>/dev/null || true
  groupdel "${APP_GROUP}" 2>/dev/null || true
  printf '%s removed, including configuration and runtime state.\n' "${APP_NAME}"
else
  printf '%s removed. Kept %s and %s.\n' "${APP_NAME}" "${CONFIG_DIR}" "${STATE_DIR}"
  printf 'Use --purge to remove those directories and the service user.\n'
fi
