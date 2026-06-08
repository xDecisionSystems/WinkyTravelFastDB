#!/usr/bin/env bash
# proxmox_deploy.sh
# Create a Debian LXC on Proxmox and deploy Winky Travel FastDB.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="${SCRIPT_DIR}/../.env.dev"
ENV_FILE="${ENV_FILE:-${DEFAULT_ENV_FILE}}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

PROXMOX_HOST="${PROXMOX_HOST:-}"
VMID="${VMID:-}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
REPO_URL="${REPO_URL:-https://github.com/xDecisionSystems/WinkyTravelFastDB.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
LXC_IP="${LXC_IP:-dhcp}"
GATEWAY="${GATEWAY:-}"
DNS="${DNS:-8.8.8.8}"
TEMPLATE="${TEMPLATE:-}"
DRY_RUN=0

HOSTNAME="winky-travel-fastdb"
INSTALL_DIR="/opt/winky-travel-fastdb"
VENV_DIR="/opt/winky-travel-fastdb-env"
SERVICE_NAME="winky-travel-fastdb"
API_PORT=8000

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }
EXISTING_STACKS=""
FOUND_VMID=""
UPLOAD_ENV_FILE="${UPLOAD_ENV_FILE:-}"
declare -a STORAGE_LIST

SSH_SOCKET=""

ssh_open() {
  local host="$1"
  SSH_SOCKET="$(mktemp -u /tmp/ssh-mux-XXXXXX)"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] ssh -M -o ControlMaster=yes ... root@${host}"
    return 0
  fi
  ssh -o StrictHostKeyChecking=accept-new \
      -o ControlMaster=yes \
      -o ControlPath="${SSH_SOCKET}" \
      -o ControlPersist=yes \
      -fN "root@${host}"
  trap 'ssh_close' EXIT
}

ssh_close() {
  if [[ -n "${SSH_SOCKET}" && "${DRY_RUN}" != "1" ]]; then
    ssh -o ControlPath="${SSH_SOCKET}" -O exit "root@${PROXMOX_HOST}" 2>/dev/null || true
  fi
}

confirm_yes_default() {
  local prompt="$1"
  local reply
  read -r -p "${prompt} [Y/n] " reply
  reply="${reply:-y}"
  [[ "${reply,,}" == "y" ]]
}
prompt_with_default() {
  local var_name="$1"
  local prompt_text="$2"
  local current_value="${!var_name:-}"
  local input=""

  if [[ -n "${current_value}" ]]; then
    read -r -p "${prompt_text} [${current_value}]: " input
  else
    read -r -p "${prompt_text}: " input
  fi
  if [[ -n "${input}" ]]; then
    printf -v "${var_name}" "%s" "${input}"
  fi
}

ssh_run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] ssh root@${PROXMOX_HOST} $*"
    return 0
  fi
  ssh -o ControlPath="${SSH_SOCKET}" "root@${PROXMOX_HOST}" "$@"
}

lxc_exec() {
  local vmid="$1"; shift
  ssh_run "pct exec ${vmid} -- env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 bash -c $(printf '%q' "$*")"
}

next_available_vmid() {
  local next_vmid
  next_vmid="$(
    ssh -o ControlPath="${SSH_SOCKET}" "root@${PROXMOX_HOST}" \
      "pvesh get /cluster/nextid 2>/dev/null || \
       { used=\$(pct list | awk 'NR>1{print \$1}' | sort -n); \
         id=100; for u in \$used; do [ \$id -lt \$u ] && break; id=\$((u+1)); done; echo \$id; }" \
      | tr -d '[:space:]\"' \
      || true
  )"
  [[ "${next_vmid}" =~ ^[0-9]+$ ]] || return 1
  echo "${next_vmid}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --proxmox-host) PROXMOX_HOST="$2"; shift 2 ;;
    --vmid) VMID="$2"; shift 2 ;;
    --storage) STORAGE="$2"; shift 2 ;;
    --bridge) BRIDGE="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --repo-branch) REPO_BRANCH="$2"; shift 2 ;;
    --ip) LXC_IP="$2"; shift 2 ;;
    --gateway) GATEWAY="$2"; shift 2 ;;
    --dns) DNS="$2"; shift 2 ;;
    --template) TEMPLATE="$2"; shift 2 ;;
    --upload-env) UPLOAD_ENV_FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) die "Unknown option: $1" ;;
  esac
done

INTERACTIVE=0
if [[ -t 0 && "${SKIP_PROMPTS:-0}" != "1" ]]; then
  INTERACTIVE=1
fi

if [[ "${INTERACTIVE}" == "1" ]]; then
  prompt_with_default PROXMOX_HOST "Proxmox host (IP or hostname)"
fi

[[ -n "${PROXMOX_HOST}" ]] || die "--proxmox-host is required"

log "Opening SSH connection to ${PROXMOX_HOST} ..."
ssh_open "${PROXMOX_HOST}"

# Find existing Winky Travel containers on host.
log "Searching for existing '${HOSTNAME}' containers on ${PROXMOX_HOST} ..."
EXISTING_STACKS="$(
  ssh_run \
    "pct list | awk 'NR>1 {print \$1}' | while read -r id; do
       h=\$(pct config \"\$id\" 2>/dev/null | awk -F': ' '/^hostname:/{print \$2}')
       case \"\$h\" in ${HOSTNAME}*) echo \"\$id \$h\" ;; esac
     done" \
    || true
)"
if [[ -n "${EXISTING_STACKS}" ]]; then
  echo ""
  echo "  Existing ${HOSTNAME} containers:"
  while IFS= read -r line; do
    echo "    VMID $(echo "${line}" | awk '{print $1}')  hostname: $(echo "${line}" | awk '{print $2}')"
  done <<< "${EXISTING_STACKS}"
  FOUND_VMID="$(echo "${EXISTING_STACKS}" | awk -v h="${HOSTNAME}" '$2==h{print $1}' | head -n1)"
fi

if [[ -z "${VMID}" ]]; then
  if [[ -n "${FOUND_VMID}" ]]; then
    VMID="${FOUND_VMID}"
    log "Found existing '${HOSTNAME}' at VMID ${VMID}; defaulting to redeploy that VMID."
  else
    VMID="$(next_available_vmid || true)"
  fi
fi

if [[ "${INTERACTIVE}" == "1" ]]; then
  echo ""
  echo "Configure deployment settings (press Enter to keep current default):"
  if [[ -z "${VMID}" ]]; then
    read -r -p "LXC VMID (auto-detect failed, required): " VMID
  else
    prompt_with_default VMID "LXC VMID"
  fi
  log "Querying available storage pools ..."
  STORAGE_RAW="$(ssh_run "pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && \$3==\"active\" {print \$1, \$2}'" || true)"
  if [[ -n "${STORAGE_RAW}" ]]; then
    mapfile -t STORAGE_LIST <<< "${STORAGE_RAW}"
    echo ""
    echo "Available storage pools for LXC rootfs:"
    default_storage_index=0
    ssd_storage_index=""
    for i in "${!STORAGE_LIST[@]}"; do
      storage_name="$(echo "${STORAGE_LIST[$i]}" | awk '{print $1}')"
      storage_type="$(echo "${STORAGE_LIST[$i]}" | awk '{print $2}')"
      if [[ "${storage_name}" == "${STORAGE}" ]]; then
        default_storage_index="${i}"
      fi
      if [[ -z "${ssd_storage_index}" && "${storage_name,,}" == *ssd* ]]; then
        ssd_storage_index="${i}"
      fi
      echo "  [${i}] ${storage_name} (${storage_type})"
    done
    if [[ -n "${ssd_storage_index}" ]]; then
      default_storage_index="${ssd_storage_index}"
    fi
    echo ""
    read -r -p "Select storage index [${default_storage_index}]: " STORAGE_CHOICE
    STORAGE_CHOICE="${STORAGE_CHOICE:-${default_storage_index}}"
    if [[ "${STORAGE_CHOICE}" =~ ^[0-9]+$ ]] && [[ "${STORAGE_CHOICE}" -lt "${#STORAGE_LIST[@]}" ]]; then
      STORAGE="$(echo "${STORAGE_LIST[$STORAGE_CHOICE]}" | awk '{print $1}')"
    else
      die "Invalid storage index: ${STORAGE_CHOICE}"
    fi
    log "Using storage: ${STORAGE}"
  else
    log "Could not query storage pools; keeping configured storage: ${STORAGE}"
    prompt_with_default STORAGE "Storage pool"
  fi
  prompt_with_default BRIDGE "Network bridge"
  prompt_with_default LXC_IP "LXC IP (dhcp or CIDR)"
  if [[ "${LXC_IP}" != "dhcp" ]]; then
    prompt_with_default GATEWAY "Gateway IP (required for static IP)"
  fi
  prompt_with_default DNS "DNS server"

  if [[ -z "${TEMPLATE}" ]]; then
    log "Querying available Debian templates ..."
    TEMPLATES_RAW="$(ssh_run \
      "pvesm status --content vztmpl 2>/dev/null | awk 'NR>1 {print \$1}' | \
       while read -r storage; do
         pveam list \"\$storage\" 2>/dev/null | awk 'NR>1 {print \$1}'
       done | grep -i 'debian' | sort -rV" \
      || true)"
    if [[ -z "${TEMPLATES_RAW}" ]]; then
      die "No Debian templates found. Download one with: pveam download local debian-12-standard_*.tar.zst"
    fi
    mapfile -t TEMPLATE_LIST <<< "${TEMPLATES_RAW}"
    echo ""
    echo "Available Debian templates:"
    for i in "${!TEMPLATE_LIST[@]}"; do
      echo "  [${i}] ${TEMPLATE_LIST[$i]}"
    done
    read -r -p "Select template index or press Enter for newest (${TEMPLATE_LIST[0]}): " TMPL_CHOICE
    if [[ -z "${TMPL_CHOICE}" || "${TMPL_CHOICE}" == "auto" ]]; then
      TEMPLATE="${TEMPLATE_LIST[0]}"
    elif [[ "${TMPL_CHOICE}" =~ ^[0-9]+$ ]] && [[ "${TMPL_CHOICE}" -lt "${#TEMPLATE_LIST[@]}" ]]; then
      TEMPLATE="${TEMPLATE_LIST[$TMPL_CHOICE]}"
    else
      die "Invalid template index: ${TMPL_CHOICE}"
    fi
  fi
  log "Using template: ${TEMPLATE}"

  SEARCH_DIR="$(pwd)"
  mapfile -t UPLOAD_ENV_CANDIDATES < <(find "${SEARCH_DIR}" -maxdepth 2 -name ".env*" -type f | sort)
  echo ""
  if [[ "${#UPLOAD_ENV_CANDIDATES[@]}" -eq 0 ]]; then
    echo "  No .env files found in ${SEARCH_DIR} — will use .env.example from repo."
  else
    echo "  Available .env files to upload as the container's runtime .env:"
    echo "    [0] (none — use .env.example from repo)"
    default_upload_choice=0
    for i in "${!UPLOAD_ENV_CANDIDATES[@]}"; do
      echo "    [$((i+1))] ${UPLOAD_ENV_CANDIDATES[$i]}"
      if [[ "$(basename "${UPLOAD_ENV_CANDIDATES[$i]}")" == ".env.dev" ]]; then
        default_upload_choice=$((i+1))
      fi
    done
    read -r -p "  Select index or type a path [${default_upload_choice}]: " UPLOAD_ENV_CHOICE
    UPLOAD_ENV_CHOICE="${UPLOAD_ENV_CHOICE:-${default_upload_choice}}"
    if [[ "${UPLOAD_ENV_CHOICE}" != "0" && "${UPLOAD_ENV_CHOICE}" =~ ^[0-9]+$ ]]; then
      idx=$((UPLOAD_ENV_CHOICE - 1))
      if [[ "${idx}" -ge 0 && "${idx}" -lt "${#UPLOAD_ENV_CANDIDATES[@]}" ]]; then
        UPLOAD_ENV_FILE="${UPLOAD_ENV_CANDIDATES[$idx]}"
        log "Will upload: ${UPLOAD_ENV_FILE}"
      else
        echo "  Invalid index — will use .env.example from repo."
      fi
    elif [[ "${UPLOAD_ENV_CHOICE}" != "0" ]]; then
      expanded="${UPLOAD_ENV_CHOICE/#\~/$HOME}"
      if [[ -f "${expanded}" ]]; then
        UPLOAD_ENV_FILE="${expanded}"
        log "Will upload: ${UPLOAD_ENV_FILE}"
      else
        echo "  File not found: ${expanded} — will use .env.example from repo."
      fi
    fi
  fi
fi

DB_ROLE_NAME="winky"
DB_ROLE_PASSWORD="change-this-password"
DB_DATABASE_NAME="winky_travel"
if [[ -n "${UPLOAD_ENV_FILE}" && -f "${UPLOAD_ENV_FILE}" ]]; then
  env_db_user="$(grep -E '^DB_USER=' "${UPLOAD_ENV_FILE}" | tail -n1 | cut -d= -f2-)"
  env_db_password="$(grep -E '^DB_PASSWORD=' "${UPLOAD_ENV_FILE}" | tail -n1 | cut -d= -f2-)"
  env_db_name="$(grep -E '^DB_NAME=' "${UPLOAD_ENV_FILE}" | tail -n1 | cut -d= -f2-)"
  [[ -n "${env_db_user}" ]] && DB_ROLE_NAME="${env_db_user}"
  [[ -n "${env_db_password}" ]] && DB_ROLE_PASSWORD="${env_db_password}"
  [[ -n "${env_db_name}" ]] && DB_DATABASE_NAME="${env_db_name}"
fi

[[ -n "${REPO_URL}" ]] || die "--repo-url is required"
[[ -n "${TEMPLATE}" ]] || die "Unable to determine LXC template automatically. Set TEMPLATE in env or pass --template."
[[ -n "${VMID}" ]] || die "Unable to determine VMID automatically. Set VMID in env or pass --vmid."
[[ "${VMID}" =~ ^[0-9]+$ ]] || die "--vmid must be numeric"

if [[ "${LXC_IP}" == "dhcp" ]]; then
  NET0="name=eth0,bridge=${BRIDGE},ip=dhcp"
else
  [[ -n "${GATEWAY}" ]] || die "--gateway required when using static --ip"
  NET0="name=eth0,bridge=${BRIDGE},ip=${LXC_IP},gw=${GATEWAY}"
fi

if [[ "${INTERACTIVE}" == "1" ]]; then
  echo ""
  echo "  Proxmox host : ${PROXMOX_HOST}"
  echo "  VMID         : ${VMID}"
  echo "  Hostname     : ${HOSTNAME}"
  echo "  IP           : ${LXC_IP}"
  if [[ "${LXC_IP}" != "dhcp" ]]; then
    echo "  Gateway      : ${GATEWAY}"
  fi
  echo "  Template     : ${TEMPLATE}"
  echo "  Storage      : ${STORAGE}"
  echo "  Bridge       : ${BRIDGE}"
  echo "  DNS          : ${DNS}"
  echo "  Repo         : ${REPO_URL} (branch: ${REPO_BRANCH})"
  echo "  Config source: ${ENV_FILE}"
  echo "  Upload .env  : ${UPLOAD_ENV_FILE:-(none — use .env.example from repo)}"
  if [[ -n "${FOUND_VMID}" && "${VMID}" != "${FOUND_VMID}" ]]; then
    echo ""
    echo "  WARNING: existing '${HOSTNAME}' found at VMID ${FOUND_VMID},"
    echo "           but selected VMID is ${VMID}."
  fi
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo ""
    echo "  *** DRY RUN — no changes will be made ***"
  fi
  echo ""
  if ! confirm_yes_default "Proceed?"; then
    log "Aborted."
    exit 0
  fi
fi

EXISTS="$(ssh_run "pct list | awk 'NR>1 {print \$1}' | grep -w '${VMID}' || true")"
if [[ -n "${EXISTS}" ]]; then
  EXISTING_HOSTNAME="$(ssh_run "pct config ${VMID} | awk -F': ' '/^hostname:/{print \$2}'" || echo "unknown")"
  echo ""
  echo "  VMID ${VMID} is already in use by hostname '${EXISTING_HOSTNAME}'."
  echo "  It must be destroyed before redeploy."
  echo ""
  if [[ "${INTERACTIVE}" == "1" ]]; then
    if ! confirm_yes_default "Destroy VMID ${VMID} and continue?"; then
      die "Aborted."
    fi
  else
    die "VMID ${VMID} already exists; re-run interactively to confirm destroy or choose a different --vmid."
  fi
  log "Stopping and destroying VMID ${VMID} ..."
  ssh_run "pct stop ${VMID} --skiplock 1 2>/dev/null || true"
  ssh_run "pct destroy ${VMID} --purge 1"
fi

log "Creating LXC ${VMID} on ${PROXMOX_HOST} ..."
ssh_run "pct create ${VMID} ${TEMPLATE} \
  --hostname ${HOSTNAME} \
  --cores 2 --memory 2048 --swap 512 \
  --rootfs ${STORAGE}:12 \
  --net0 ${NET0} \
  --nameserver ${DNS} \
  --unprivileged 1 \
  --features nesting=1"

ssh_run "pct start ${VMID}"

log "Waiting for LXC to be ready ..."
ssh_run "sleep 6"

log "Generating en_US.UTF-8 locale in container ..."
ssh_run "pct exec ${VMID} -- env LANG=C LC_ALL=C bash -c $(printf '%q' "
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive
  loc_log=\"\$(mktemp)\"
  if ! apt-get update -qq > \"\$loc_log\" 2>&1 || \
     ! apt-get install -y -qq locales >> \"\$loc_log\" 2>&1 || \
     ! sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen || \
     ! locale-gen >> \"\$loc_log\" 2>&1 || \
     ! update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 >> \"\$loc_log\" 2>&1; then
    echo '--- locale setup output ---' >&2
    cat \"\$loc_log\" >&2
    rm -f \"\$loc_log\"
    exit 1
  fi
  rm -f \"\$loc_log\"
")"

log "Installing runtime packages in container ..."
db_role_name_sql="${DB_ROLE_NAME//\'/\'\'}"
db_role_password_sql="${DB_ROLE_PASSWORD//\'/\'\'}"
db_database_name_sql="${DB_DATABASE_NAME//\'/\'\'}"
lxc_exec "${VMID}" "
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive
  apt_log=\"\$(mktemp)\"
  if ! apt-get update -qq > \"\$apt_log\" 2>&1 || \
     ! apt-get install -y -qq git curl python3 python3-venv python3-pip postgresql >> \"\$apt_log\" 2>&1; then
    echo '--- apt output ---' >&2
    cat \"\$apt_log\" >&2
    rm -f \"\$apt_log\"
    exit 1
  fi
  rm -f \"\$apt_log\"
  systemctl enable --now postgresql

  if ! runuser -u postgres -- psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = '${db_role_name_sql}'\" | grep -q 1; then
    runuser -u postgres -- psql -c \"CREATE ROLE ${db_role_name_sql} LOGIN PASSWORD '${db_role_password_sql}'\"
  else
    runuser -u postgres -- psql -c \"ALTER ROLE ${db_role_name_sql} LOGIN PASSWORD '${db_role_password_sql}'\"
  fi
  if ! runuser -u postgres -- psql -tAc \"SELECT 1 FROM pg_database WHERE datname = '${db_database_name_sql}'\" | grep -q 1; then
    runuser -u postgres -- psql -c \"CREATE DATABASE ${db_database_name_sql} OWNER ${db_role_name_sql}\"
  fi
"

log "Cloning backend repo ..."
lxc_exec "${VMID}" "
  set -euo pipefail
  useradd -m -s /bin/bash winky || true
  rm -rf ${INSTALL_DIR}
  git clone --branch ${REPO_BRANCH} ${REPO_URL} ${INSTALL_DIR}
  python3 -m venv ${VENV_DIR}
  ${VENV_DIR}/bin/pip install --quiet --upgrade pip
  ${VENV_DIR}/bin/pip install --quiet -r ${INSTALL_DIR}/requirements.txt
  chown -R winky:winky ${INSTALL_DIR} ${VENV_DIR}
"

ENV_DEST="${INSTALL_DIR}/.env"
if [[ -n "${UPLOAD_ENV_FILE}" && -f "${UPLOAD_ENV_FILE}" ]]; then
  log "Uploading ${UPLOAD_ENV_FILE} -> LXC:${ENV_DEST} ..."
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] scp ${UPLOAD_ENV_FILE} -> LXC:${ENV_DEST}"
  else
    tmp_remote="$(ssh_run "mktemp")"
    scp -o ControlPath="${SSH_SOCKET}" "${UPLOAD_ENV_FILE}" "root@${PROXMOX_HOST}:${tmp_remote}"
    ssh_run "pct push ${VMID} ${tmp_remote} ${ENV_DEST} --perms 0600 && rm -f ${tmp_remote}"
    lxc_exec "${VMID}" "chown winky:winky ${ENV_DEST}"
  fi
  log "Env file uploaded."
else
  log "No env file supplied — copying .env.example ..."
  lxc_exec "${VMID}" "
    if [ -f ${INSTALL_DIR}/.env.example ]; then
      cp ${INSTALL_DIR}/.env.example ${ENV_DEST}
      chown winky:winky ${ENV_DEST}
      chmod 0600 ${ENV_DEST}
    fi
  "
  log "Edit ${ENV_DEST} on VMID ${VMID} to verify database and API settings."
fi

log "Writing systemd unit ..."
lxc_exec "${VMID}" "
  cat > /etc/systemd/system/${SERVICE_NAME}.service <<'EOF'
[Unit]
Description=Winky Travel FastDB API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=winky
Group=winky
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn api.main:app --host 0.0.0.0 --port ${API_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now ${SERVICE_NAME}
"

log "Waiting for ${SERVICE_NAME} API on port ${API_PORT} ..."
lxc_exec "${VMID}" "
  for i in \$(seq 1 15); do
    curl -sf http://127.0.0.1:${API_PORT}/health > /dev/null 2>&1 && exit 0
    sleep 2
  done
  echo '--- ${SERVICE_NAME} service status ---'
  systemctl status ${SERVICE_NAME} --no-pager -l || true
  echo '--- last 50 journal lines ---'
  journalctl -u ${SERVICE_NAME} -n 50 --no-pager || true
  echo '${SERVICE_NAME} did not start in time'; exit 1
"
log "${SERVICE_NAME} PASSED."

LXC_ACTUAL_IP="$(ssh_run "pct exec ${VMID} -- hostname -I 2>/dev/null | awk '{print \$1}'" || echo "(check manually)")"

log ""
log "=== Deployment complete ==="
log ""
echo "  ${SERVICE_NAME} health  http://${LXC_ACTUAL_IP}:${API_PORT}/health"
echo "  ${SERVICE_NAME} docs    http://${LXC_ACTUAL_IP}:${API_PORT}/docs"
echo ""
