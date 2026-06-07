#!/usr/bin/env bash
# update.sh — Pull latest code, reinstall dependencies, and restart services.

set -euo pipefail

INSTALL_DIR="/opt/winky-travel-fastdb"
VENV_DIR="/opt/winky-travel-fastdb-env"
SERVICE_NAME="winky-travel-fastdb"

log() { echo "[update] $*"; }
die() { echo "[update] ERROR: $*" >&2; exit 1; }

confirm() {
  local prompt="$1"
  local reply
  read -r -p "${prompt} [Y/n]: " reply
  [[ "${reply}" =~ ^([Yy]([Ee][Ss])?)?$ ]]
}

parse_database_url() {
  local database_url="$1"
  DB_USER="$(echo "${database_url}" | sed -E 's#^[a-zA-Z0-9+.-]+://([^:/@]+)(:[^@]*)?@[^/]+/([^?]+).*$#\1#')"
  DB_NAME="$(echo "${database_url}" | sed -E 's#^[a-zA-Z0-9+.-]+://([^:/@]+)(:[^@]*)?@[^/]+/([^?]+).*$#\3#')"

  if [[ -z "${DB_USER}" || -z "${DB_NAME}" || "${DB_USER}" == "${database_url}" || "${DB_NAME}" == "${database_url}" ]]; then
    die "Could not parse DATABASE_URL. Expected format: postgresql://user:pass@host:5432/dbname"
  fi
}

get_env_value() {
  local env_file="$1"
  local key="$2"
  local raw
  raw="$(grep -E "^${key}=" "${env_file}" | tail -n1 | cut -d= -f2- || true)"
  raw="${raw%%$'\r'}"
  if [[ "${raw}" == \"*\" && "${raw}" == *\" ]]; then
    raw="${raw:1:${#raw}-2}"
  elif [[ "${raw}" == \'*\' ]]; then
    raw="${raw:1:${#raw}-2}"
  fi
  echo "${raw}"
}

load_database_identity_from_env() {
  local env_file="$1"
  DB_USER="$(get_env_value "${env_file}" "DB_USER")"
  DB_NAME="$(get_env_value "${env_file}" "DB_NAME")"

  if [[ -n "${DB_USER}" && -n "${DB_NAME}" ]]; then
    return 0
  fi

  # Backward compatibility for environments still using DATABASE_URL.
  local database_url
  database_url="$(get_env_value "${env_file}" "DATABASE_URL")"
  [[ -n "${database_url}" ]] || die "Missing DB_USER/DB_NAME (or DATABASE_URL) in ${env_file}"
  parse_database_url "${database_url}"
}

maybe_recreate_database() {
  local env_file="${INSTALL_DIR}/.env"

  if [[ ! -f "${env_file}" ]]; then
    die "Environment file not found: ${env_file}"
  fi

  load_database_identity_from_env "${env_file}"

  if [[ -t 0 ]]; then
    if ! confirm "Destroy and recreate SQL database '${DB_NAME}' (owner '${DB_USER}')?"; then
      log "Keeping existing SQL database."
      return 0
    fi
  else
    log "Non-interactive shell detected; skipping SQL database recreation prompt."
    return 0
  fi

  log "Recreating SQL database '${DB_NAME}' owned by '${DB_USER}' ..."
  runuser -u postgres -- dropdb --if-exists "${DB_NAME}"
  runuser -u postgres -- createdb --owner="${DB_USER}" "${DB_NAME}"
}

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  die "Install directory not found: ${INSTALL_DIR}"
fi

OLD_VERSION="$(grep '^VERSION_NAME=' "${INSTALL_DIR}/VERSION.md" 2>/dev/null | cut -d= -f2 || echo 'unknown')"

log "Pulling latest code in ${INSTALL_DIR} ..."
git -C "${INSTALL_DIR}" pull --ff-only

log "Installing Python dependencies ..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

maybe_recreate_database

log "Reloading systemd daemon ..."
systemctl daemon-reload

log "Restarting services ..."
bash "${INSTALL_DIR}/deploy/restart.sh"

NEW_VERSION="$(grep '^VERSION_NAME=' "${INSTALL_DIR}/VERSION.md" 2>/dev/null | cut -d= -f2 || echo 'unknown')"
log "Update complete: ${OLD_VERSION} -> ${NEW_VERSION}"
