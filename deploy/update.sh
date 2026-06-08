#!/usr/bin/env bash
# update.sh — Pull latest code, reinstall dependencies, and restart services.
#
# Usage:
#   bash /opt/winky-travel-fastdb/deploy/update.sh

set -euo pipefail

INSTALL_DIR="/opt/winky-travel-fastdb"
VENV_DIR="/opt/winky-travel-fastdb-env"
SERVICE_NAME="winky-travel-fastdb"

log() { echo "[update] $*"; }
die() { echo "[update] ERROR: $*" >&2; exit 1; }

repo_owner_user() {
  local owner
  owner="$(stat -c '%U' "${INSTALL_DIR}" 2>/dev/null || true)"
  [[ -n "${owner}" && "${owner}" != "UNKNOWN" ]] || die "Could not determine repo owner for ${INSTALL_DIR}"
  echo "${owner}"
}

git_repo_cmd() {
  if [[ "${REPO_OWNER}" == "root" ]]; then
    git -C "${INSTALL_DIR}" "$@"
  else
    runuser -u "${REPO_OWNER}" -- git -C "${INSTALL_DIR}" "$@"
  fi
}

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

  # Prevent app reconnect loops while we forcibly drop the DB.
  log "Stopping ${SERVICE_NAME} before database recreation ..."
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true

  log "Recreating SQL database '${DB_NAME}' owned by '${DB_USER}' ..."
  if ! runuser -u postgres -- dropdb --if-exists --force "${DB_NAME}"; then
    log "dropdb --force failed; terminating active DB sessions manually ..."
    runuser -u postgres -- psql -d postgres -v ON_ERROR_STOP=1 -v dbname="${DB_NAME}" \
      -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'dbname' AND pid <> pg_backend_pid();" \
      >/dev/null
    runuser -u postgres -- dropdb --if-exists "${DB_NAME}"
  fi
  runuser -u postgres -- createdb --owner="${DB_USER}" "${DB_NAME}"
}

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  die "Install directory not found: ${INSTALL_DIR}"
fi

REPO_OWNER="$(repo_owner_user)"
OLD_VERSION="$(grep '^VERSION_NAME=' "${INSTALL_DIR}/VERSION.md" 2>/dev/null | cut -d= -f2 || echo 'unknown')"
OLD_COMMIT_FULL="$(git_repo_cmd rev-parse HEAD 2>/dev/null || echo 'unknown')"
OLD_COMMIT_SHORT="$(git_repo_cmd rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
CURRENT_BRANCH="$(git_repo_cmd rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'main')"

log "Fetching remote metadata ..."
git_repo_cmd fetch --quiet origin
REMOTE_REF="origin/${CURRENT_BRANCH}"
if ! git_repo_cmd show-ref --verify --quiet "refs/remotes/${REMOTE_REF}"; then
  REMOTE_REF="origin/main"
fi
REMOTE_VERSION="$({ git_repo_cmd show "${REMOTE_REF}:VERSION.md" 2>/dev/null | grep '^VERSION_NAME=' | cut -d= -f2; } || echo 'unknown')"
REMOTE_COMMIT_SHORT="$(git_repo_cmd rev-parse --short "${REMOTE_REF}" 2>/dev/null || echo 'unknown')"
INCOMING_CHANGES="$(git_repo_cmd --no-pager diff --name-status "HEAD..${REMOTE_REF}" || true)"

if [[ -t 0 ]]; then
  echo ""
  echo "  Current : ${OLD_VERSION} (${OLD_COMMIT_SHORT})"
  echo "  Incoming: ${REMOTE_VERSION} (${REMOTE_COMMIT_SHORT})"
  if [[ -n "${INCOMING_CHANGES}" ]]; then
    echo ""
    echo "  Incoming file changes:"
    while IFS= read -r change_line; do
      [[ -n "${change_line}" ]] && echo "    ${change_line}"
    done <<< "${INCOMING_CHANGES}"
  fi
  echo ""
  read -r -p "  Proceed with update? [Y/n] " PROCEED_UPDATE
  case "${PROCEED_UPDATE}" in
    [nN]|[nN][oO])
      log "Aborted."
      exit 0
      ;;
    *) ;;
  esac
  echo ""
fi

log "Pulling latest code in ${INSTALL_DIR} ..."
git_repo_cmd pull --ff-only

log "Installing Python dependencies ..."
PIP_LOG="$(mktemp /tmp/winky-update-pip.XXXXXX.log)"
if ! "${VENV_DIR}/bin/pip" install --quiet --upgrade pip >"${PIP_LOG}" 2>&1; then
  log "pip upgrade failed. Recent output:"
  tail -n 200 "${PIP_LOG}" >&2 || true
  rm -f "${PIP_LOG}"
  die "Python dependency install failed."
fi
if ! "${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt" >>"${PIP_LOG}" 2>&1; then
  log "pip requirements install failed. Recent output:"
  tail -n 200 "${PIP_LOG}" >&2 || true
  rm -f "${PIP_LOG}"
  die "Python dependency install failed."
fi
rm -f "${PIP_LOG}"

maybe_recreate_database

log "Reloading systemd daemon ..."
systemctl daemon-reload

log "Restarting ${SERVICE_NAME} stack ..."
bash "${INSTALL_DIR}/deploy/restart.sh"

NEW_VERSION="$(grep '^VERSION_NAME=' "${INSTALL_DIR}/VERSION.md" 2>/dev/null | cut -d= -f2 || echo 'unknown')"
NEW_COMMIT_FULL="$(git_repo_cmd rev-parse HEAD 2>/dev/null || echo 'unknown')"
NEW_COMMIT_SHORT="$(git_repo_cmd rev-parse --short HEAD 2>/dev/null || echo 'unknown')"

CHANGED_FILES=""
if [[ "${OLD_COMMIT_FULL}" != "unknown" && "${NEW_COMMIT_FULL}" != "unknown" && "${OLD_COMMIT_FULL}" != "${NEW_COMMIT_FULL}" ]]; then
  CHANGED_FILES="$(git_repo_cmd --no-pager diff --name-status "${OLD_COMMIT_FULL}..${NEW_COMMIT_FULL}" || true)"
fi

log ""
log "=== Update complete ==="
log "  Version: ${OLD_VERSION} -> ${NEW_VERSION}"
log "  Commit : ${OLD_COMMIT_SHORT} -> ${NEW_COMMIT_SHORT}"
if [[ -n "${CHANGED_FILES}" ]]; then
  log "  Changed files:"
  while IFS= read -r changed_line; do
    [[ -n "${changed_line}" ]] && log "    ${changed_line}"
  done <<< "${CHANGED_FILES}"
else
  log "  Changed files: none"
fi
