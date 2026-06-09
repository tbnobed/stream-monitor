#!/usr/bin/env bash
#
# OTT Stream Monitor — Ubuntu installer.
#
# Installs Docker Engine + the Compose plugin (if missing), generates deploy/.env
# on first run, then builds and starts the full stack (db + api + web).
#
# Usage (from anywhere; the whole repository must be present on this server):
#   sudo bash deploy/install.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $EUID -ne 0 ]]; then
  echo "This installer needs root to install Docker. Re-run with:  sudo bash deploy/install.sh" >&2
  exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "x86_64" && "$ARCH" != "amd64" ]]; then
  echo "WARNING: detected architecture '$ARCH'. The frontend build is pinned to"
  echo "         x86_64/amd64 (see pnpm-workspace.yaml platform overrides) and"
  echo "         will likely fail to build on this machine."
  read -r -p "Continue anyway? [y/N] " reply
  [[ "${reply:-N}" =~ ^[Yy]$ ]] || exit 1
fi

# ---------------------------------------------------------------------------
# 1. Install Docker Engine + Compose plugin (official Docker apt repository).
# ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker Engine..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
  fi
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  echo "==> Docker already installed: $(docker --version)"
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: 'docker compose' plugin is not available after installation." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Create deploy/.env on first run (generates a strong DB password).
# ---------------------------------------------------------------------------
rand_hex() {
  # $1 = number of bytes
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

if [[ ! -f .env ]]; then
  echo "==> Generating deploy/.env ..."
  PW="$(rand_hex 24)"
  SECRET="$(rand_hex 32)"
  ADMIN_PW="$(rand_hex 12)"
  cat > .env <<EOF
POSTGRES_USER=ott
POSTGRES_PASSWORD=${PW}
POSTGRES_DB=ott_monitor
DATABASE_URL=postgresql://ott:${PW}@127.0.0.1:5432/ott_monitor

# --- Authentication ---
SESSION_SECRET=${SECRET}
SESSION_COOKIE_SECURE=false
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=${ADMIN_PW}

# --- Authentik / OIDC SSO (optional; leave blank to disable) ---
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_DISCOVERY_URL=
OIDC_REDIRECT_URI=
OIDC_DISPLAY_NAME=SSO
EOF
  chmod 600 .env
  echo "    Wrote deploy/.env (keep this file private)."
  echo "    Initial login: admin / ${ADMIN_PW}"
  echo "    (also stored as INITIAL_ADMIN_PASSWORD in deploy/.env — change it after first sign-in)."
else
  echo "==> deploy/.env already exists; leaving it untouched."
  if ! grep -q '^SESSION_SECRET=' .env; then
    echo "==> Adding a generated SESSION_SECRET to existing deploy/.env ..."
    {
      echo ""
      echo "# --- Authentication (added by install.sh) ---"
      echo "SESSION_SECRET=$(rand_hex 32)"
    } >> .env
  fi
fi

# ---------------------------------------------------------------------------
# 3. Preflight: warn if a non-Docker process already holds a required port.
# ---------------------------------------------------------------------------
port_held_by_foreign_proc() {
  # Returns 0 if $1 is listening and NOT owned by docker-proxy/dockerd.
  command -v ss >/dev/null 2>&1 || return 1
  local line
  line="$(ss -ltnp 2>/dev/null | awk -v p=":$1\$" '$4 ~ p')" || return 1
  [[ -n "$line" ]] || return 1
  grep -Eq 'docker-proxy|dockerd|com.docker' <<<"$line" && return 1
  return 0
}
for p in 80 8080 5432; do
  if port_held_by_foreign_proc "$p"; then
    echo "WARNING: port ${p} is already in use by a non-Docker process; the stack may fail to bind it."
  fi
done

# ---------------------------------------------------------------------------
# 4. Build images and start the stack.
# ---------------------------------------------------------------------------
echo "==> Building and starting containers (this can take a few minutes)..."
docker compose up -d --build

echo
echo "==> Done. Stack status:"
docker compose ps

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "OTT Stream Monitor is starting up."
echo "  Open:        http://${IP:-<server-ip>}/"
echo "  Follow logs: (cd deploy && docker compose logs -f)"
echo "  Stop:        (cd deploy && docker compose down)"
echo
echo "For native device control, this server must be on the SAME LAN/subnet as"
echo "your OTT devices, and each device needs its IP set in the Devices page."
echo
echo "Firewall (recommended, defense-in-depth): expose only the web UI."
echo "  sudo ufw allow 80/tcp"
echo "  # The API (8080) and PostgreSQL (5432) bind to loopback only and should"
echo "  # NOT be opened to the network."
