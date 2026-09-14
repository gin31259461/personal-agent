#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="personal-agent"
APP_USER="personal-agent"
APP_GROUP="personal-agent"
APP_DIR="/opt/personal-agent"
PYTHON_INSTALL_DIR="/opt/personal-agent-runtime/python"
CONFIG_DIR="/etc/personal-agent"
STATE_DIR="/var/lib/personal-agent"
SERVICE_FILE="/etc/systemd/system/personal-agent.service"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || die "run this script as root: sudo ./install.sh"
command -v uv >/dev/null 2>&1 || die "uv is required; install it before running this script"
command -v systemctl >/dev/null 2>&1 || die "systemd is required"

[[ -f "${SCRIPT_DIR}/pyproject.toml" ]] || die "pyproject.toml not found beside install.sh"
[[ -f "${SCRIPT_DIR}/uv.lock" ]] || die "uv.lock not found beside install.sh"
[[ -f "${SCRIPT_DIR}/config.toml" ]] || die "config.toml is required beside install.sh"
[[ -f "${SCRIPT_DIR}/.env" ]] || die ".env is required beside install.sh"

if ! getent group "${APP_GROUP}" >/dev/null; then
  groupadd --system "${APP_GROUP}"
fi
if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --gid "${APP_GROUP}" --home-dir "${STATE_DIR}" \
    --create-home --shell /usr/bin/nologin "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_GROUP}" "${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" "${STATE_DIR}"
install -d -m 0750 -o root -g "${APP_GROUP}" "${CONFIG_DIR}"

cp -a "${SCRIPT_DIR}/pyproject.toml" "${APP_DIR}/"
cp -a "${SCRIPT_DIR}/uv.lock" "${APP_DIR}/"
cp -a "${SCRIPT_DIR}/.python-version" "${APP_DIR}/"
rm -rf "${APP_DIR}/src"
cp -a "${SCRIPT_DIR}/src" "${APP_DIR}/"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
  install -m 0640 -o root -g "${APP_GROUP}" \
    "${SCRIPT_DIR}/config.toml" "${CONFIG_DIR}/config.toml"
else
  printf 'keeping existing %s\n' "${CONFIG_DIR}/config.toml"
fi

if [[ ! -f "${CONFIG_DIR}/agent.env" ]]; then
  install -m 0640 -o root -g "${APP_GROUP}" \
    "${SCRIPT_DIR}/.env" "${CONFIG_DIR}/agent.env"
else
  printf 'keeping existing %s\n' "${CONFIG_DIR}/agent.env"
fi

# The service reads this file as APP_USER. Keep it root-owned while granting
# read access through the service group, including for files from old installs.
chown root:"${APP_GROUP}" "${CONFIG_DIR}/agent.env"
chmod 0640 "${CONFIG_DIR}/agent.env"

# Do not let uv install Python under /root.  The systemd service runs as
# personal-agent and must be able to traverse the managed Python path.
install -d -m 0755 -o root -g root "$(dirname -- "${PYTHON_INSTALL_DIR}")"
install -d -m 0755 -o root -g root "${PYTHON_INSTALL_DIR}"

systemctl stop "${APP_NAME}.service" 2>/dev/null || true

UV_PYTHON_INSTALL_DIR="${PYTHON_INSTALL_DIR}" \
  uv python install 3.13 \
  --install-dir "${PYTHON_INSTALL_DIR}" \
  --managed-python

cd "${APP_DIR}"
UV_PYTHON_INSTALL_DIR="${PYTHON_INSTALL_DIR}" \
  uv venv --clear \
  --python 3.13 \
  --managed-python \
  "${VENV_DIR}"

UV_PYTHON_INSTALL_DIR="${PYTHON_INSTALL_DIR}" \
  uv sync --locked --python "${VENV_DIR}/bin/python"

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

[[ -x "${VENV_DIR}/bin/python" ]] || die "virtualenv interpreter was not created: ${VENV_DIR}/bin/python"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/python" --version >/dev/null \
  || die "${APP_USER} cannot execute ${VENV_DIR}/bin/python"

install -m 0644 "${SCRIPT_DIR}/deploy/personal-agent.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable --now "${APP_NAME}.service"

printf '\n%s installed and started.\n' "${APP_NAME}"
systemctl --no-pager --full status "${APP_NAME}.service" || true
