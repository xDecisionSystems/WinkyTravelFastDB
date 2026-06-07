#!/usr/bin/env bash
# proxmox_deploy.sh
# Create a Debian LXC on Proxmox and deploy Winky Travel FastDB.

set -euo pipefail

PROXMOX_HOST="${PROXMOX_HOST:-}"
VMID="${VMID:-220}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
REPO_URL="${REPO_URL:-}"
REPO_BRANCH="${REPO_BRANCH:-main}"
LXC_IP="${LXC_IP:-dhcp}"
GATEWAY="${GATEWAY:-}"
DNS="${DNS:-8.8.8.8}"
TEMPLATE="${TEMPLATE:-local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst}"

HOSTNAME="winky-travel-fastdb"
INSTALL_DIR="/opt/winky-travel-fastdb"
VENV_DIR="/opt/winky-travel-fastdb-env"
SERVICE_NAME="winky-travel-fastdb"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

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
    *) die "Unknown option: $1" ;;
  esac
done

[[ -n "${PROXMOX_HOST}" ]] || die "--proxmox-host is required"
[[ -n "${REPO_URL}" ]] || die "--repo-url is required"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new)

if [[ "${LXC_IP}" == "dhcp" ]]; then
  NET0="name=eth0,bridge=${BRIDGE},ip=dhcp"
else
  [[ -n "${GATEWAY}" ]] || die "--gateway required when using static --ip"
  NET0="name=eth0,bridge=${BRIDGE},ip=${LXC_IP},gw=${GATEWAY}"
fi

log "Creating LXC ${VMID} on ${PROXMOX_HOST} ..."
ssh "${SSH_OPTS[@]}" "root@${PROXMOX_HOST}" "pct create ${VMID} ${TEMPLATE} \
  --hostname ${HOSTNAME} \
  --cores 2 --memory 2048 --swap 512 \
  --rootfs ${STORAGE}:12 \
  --net0 ${NET0} \
  --nameserver ${DNS} \
  --unprivileged 1 \
  --features nesting=1"

ssh "${SSH_OPTS[@]}" "root@${PROXMOX_HOST}" "pct start ${VMID}"

log "Installing runtime packages in container ..."
ssh "${SSH_OPTS[@]}" "root@${PROXMOX_HOST}" "pct exec ${VMID} -- bash -lc '
  set -euo pipefail
  apt-get update
  apt-get install -y git curl python3 python3-venv python3-pip postgresql
  systemctl enable --now postgresql

  if ! runuser -u postgres -- psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = \$\$winky\$\$\" | grep -q 1; then
    runuser -u postgres -- psql -c \"CREATE ROLE winky LOGIN PASSWORD \$\$change-this-password\$\$\"
  fi
  if ! runuser -u postgres -- psql -tAc \"SELECT 1 FROM pg_database WHERE datname = \$\$winky_travel\$\$\" | grep -q 1; then
    runuser -u postgres -- psql -c \"CREATE DATABASE winky_travel OWNER winky\"
  fi
'
"

log "Cloning backend repo ..."
ssh "${SSH_OPTS[@]}" "root@${PROXMOX_HOST}" "pct exec ${VMID} -- bash -lc '
  set -euo pipefail
  useradd -m -s /bin/bash winky || true
  rm -rf ${INSTALL_DIR}
  git clone --branch ${REPO_BRANCH} ${REPO_URL} ${INSTALL_DIR}
  python3 -m venv ${VENV_DIR}
  ${VENV_DIR}/bin/pip install --upgrade pip
  ${VENV_DIR}/bin/pip install -r ${INSTALL_DIR}/requirements.txt
  if [ ! -f ${INSTALL_DIR}/.env ] && [ -f ${INSTALL_DIR}/.env.example ]; then
    cp ${INSTALL_DIR}/.env.example ${INSTALL_DIR}/.env
  fi
  chown -R winky:winky ${INSTALL_DIR} ${VENV_DIR}
'
"

log "Writing systemd unit ..."
ssh "${SSH_OPTS[@]}" "root@${PROXMOX_HOST}" "pct exec ${VMID} -- bash -lc '
  cat > /etc/systemd/system/${SERVICE_NAME}.service << UNIT
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
ExecStart=${VENV_DIR}/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now ${SERVICE_NAME}
'
"

log "Deployment complete."
log "Verify: curl http://<lxc-ip>:8000/health"
