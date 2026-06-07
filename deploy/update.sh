#!/usr/bin/env bash
# update.sh — Pull latest code, reinstall dependencies, and restart services.

set -euo pipefail

INSTALL_DIR="/opt/winky-travel-fastdb"
VENV_DIR="/opt/winky-travel-fastdb-env"
SERVICE_NAME="winky-travel-fastdb"

log() { echo "[update] $*"; }
die() { echo "[update] ERROR: $*" >&2; exit 1; }

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  die "Install directory not found: ${INSTALL_DIR}"
fi

OLD_VERSION="$(grep '^VERSION_NAME=' "${INSTALL_DIR}/VERSION.md" 2>/dev/null | cut -d= -f2 || echo 'unknown')"

log "Pulling latest code in ${INSTALL_DIR} ..."
git -C "${INSTALL_DIR}" pull --ff-only

log "Installing Python dependencies ..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

log "Reloading systemd daemon ..."
systemctl daemon-reload

log "Restarting services ..."
bash "${INSTALL_DIR}/deploy/restart.sh"

NEW_VERSION="$(grep '^VERSION_NAME=' "${INSTALL_DIR}/VERSION.md" 2>/dev/null | cut -d= -f2 || echo 'unknown')"
log "Update complete: ${OLD_VERSION} -> ${NEW_VERSION}"
